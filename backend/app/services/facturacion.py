"""Emisión de comprobantes electrónicos a partir de una venta.

Traduce una venta del ERP al JSON de FactPro, dispara el envío (real o
simulado) y persiste el comprobante con todo lo que devuelve SUNAT.
"""

import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.fechas import hoy_local
from app.models.comprobante import (
    ComprobanteElectronico,
    EstadoComprobante,
    TipoComprobante,
)
from app.models.cliente import TipoDocumento
from app.models.venta import EstadoVenta, TipoVenta, Venta
from app.services import (
    factpro_client,
    nubefact_catalogos,
    nubefact_client,
    nubefact_facturacion,
)
from app.services.nubefact_catalogos import ERROR_YA_EXISTE
from app.services.factpro_catalogos import (
    ESTADO_SUNAT_ACEPTADO,
    ESTADO_SUNAT_ANULADO,
    ESTADO_SUNAT_REGISTRADO,
    ESTADO_SUNAT_RECHAZADO,
    TIPO_COMPROBANTE_SUNAT,
    NUM_DOC_SIN_CLIENTE,
    TIPO_DOC_CLIENTE,
    TIPO_DOC_SIN_CLIENTE,
    TIPO_TAX_GRAVADO,
    UNIDAD_POR_DEFECTO,
)

#: Estados en los que el comprobante sigue "vivo": bloquean re-emitir la venta.
ESTADOS_VIGENTES = {
    EstadoComprobante.PENDIENTE,
    EstadoComprobante.REGISTRADO,
    EstadoComprobante.ACEPTADO,
}

#: SUNAT permite boleta sin identificar al cliente sólo hasta este monto.
TOPE_BOLETA_SIN_DOCUMENTO = Decimal("700.00")

#: IGV general. El ERP sólo maneja operaciones gravadas; exonerado o inafecto
#: exigirían desglosar por ítem, no a nivel documento.
IGV_TASA = Decimal("0.18")


