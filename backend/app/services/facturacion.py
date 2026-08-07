"""Emisión de comprobantes electrónicos ante SUNAT, sin intermediarios.

El XML se genera y se firma aquí con el certificado de la empresa y se manda
directo a SUNAT. Ya no hay PSE de por medio, con tres consecuencias que marcan
el diseño de este módulo:

1. **El correlativo lo lleva el ERP.** Va por una secuencia de Postgres por
   serie, y el reintento reutiliza el número reservado para no dejar huecos.
2. **El archivo es nuestro.** El XML firmado y el CDR se guardan en la base, y
   la representación impresa se genera aquí. No dependemos de que nadie aloje
   nada: es justo lo que se perdió cuando el proveedor anterior dejó de
   responder.
3. **Que SUNAT no conteste no es un rechazo del documento.** Sólo se ve el día
   que SUNAT se cae, y es el caso que más daño hacía: el comprobante ya está
   emitido y firmado, así que queda `REGISTRADO` con el envío pendiente y se
   reintenta tal cual —mismo XML, mismo correlativo— hasta que haya respuesta.
   Antes se marcaba `ERROR`, quien atendía volvía a emitir, y la serie acababa
   con dos documentos para el mismo número.

Sin certificado configurado se opera en **modo simulación**: se construye y
persiste todo igual, pero no se llama a SUNAT y el comprobante queda marcado
como simulado.
"""

import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from sunat_cpe import (
    Certificado,
    Credenciales,
    ErrorDeFirma,
    ErrorSunat,
    Respuesta,
    enviar,
    generar_xml,
)

from app.core.config import settings
from app.core.fechas import hoy_local
from app.models.comprobante import (
    ComprobanteElectronico,
    EstadoComprobante,
    TipoComprobante,
)
from app.models.cliente import TipoDocumento
from app.models.venta import EstadoVenta, TipoVenta, Venta
from app.services import configuracion_sunat, sunat_adaptador

#: Estados en los que el comprobante sigue "vivo": bloquean re-emitir la venta.
ESTADOS_VIGENTES = {
    EstadoComprobante.PENDIENTE,
    EstadoComprobante.REGISTRADO,
    EstadoComprobante.ACEPTADO,
}

#: SUNAT permite boleta sin identificar al cliente sólo hasta este monto.
TOPE_BOLETA_SIN_DOCUMENTO = Decimal("700.00")

#: IGV general. El ERP sólo maneja operaciones gravadas.
IGV_TASA = Decimal("0.18")

#: Plazo de SUNAT para entregar una factura desde su emisión. Se usa sólo para
#: avisar: un comprobante que lleva más de esto en la cola ya no es una caída
#: pasajera y alguien tiene que mirarlo.
DIAS_PLAZO_ENVIO = 3

#: Los dos faults con los que SUNAT dice, literalmente, «el sistema no puede
#: responder su solicitud». Son los únicos códigos que se reintentan.
#:
#: La lista es blanca y corta a propósito. El resto de la familia `01xx` **no**
#: es indisponibilidad: hay credenciales (0102, 0111) y hay errores de formato
#: del propio envío (ZIP corrupto, nombre de archivo que no cuadra, XML fuera
#: del estándar). Reintentar cualquiera de ésos sería repetir lo mismo para
#: siempre, y además atascaría la cola detrás del documento imposible.
CODIGOS_SIN_SERVICIO = {
    "0100",  # El sistema no puede responder su solicitud (error no controlado)
    "0109",  # El sistema no puede responder su solicitud (error en la BD)
}

#: Mensaje del 401 de la librería. Es un fallo de credenciales, no una caída, y
#: llega sin código porque SUNAT lo devuelve como HTTP y no como SOAP Fault.
_MENSAJE_401 = "SUNAT rechazó las credenciales"


def sunat_no_disponible(exc: ErrorSunat) -> bool:
    """¿El envío se quedó sin respuesta, en vez de ser rechazado?

    Distinguirlo es lo único que separa «vuelve a intentarlo con este mismo
    número» de «este documento no vale, hay que rehacerlo»:

    * **Sin código** es transporte, y es el caso habitual de una caída: no se
      pudo contactar, contestó algo que no era XML —la página de mantenimiento—,
      un HTTP 5xx, o no devolvió el CDR. SUNAT nunca llegó a evaluar el
      documento. La única excepción es el 401, que tampoco trae código pero es
      de credenciales.
    * **Con código** SUNAT sí contestó, y salvo los dos faults de «sistema no
      disponible» lo que contestó es un veredicto sobre el envío. Insistir con
      el mismo contenido daría siempre el mismo resultado.
    """
    codigo = (exc.codigo or "").strip()
    if not codigo:
        return _MENSAJE_401 not in exc.mensaje
    return codigo in CODIGOS_SIN_SERVICIO


