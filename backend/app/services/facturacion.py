"""Emisión de comprobantes electrónicos ante SUNAT, sin intermediarios.

El XML se genera y se firma aquí con el certificado de la empresa y se manda
directo a SUNAT. Ya no hay PSE de por medio, con dos consecuencias que marcan el
diseño de este módulo:

1. **El correlativo lo lleva el ERP.** Va por una secuencia de Postgres por
   serie, y el reintento reutiliza el número reservado para no dejar huecos.
2. **El archivo es nuestro.** El XML firmado y el CDR se guardan en la base, y
   la representación impresa se genera aquí. No dependemos de que nadie aloje
   nada: es justo lo que se perdió cuando el proveedor anterior dejó de
   responder.

Sin certificado configurado se opera en **modo simulación**: se construye y
persiste todo igual, pero no se llama a SUNAT y el comprobante queda marcado
como simulado.
"""

import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from sunat_cpe import (
    Certificado,
    Credenciales,
    ErrorDeFirma,
    ErrorSunat,
    Respuesta,
    emitir,
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
from app.services import sunat_adaptador

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


@lru_cache(maxsize=1)
def certificado_de_la_empresa() -> Certificado:
    """Carga el certificado una vez y lo deja en memoria.

    Se cachea porque abrir el PKCS#12 implica descifrarlo, y eso ocurriría en
    cada emisión. El proceso se reinicia al renovar el certificado.
    """
    ruta = Path(settings.CERTIFICADO_RUTA)
    if not ruta.is_file():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"No se encuentra el certificado digital en {ruta}. Móntalo en el "
                "contenedor y define CERTIFICADO_CLAVE."
            ),
        )
    try:
        return Certificado.desde_pfx(ruta.read_bytes(), settings.CERTIFICADO_CLAVE)
    except ErrorDeFirma as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"El certificado digital no se pudo abrir: {exc}",
        ) from exc


def credenciales_sol() -> Credenciales:
    return Credenciales(
        ruc=settings.EMISOR_RUC,
        usuario_sol=settings.SOL_USUARIO,
        clave_sol=settings.SOL_CLAVE,
        produccion=settings.SUNAT_PRODUCCION,
    )


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


def _serie_para(tipo: TipoComprobante) -> str:
    return (
        settings.SERIE_FACTURA
        if tipo is TipoComprobante.FACTURA
        else settings.SERIE_BOLETA
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
    serie = _serie_para(tipo)

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
        documento = sunat_adaptador.comprobante_de_venta(venta, tipo, serie, numero)
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
        usuario_id=actor_id,
    )

    if settings.facturacion_simulada:
        xml, digest = _xml_simulado(documento)
        _aplicar(comprobante, _respuesta_simulada(documento.numero), xml, digest, True)
        db.add(comprobante)
        db.commit()
        db.refresh(comprobante)
        return comprobante

    try:
        respuesta, xml, digest = emitir(
            documento, certificado_de_la_empresa(), credenciales_sol()
        )
    except ErrorSunat as exc:
        # Se persiste el intento fallido con su número reservado, para que el
        # reintento lo reutilice y no deje un hueco en la serie.
        comprobante.estado = EstadoComprobante.ERROR
        comprobante.mensaje_error = exc.mensaje[:1000]
        comprobante.tipo_estado_sunat = (exc.codigo or "")[:4] or None
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


def _xml_simulado(documento) -> tuple[bytes, str]:
    """XML firmado con el certificado si lo hay; si no, sin firmar.

    En simulación interesa que el XML exista y sea inspeccionable, no que esté
    firmado: puede no haber certificado en la máquina de desarrollo.
    """
    try:
        return generar_xml(documento, certificado_de_la_empresa())
    except HTTPException:
        from lxml import etree

        from sunat_cpe.ubl import construir

        return etree.tostring(construir(documento), xml_declaration=True, encoding="utf-8"), ""


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
    Se conserva el endpoint porque la interfaz lo ofrece y porque los lotes sí
    se resuelven en diferido.
    """
    return comprobante