def desglosar_igv(total: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    """Reparte un total que YA incluye IGV en (base, igv, total).

    Los precios del ERP son de mostrador —impuesto incluido—, así que la base
    se obtiene dividiendo. El IGV se calcula por diferencia para que las tres
    cifras sumen exactas y no aparezca un céntimo de descuadre al totalizar.
    """
    total = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    base = (total / (Decimal("1") + IGV_TASA)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return base, total - base, total


def _siguiente_numero(db: Session, serie: str) -> int:
    """Número correlativo de la serie, desde una secuencia dedicada.

    Con FactPro esto sólo servía para la simulación, porque el número lo
    asignaba el proveedor. **Con Nubefact es la fuente de verdad**: el
    correlativo lo manda el emisor y debe ser consecutivo desde 1 por tipo de
    documento, sin huecos ni repeticiones.

    Las secuencias de Postgres no retroceden con un ROLLBACK. Eso es
    deliberado aquí: si dos cajeros emiten a la vez, cada uno recibe un número
    distinto sin bloquearse. A cambio, un envío fallido deja su número
    reservado, y por eso el reintento reutiliza el del comprobante en ERROR en
    vez de pedir otro (ver `_numero_reservado`).
    """
    seq = f"comprobante_{serie.lower()}_seq"
    db.execute(text(f"CREATE SEQUENCE IF NOT EXISTS {seq}"))
    return int(db.scalar(text(f"SELECT nextval('{seq}')")))


def _numero_reservado(db: Session, venta_id: uuid.UUID, serie: str) -> int | None:
    """Número que ya se había reservado para esta venta en un intento fallido.

    Reutilizarlo evita dejar huecos en la numeración, que SUNAT observa. Sólo
    se consideran los intentos de la misma serie: cambiar de boleta a factura
    (porque se corrigió el documento del cliente) exige número nuevo.
    """
    return db.scalar(
        select(ComprobanteElectronico.numero).where(
            ComprobanteElectronico.venta_id == venta_id,
            ComprobanteElectronico.estado == EstadoComprobante.ERROR,
            ComprobanteElectronico.serie == serie,
            ComprobanteElectronico.numero > 0,
        )
        .order_by(ComprobanteElectronico.numero.desc())
        .limit(1)
    )


def _tipo_para(venta: Venta) -> TipoComprobante:
    """Factura si el cliente tiene RUC; boleta en cualquier otro caso."""
    if venta.cliente and venta.cliente.tipo_documento is TipoDocumento.RUC:
        return TipoComprobante.FACTURA
    return TipoComprobante.BOLETA


def _serie_para(tipo: TipoComprobante) -> str:
    return (
        settings.SERIE_FACTURA
        if tipo is TipoComprobante.FACTURA
        else settings.SERIE_BOLETA
    )


def _datos_cliente(venta: Venta) -> dict[str, str]:
    """Identidad del receptor. Sin cliente, se emite boleta a 'clientes varios'."""
    if venta.cliente is None:
        return {
            "cliente_tipo_documento": TIPO_DOC_SIN_CLIENTE,
            "cliente_numero_documento": NUM_DOC_SIN_CLIENTE,
            "cliente_denominacion": "CLIENTES VARIOS",
            "cliente_direccion": "-",
            "cliente_email": "",
            "cliente_telefono": "",
        }
    c = venta.cliente
    return {
        "cliente_tipo_documento": TIPO_DOC_CLIENTE[c.tipo_documento],
        "cliente_numero_documento": c.numero_documento,
        "cliente_denominacion": c.nombre,
        "cliente_direccion": c.direccion or "-",
        "cliente_email": c.email or "",
        "cliente_telefono": c.telefono or "",
    }


def _construir_payload(venta: Venta, tipo: TipoComprobante, serie: str) -> dict:
    """Arma el JSON de FactPro.

    Los precios del ERP ya incluyen IGV (precio de mostrador), así que se envía
    `incluye_tax: true` y FactPro desglosa el impuesto. El descuento global de
    la venta se reparte al no existir un campo de descuento a nivel documento en
    el comprobante simple: se prorratea sobre los ítems.
    """
    items = []
    for it in venta.items:
        # El detalle libre de la línea se anexa a la descripción: SUNAT no tiene
        # un campo aparte, pero así queda impreso en el comprobante.
        descripcion = f"{it.descripcion} - {it.detalle}" if it.detalle else it.descripcion
        # El descuento de línea del ERP está en soles; FactPro lo toma directo.
        items.append(
            {
                "unidad": UNIDAD_POR_DEFECTO,
                "codigo": it.producto.sku if it.producto else "",
                "descripcion": descripcion,
                "cantidad": float(it.cantidad),
                "precio": float(it.precio_unitario),
                "incluye_tax": True,
                "tipo_tax": TIPO_TAX_GRAVADO,
                "descuento": float(it.descuento),
            }
        )

    payload = {
        "serie": serie,
        "numero": "#",  # FactPro asigna el correlativo
        # Fecha de Lima, no del servidor: una boleta emitida a las 8 p. m.
        # viajaría a SUNAT fechada al día siguiente.
        "fecha_de_emision": hoy_local().isoformat(),
        "moneda": settings.MONEDA_POR_DEFECTO,
        "tipo_operacion": "1",
        "enviar_automaticamente_al_cliente": False,
        "cliente": _datos_cliente(venta),
        "items": items,
        "condicion_de_pago": [
            {"tipo_de_condicion": "0", "forma_de_pago": "0", "monto": float(venta.total)}
        ],
        "observaciones": venta.notas or "",
        "formato_pdf": "a4",
    }
    return payload


def _aplicar_respuesta(comprobante: ComprobanteElectronico, respuesta: dict) -> None:
    """Vuelca la respuesta de FactPro sobre el comprobante."""
    data = respuesta.get("data", {})
    archivos = respuesta.get("archivos", {})

    comprobante.respuesta = respuesta
    comprobante.es_simulado = bool(respuesta.get("_simulado"))
    comprobante.hash_cpe = data.get("hash")
    comprobante.qr = data.get("qr")
    comprobante.tipo_estado_sunat = data.get("tipo_estado")
    comprobante.descripcion_estado_sunat = data.get("descripcion_estado")
    comprobante.xml_url = archivos.get("xml") or None
    comprobante.pdf_url = archivos.get("pdf") or None
    comprobante.cdr_url = archivos.get("cdr") or None
    comprobante.estado = _estado_desde_sunat(data.get("tipo_estado"))


def _estado_desde_sunat(tipo_estado: str | None) -> EstadoComprobante:
    return {
        ESTADO_SUNAT_REGISTRADO: EstadoComprobante.REGISTRADO,
        ESTADO_SUNAT_ACEPTADO: EstadoComprobante.ACEPTADO,
        ESTADO_SUNAT_RECHAZADO: EstadoComprobante.RECHAZADO,
        ESTADO_SUNAT_ANULADO: EstadoComprobante.ANULADO,
    }.get(tipo_estado or "", EstadoComprobante.REGISTRADO)


def comprobante_vigente_de(db: Session, venta_id: uuid.UUID) -> ComprobanteElectronico | None:
    return db.scalar(
        select(ComprobanteElectronico).where(
            ComprobanteElectronico.venta_id == venta_id,
            ComprobanteElectronico.estado.in_(ESTADOS_VIGENTES),
        )
    )


def emitir_desde_venta(
    db: Session, venta: Venta, actor_id: uuid.UUID | None
) -> ComprobanteElectronico:
    if venta.tipo is not TipoVenta.VENTA:
        raise HTTPException(status_code=409, detail="Una cotización no se factura; conviértela primero")
    if venta.estado is not EstadoVenta.CONFIRMADA:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La venta está {venta.estado.value.lower()} y no se puede facturar",
        )

    existente = comprobante_vigente_de(db, venta.id)
    if existente is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La venta ya tiene el comprobante {existente.numero_completo}",
        )

    tipo = _tipo_para(venta)
    serie = _serie_para(tipo)

    # Boleta sin cliente identificado sólo procede bajo el tope de SUNAT.
    if (
        tipo is TipoComprobante.BOLETA
        and venta.cliente is None
        and venta.total > TOPE_BOLETA_SIN_DOCUMENTO
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Una boleta sin cliente identificado no puede superar "
                f"S/ {TOPE_BOLETA_SIN_DOCUMENTO}. Registra el cliente."
            ),
        )

    if settings.usa_nubefact:
        return _emitir_nubefact(db, venta, tipo, serie, actor_id)
    return _emitir_factpro(db, venta, tipo, serie, actor_id)