def desglosar_igv(total: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    """Reparte un total que YA incluye IGV en (base, igv, total).

    Los precios del ERP son de mostrador —impuesto incluido—, así que la base se
    obtiene dividiendo. El IGV se calcula por diferencia para que las tres
    cifras sumen exactas y no aparezca un céntimo de descuadre al totalizar.
    """
    total = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    base = (total / (Decimal("1") + IGV_TASA)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return base, total - base, total


def certificado_de_la_empresa(db: Session) -> Certificado:
    """Certificado listo para firmar, según la configuración vigente.

    Se resuelve en cada emisión y **no se cachea**: cambiar el certificado desde
    la interfaz debe surtir efecto sin reiniciar el contenedor, que es justo
    para lo que sirve poder cargarlo desde ahí.
    """
    return configuracion_sunat.certificado_cargado(configuracion_sunat.resolver(db))


def credenciales_sol(db: Session) -> Credenciales:
    return configuracion_sunat.credenciales(configuracion_sunat.resolver(db))


def en_simulacion(db: Session) -> bool:
    """Sin certificado o sin credenciales no se llama a SUNAT."""
    return not configuracion_sunat.resolver(db).completa


def _siguiente_numero(db: Session, serie: str) -> int:
    """Correlativo de la serie, desde una secuencia dedicada.

    Las secuencias de Postgres no retroceden con un ROLLBACK. Es deliberado: dos
    cajeros que emiten a la vez reciben números distintos sin bloquearse. A
    cambio, un envío fallido deja su número reservado, y por eso el reintento
    reutiliza el del comprobante en ERROR en vez de pedir otro.
    """
    seq = f"comprobante_{serie.lower()}_seq"
    db.execute(text(f"CREATE SEQUENCE IF NOT EXISTS {seq}"))
    return int(db.scalar(text(f"SELECT nextval('{seq}')")))


def _numero_reservado(db: Session, venta_id: uuid.UUID, serie: str) -> int | None:
    """Número que ya se reservó para esta venta en un intento fallido.

    Reutilizarlo evita huecos en la numeración, que SUNAT observa.
    """
    return db.scalar(
        select(ComprobanteElectronico.numero)
        .where(
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


def _serie_para(db: Session, tipo: TipoComprobante) -> str:
    config = configuracion_sunat.resolver(db)
    return (
        config.serie_factura if tipo is TipoComprobante.FACTURA else config.serie_boleta
    )


def comprobante_vigente_de(db: Session, venta_id: uuid.UUID) -> ComprobanteElectronico | None:
    return db.scalar(
        select(ComprobanteElectronico).where(
            ComprobanteElectronico.venta_id == venta_id,
            ComprobanteElectronico.estado.in_(ESTADOS_VIGENTES),
        )
    )


def _respuesta_simulada(numero: str) -> Respuesta:
    """Misma forma que la real, para que el resto del flujo no se entere."""
    return Respuesta(
        aceptado=True,
        codigo="0",
        descripcion=f"SIMULACIÓN: {numero} aceptada sin envío a SUNAT",
    )


def _aplicar(
    comprobante: ComprobanteElectronico,
    respuesta: Respuesta,
    xml: bytes,
    digest: str,
    simulado: bool,
) -> None:
    """Vuelca el resultado de SUNAT sobre el comprobante.

    El XML firmado y el CDR se guardan **siempre**, también si SUNAT rechaza:
    son la prueba de qué se envió y qué contestó.
    """
    comprobante.es_simulado = simulado
    comprobante.hash_cpe = digest
    comprobante.xml_firmado = xml.decode("utf-8", errors="replace")
    comprobante.tipo_estado_sunat = respuesta.codigo[:4] if respuesta.codigo else None
    comprobante.descripcion_estado_sunat = (respuesta.descripcion or "")[:300] or None

    if respuesta.cdr_xml:
        comprobante.cdr_xml = respuesta.cdr_xml.decode("utf-8", errors="replace")

    if respuesta.notas:
        # Las observaciones no impiden operar, pero conviene conservarlas.
        comprobante.mensaje_error = " | ".join(respuesta.notas)[:1000]

    comprobante.estado = (
        EstadoComprobante.ACEPTADO if respuesta.aceptado else EstadoComprobante.RECHAZADO
    )
    # Hubo respuesta: aceptado o rechazado, el documento ya no está en la cola.
    comprobante.envio_pendiente = False


def _encolar(comprobante: ComprobanteElectronico, exc: ErrorSunat) -> None:
    """Deja el comprobante emitido pero pendiente de entregar.

    El documento existe: tiene número, está firmado y el cliente se lleva su
    copia. Lo único que falta es que SUNAT lo reciba, y eso se reintenta con
    **este mismo XML y este mismo correlativo**. Emitir otro sería duplicar el
    número el día que SUNAT vuelva y acepte los dos.
    """
    comprobante.estado = EstadoComprobante.REGISTRADO
    comprobante.envio_pendiente = True
    comprobante.tipo_estado_sunat = (exc.codigo or "")[:4] or None
    comprobante.descripcion_estado_sunat = "Registrado: pendiente de envío a SUNAT"
    comprobante.mensaje_error = (
        f"SUNAT no está disponible; el comprobante se reenviará automáticamente. {exc.mensaje}"
    )[:1000]


def _fallar(comprobante: ComprobanteElectronico, exc: ErrorSunat) -> None:
    """El documento fue evaluado y no vale: queda en ERROR con su número.

    Se conserva la fila con el correlativo reservado para que el reintento lo
    reutilice y la serie no quede con un hueco, que SUNAT observa.
    """
    comprobante.estado = EstadoComprobante.ERROR
    comprobante.envio_pendiente = False
    comprobante.mensaje_error = exc.mensaje[:1000]
    comprobante.tipo_estado_sunat = (exc.codigo or "")[:4] or None
    # Se limpia porque puede venir de la cola, y ahí decía "pendiente de envío":
    # dejarlo haría que la etiqueta siguiera prometiendo un reenvío que ya no
    # va a ocurrir.
    comprobante.descripcion_estado_sunat = None


def emitir_desde_venta(
    db: Session, venta: Venta, actor_id: uuid.UUID | None
) -> ComprobanteElectronico:
    """Emite la boleta o factura de una venta confirmada."""
    if venta.tipo is not TipoVenta.VENTA:
        raise HTTPException(
            status_code=409, detail="Una cotización no se factura; conviértela primero"
        )
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
    serie = _serie_para(db, tipo)

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

    numero = _numero_reservado(db, venta.id, serie) or _siguiente_numero(db, serie)

    try:
        documento = sunat_adaptador.comprobante_de_venta(db, venta, tipo, serie, numero)
    except ValueError as exc:
        # La librería valida antes de enviar: un error aquí es un dato mal
        # formado, y decirlo así ahorra descifrar un código de SUNAT.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"El comprobante no se puede armar: {exc}",
        ) from exc

    base, igv, total = desglosar_igv(venta.total)
    receptor = documento.receptor
    comprobante = ComprobanteElectronico(
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
        cliente_tipo_documento=receptor.tipo_documento.value,
        cliente_numero_documento=receptor.numero_documento,
        cliente_denominacion=receptor.razon_social,
        emitido_en_produccion=configuracion_sunat.resolver(db).produccion,
        usuario_id=actor_id,
    )

    if en_simulacion(db):
        xml, digest = _xml_simulado(db, documento)
        _aplicar(comprobante, _respuesta_simulada(documento.numero), xml, digest, True)
        db.add(comprobante)
        db.commit()
        db.refresh(comprobante)
        return comprobante

    # Firmar y enviar van por separado —y no con `emitir()`, que hace las dos—
    # porque el XML firmado hay que conservarlo aunque el envío no salga: es lo
    # que se reintenta después, byte a byte, si SUNAT no estaba disponible.
    try:
        xml, digest = generar_xml(documento, certificado_de_la_empresa(db))
    except ErrorDeFirma as exc:
        # El certificado no sirve. El número ya se consumió de la secuencia, así
        # que se guarda el intento para que el reintento lo reutilice en vez de
        # dejar un hueco en la serie.
        _fallar(comprobante, ErrorSunat(f"No se pudo firmar el comprobante: {exc}"))
        db.add(comprobante)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo firmar el comprobante: {exc}",
        ) from exc

    comprobante.hash_cpe = digest
    comprobante.xml_firmado = xml.decode("utf-8", errors="replace")
    comprobante.intentos_envio = 1
    comprobante.ultimo_intento_envio = datetime.now(UTC)

    try:
        respuesta = enviar(credenciales_sol(db), documento.nombre_archivo, xml)
    except ErrorSunat as exc:
        if sunat_no_disponible(exc):
            # SUNAT no llegó a ver el documento. Queda emitido y en cola: el
            # cliente se lleva su comprobante y el reenvío lo entrega luego con
            # el mismo número. Devolver un error aquí es lo que llevaba a
            # reemitir y duplicar el correlativo.
            _encolar(comprobante, exc)
            db.add(comprobante)
            db.commit()
            db.refresh(comprobante)
            return comprobante

        _fallar(comprobante, exc)
        db.add(comprobante)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"SUNAT rechazó el comprobante: {exc.mensaje}",
        ) from exc

    _aplicar(comprobante, respuesta, xml, digest, False)
    db.add(comprobante)
    db.commit()
    db.refresh(comprobante)
    return comprobante


def _xml_simulado(db: Session, documento) -> tuple[bytes, str]:
    """XML firmado con el certificado si lo hay; si no, sin firmar.

    En simulación interesa que el XML exista y sea inspeccionable, no que esté
    firmado: puede no haber certificado en la máquina de desarrollo.
    """
    try:
        return generar_xml(documento, certificado_de_la_empresa(db))
    except HTTPException:
        from lxml import etree

        from sunat_cpe.ubl import construir

        return etree.tostring(construir(documento), xml_declaration=True, encoding="utf-8"), ""


# --------------------------------------------------------------------------
# Cola de reenvío
#
# Lo que SUNAT no recibió cuando estaba caído. No se vuelve a construir nada:
# se manda el mismo XML firmado que se guardó al emitir, con su mismo número.
# --------------------------------------------------------------------------
def _nombre_envio(comprobante: ComprobanteElectronico) -> str:
    """Nombre del archivo tal como viajó la primera vez.

    SUNAT contrasta el nombre del ZIP con lo que dice el XML, así que el
    reenvío tiene que repetirlo exactamente: `RUC-TIPO-SERIE-CORRELATIVO`, con
    el correlativo **sin rellenar de ceros**, que es como lo arma la librería.
    El de `nombre_sunat`, el de las descargas, lleva ocho dígitos y aquí no
    vale.
    """
    # Import local: `comprobante_pdf` arrastra WeasyPrint y este módulo lo
    # importa también el programador, que no genera PDF ninguno.
    from app.services.comprobante_pdf import TIPO_SUNAT, ruc_emisor

    tipo = TIPO_SUNAT.get(comprobante.tipo.value, "01")
    return f"{ruc_emisor(comprobante)}-{tipo}-{comprobante.serie}-{comprobante.numero}"


def pendientes_de_envio(db: Session) -> list[ComprobanteElectronico]:
    """Comprobantes emitidos que SUNAT todavía no ha recibido, los viejos antes."""
    return list(
        db.scalars(
            select(ComprobanteElectronico)
            .where(ComprobanteElectronico.envio_pendiente.is_(True))
            .order_by(
                ComprobanteElectronico.fecha_emision,
                ComprobanteElectronico.serie,
                ComprobanteElectronico.numero,
            )
        )
        .unique()
        .all()
    )


def reenviar(db: Session, comprobante: ComprobanteElectronico) -> ComprobanteElectronico:
    """Entrega a SUNAT un comprobante que se quedó en la cola.

    Reenviar el mismo documento es seguro: si SUNAT llegó a registrarlo en el
    intento anterior y lo que se perdió fue la respuesta, devuelve el CDR que ya
    tenía en vez de un duplicado. Por eso el reintento reutiliza el XML y no
    genera otro.
    """
    if not comprobante.envio_pendiente:
        return comprobante
    if not comprobante.xml_firmado:
        # No debería ocurrir: la cola sólo recibe comprobantes ya firmados. Si
        # pasa, sale de ella en vez de quedarse dando vueltas para siempre y
        # atascando a los que van detrás.
        _fallar(
            comprobante,
            ErrorSunat("El comprobante no guarda el XML firmado y no se puede reenviar"),
        )
        db.commit()
        db.refresh(comprobante)
        return comprobante

    comprobante.intentos_envio += 1
    comprobante.ultimo_intento_envio = datetime.now(UTC)
    xml = comprobante.xml_firmado.encode("utf-8")

    try:
        respuesta = enviar(credenciales_sol(db), _nombre_envio(comprobante), xml)
    except ErrorSunat as exc:
        if sunat_no_disponible(exc):
            # Sigue sin haber servicio: se queda en la cola tal cual.
            _encolar(comprobante, exc)
            db.commit()
            db.refresh(comprobante)
            return comprobante

        # Ahora sí hubo veredicto y es un rechazo: sale de la cola y su número
        # queda reservado para la corrección, igual que en la emisión.
        _fallar(comprobante, exc)
        db.commit()
        db.refresh(comprobante)
        return comprobante

    _aplicar(comprobante, respuesta, xml, comprobante.hash_cpe or "", False)
    db.commit()
    db.refresh(comprobante)
    return comprobante


def reenviar_pendientes(db: Session) -> list[ComprobanteElectronico]:
    """Vacía la cola, del más antiguo al más nuevo.

    **Se corta en cuanto SUNAT vuelve a no responder.** Si el servicio está
    caído lo está para todos, y seguir la lista sólo sirve para encadenar
    esperas de un minuto por comprobante hasta bloquear el ciclo entero.
    """
    procesados: list[ComprobanteElectronico] = []
    for comprobante in pendientes_de_envio(db):
        procesados.append(reenviar(db, comprobante))
        if comprobante.envio_pendiente:
            break
    return procesados


def dias_en_cola(db: Session) -> int:
    """Antigüedad del comprobante más viejo sin entregar. 0 si no hay ninguno."""
    fecha = db.scalar(
        select(func.min(ComprobanteElectronico.fecha_emision)).where(
            ComprobanteElectronico.envio_pendiente.is_(True)
        )
    )
    return (hoy_local() - fecha).days if fecha else 0


def anular_comprobante(
    db: Session, comprobante: ComprobanteElectronico, motivo: str, actor_id: uuid.UUID | None
) -> ComprobanteElectronico:
    """Deja el comprobante marcado para dar de baja.

    La baja ante SUNAT **no es inmediata ni individual**: las facturas se
    comunican en un lote (RA) y las boletas se anulan informándolas en el
    resumen diario con estado 3. Aquí sólo se marca la intención; el envío lo
    hace el proceso de lotes, que es quien conoce los plazos.
    """
    if comprobante.estado is EstadoComprobante.ANULADO:
        raise HTTPException(status_code=409, detail="El comprobante ya está anulado")
    if comprobante.envio_pendiente:
        # No se puede dar de baja lo que SUNAT todavía no tiene: la baja
        # llegaría antes que el documento y SUNAT la rechazaría. Hay que
        # esperar al reenvío, que es cuestión de minutos en cuanto vuelva.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "El comprobante aún no ha llegado a SUNAT: se está reenviando. "
                "Anúlalo en cuanto quede aceptado."
            ),
        )
    if comprobante.estado not in (EstadoComprobante.ACEPTADO, EstadoComprobante.REGISTRADO):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Un comprobante {comprobante.estado.value.lower()} no se puede anular",
        )
    if not motivo.strip():
        raise HTTPException(status_code=422, detail="La anulación requiere un motivo")

    comprobante.motivo_anulacion = motivo[:300]
    comprobante.fecha_anulacion = datetime.now(UTC)
    comprobante.baja_pendiente = True
    comprobante.descripcion_estado_sunat = "Baja pendiente de comunicar a SUNAT"[:300]
    db.commit()
    db.refresh(comprobante)
    return comprobante


def consultar_estado(
    db: Session, comprobante: ComprobanteElectronico
) -> ComprobanteElectronico:
    """Estado del comprobante.

    Emitiendo directo, el CDR llega en la misma respuesta del envío, así que no
    hay nada que volver a preguntar: el estado que hay guardado ya es el final.

    La excepción es un comprobante que se quedó en la cola porque SUNAT no
    respondió. Ahí «consultar» sólo puede significar una cosa —intentar
    entregarlo ahora— y eso es lo que hace, sin esperar al ciclo de fondo.
    """
    if comprobante.envio_pendiente:
        return reenviar(db, comprobante)
    return comprobante