def _nuevo_comprobante(
    venta: Venta,
    tipo: TipoComprobante,
    serie: str,
    numero: int,
    cliente_tipo: str,
    cliente_numero: str,
    cliente_denominacion: str,
    payload: dict,
    actor_id: uuid.UUID | None,
) -> ComprobanteElectronico:
    """Comprobante local, con los importes ya congelados.

    Los importes se guardan aquí y no se leen de la venta al consultarlos: un
    comprobante es un documento tributario y su monto no puede cambiar después
    ni desaparecer si la venta se borra.
    """
    base, igv, total = desglosar_igv(venta.total)
    return ComprobanteElectronico(
        tipo=tipo,
        estado=EstadoComprobante.PENDIENTE,
        serie=serie,
        numero=numero,
        venta_id=venta.id,
        fecha_emision=hoy_local(),
        moneda=settings.MONEDA_POR_DEFECTO,
        base_imponible=base,
        igv=igv,
        total=total,
        cliente_tipo_documento=cliente_tipo,
        cliente_numero_documento=cliente_numero,
        cliente_denominacion=cliente_denominacion,
        payload_enviado=payload,
        usuario_id=actor_id,
    )


def _emitir_nubefact(
    db: Session,
    venta: Venta,
    tipo: TipoComprobante,
    serie: str,
    actor_id: uuid.UUID | None,
) -> ComprobanteElectronico:
    """Emisión por Nubefact: el correlativo lo lleva el ERP, no el proveedor."""
    # Un intento anterior ya reservó número: se reutiliza para no dejar huecos
    # en la numeración, que SUNAT observa.
    numero = _numero_reservado(db, venta.id, serie) or _siguiente_numero(db, serie)

    payload = nubefact_facturacion.construir_payload(venta, tipo, serie, numero)
    comprobante = _nuevo_comprobante(
        venta,
        tipo,
        serie,
        numero,
        payload["cliente_tipo_de_documento"],
        payload["cliente_numero_de_documento"],
        payload["cliente_denominacion"],
        payload,
        actor_id,
    )

    try:
        respuesta = nubefact_client.emitir(payload)
    except nubefact_client.NubefactError as exc:
        # El código 23 significa que Nubefact YA tenía este documento: el envío
        # anterior llegó y se perdió la respuesta. Emitir otro duplicaría el
        # comprobante ante SUNAT, así que se recupera el que ya existe.
        if exc.codigo == ERROR_YA_EXISTE:
            return _recuperar_existente(db, comprobante, tipo, serie, numero)

        # Se persiste el intento fallido: deja rastro de qué se envió y por qué
        # falló. El índice único excluye los ERROR, así que varios intentos
        # sobre la misma serie y número conviven sin chocar.
        comprobante.estado = EstadoComprobante.ERROR
        comprobante.mensaje_error = exc.mensaje
        comprobante.respuesta = exc.respuesta
        db.add(comprobante)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Nubefact rechazó el comprobante: {exc.mensaje}",
        ) from exc

    nubefact_facturacion.aplicar_respuesta(comprobante, respuesta)
    db.add(comprobante)
    db.commit()
    db.refresh(comprobante)
    return comprobante


def _recuperar_existente(
    db: Session,
    comprobante: ComprobanteElectronico,
    tipo: TipoComprobante,
    serie: str,
    numero: int,
) -> ComprobanteElectronico:
    """Rescata un comprobante que Nubefact ya tenía registrado.

    Ocurre cuando el envío llegó pero la respuesta se perdió (corte de red,
    timeout). Se consulta y se guarda con los datos reales en vez de emitir un
    duplicado ante SUNAT.
    """
    try:
        respuesta = nubefact_client.consultar(
            nubefact_catalogos.TIPO_COMPROBANTE[tipo.value], serie, numero
        )
    except nubefact_client.NubefactError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"El comprobante {serie}-{numero} ya existe en Nubefact pero no se "
                f"pudo recuperar: {exc.mensaje}"
            ),
        ) from exc

    nubefact_facturacion.aplicar_respuesta(comprobante, respuesta)
    db.add(comprobante)
    db.commit()
    db.refresh(comprobante)
    return comprobante


def _emitir_factpro(
    db: Session,
    venta: Venta,
    tipo: TipoComprobante,
    serie: str,
    actor_id: uuid.UUID | None,
) -> ComprobanteElectronico:
    """Emisión por FactPro. Se conserva para poder volver atrás sin desplegar."""
    payload = _construir_payload(venta, tipo, serie)
    numero_sim = _siguiente_numero(db, serie) if settings.factpro_simulado else 0
    datos_cliente = payload["cliente"]

    comprobante = _nuevo_comprobante(
        venta,
        tipo,
        serie,
        numero_sim,
        datos_cliente["cliente_tipo_documento"],
        datos_cliente["cliente_numero_documento"],
        datos_cliente["cliente_denominacion"],
        payload,
        actor_id,
    )

    try:
        respuesta = factpro_client.emitir(
            payload, numero_sim, TIPO_COMPROBANTE_SUNAT[tipo.value]
        )
    except factpro_client.FactProError as exc:
        comprobante.estado = EstadoComprobante.ERROR
        comprobante.mensaje_error = exc.mensaje
        comprobante.respuesta = exc.respuesta
        db.add(comprobante)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"FactPro rechazó el comprobante: {exc.mensaje}",
        ) from exc

    # Con SUNAT real, el número lo asigna FactPro: se lee de la respuesta.
    if not settings.factpro_simulado:
        numero_dev = respuesta.get("data", {}).get("numero", "")
        if "-" in numero_dev:
            comprobante.numero = int(numero_dev.rsplit("-", 1)[1])

    _aplicar_respuesta(comprobante, respuesta)
    db.add(comprobante)
    db.commit()
    db.refresh(comprobante)
    return comprobante


def anular_comprobante(
    db: Session, comprobante: ComprobanteElectronico, motivo: str, actor_id: uuid.UUID | None
) -> ComprobanteElectronico:
    if comprobante.estado is EstadoComprobante.ANULADO:
        raise HTTPException(status_code=409, detail="El comprobante ya está anulado")
    if comprobante.estado not in (EstadoComprobante.ACEPTADO, EstadoComprobante.REGISTRADO):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Un comprobante {comprobante.estado.value.lower()} no se puede anular",
        )
    if not motivo.strip():
        raise HTTPException(status_code=422, detail="La anulación requiere un motivo")

    if settings.usa_nubefact:
        try:
            respuesta = nubefact_client.anular(
                nubefact_catalogos.TIPO_COMPROBANTE[comprobante.tipo.value],
                comprobante.serie,
                comprobante.numero,
                motivo,
            )
        except nubefact_client.NubefactError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Nubefact no pudo anular el comprobante: {exc.mensaje}",
            ) from exc

        # SUNAT procesa las bajas en diferido: Nubefact devuelve un ticket y
        # `aceptada_por_sunat: false` hasta que responde. Marcar ANULADO ya
        # sería afirmar algo que SUNAT todavía no ha confirmado, así que el
        # estado sólo cambia cuando viene aceptada; si no, queda para que
        # `consultar_estado` lo refresque.
        comprobante.motivo_anulacion = motivo
        comprobante.respuesta = respuesta
        if respuesta.get("_simulado"):
            comprobante.es_simulado = True

        if respuesta.get("aceptada_por_sunat"):
            comprobante.estado = EstadoComprobante.ANULADO
            comprobante.fecha_anulacion = datetime.now(UTC)
            comprobante.descripcion_estado_sunat = str(
                respuesta.get("sunat_description") or "ANULADO"
            )[:300]
        else:
            comprobante.descripcion_estado_sunat = (
                f"Baja en trámite · ticket {respuesta.get('sunat_ticket_numero') or '—'}"
            )[:300]

        db.commit()
        db.refresh(comprobante)
        return comprobante

    try:
        respuesta = factpro_client.anular(comprobante.serie, comprobante.numero, motivo)
    except factpro_client.FactProError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"FactPro no pudo anular el comprobante: {exc.mensaje}",
        ) from exc

    comprobante.estado = EstadoComprobante.ANULADO
    comprobante.motivo_anulacion = motivo
    comprobante.fecha_anulacion = datetime.now(UTC)
    data = respuesta.get("data", {})
    comprobante.tipo_estado_sunat = data.get("tipo_estado", ESTADO_SUNAT_ANULADO)
    comprobante.descripcion_estado_sunat = data.get("descripcion_estado", "ANULADO")
    if respuesta.get("_simulado"):
        comprobante.es_simulado = True
    db.commit()
    db.refresh(comprobante)
    return comprobante


def _consultar_nubefact(
    db: Session, comprobante: ComprobanteElectronico
) -> ComprobanteElectronico:
    """Refresca contra Nubefact, que responde el estado y si está anulado."""
    tipo = nubefact_catalogos.TIPO_COMPROBANTE[comprobante.tipo.value]
    try:
        respuesta = nubefact_client.consultar(tipo, comprobante.serie, comprobante.numero)
    except nubefact_client.NubefactError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo consultar el estado: {exc.mensaje}",
        ) from exc

    anulado = bool(respuesta.get("anulado"))
    estado_previo = comprobante.estado

    nubefact_facturacion.aplicar_respuesta(comprobante, respuesta)

    # `aplicar_respuesta` deduce el estado de la aceptación por SUNAT, que sigue
    # siendo true en un comprobante dado de baja: la anulación manda.
    if anulado or estado_previo is EstadoComprobante.ANULADO:
        comprobante.estado = EstadoComprobante.ANULADO
        if comprobante.fecha_anulacion is None:
            comprobante.fecha_anulacion = datetime.now(UTC)

    db.commit()
    db.refresh(comprobante)
    return comprobante


def consultar_estado(
    db: Session, comprobante: ComprobanteElectronico
) -> ComprobanteElectronico:
    """Refresca el estado SUNAT: un REGISTRADO puede haber pasado a ACEPTADO."""
    if settings.usa_nubefact:
        return _consultar_nubefact(db, comprobante)

    try:
        respuesta = factpro_client.consultar(comprobante.serie, comprobante.numero)
    except factpro_client.FactProError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo consultar el estado: {exc.mensaje}",
        ) from exc

    data = respuesta.get("data", {})
    archivos = respuesta.get("archivos", {})
    if data.get("tipo_estado"):
        comprobante.tipo_estado_sunat = data["tipo_estado"]
        comprobante.descripcion_estado_sunat = data.get("descripcion_estado")
        # No se degrada un ACEPTADO/ANULADO por una consulta posterior.
        if comprobante.estado not in (EstadoComprobante.ACEPTADO, EstadoComprobante.ANULADO):
            comprobante.estado = _estado_desde_sunat(data["tipo_estado"])
    if archivos.get("cdr"):
        comprobante.cdr_url = archivos["cdr"]

    db.commit()
    db.refresh(comprobante)
    return comprobante
