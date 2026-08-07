"""Resumen diario de boletas y comunicación de baja.

**Emitir una boleta no la declara.** SUNAT sólo la da por informada cuando llega
en un resumen diario, y hay plazo para mandarlo. Este módulo es, por tanto, tan
obligatorio como la emisión misma: sin él las boletas quedan en un limbo que se
convierte en incumplimiento a los pocos días.

El proceso es asíncrono y en dos tiempos, y por eso no puede resolverse dentro
de la petición que emite la boleta:

1. Se arma el lote con lo pendiente, se firma y se envía. SUNAT responde con un
   **ticket**, no con el CDR.
2. Más tarde se consulta ese ticket y llega el CDR.

Entre uno y otro puede pasar un rato, así que el ticket se guarda. Perderlo
significa no saber si lo enviado llegó a declararse.
"""

import uuid
from datetime import date, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sunat_cpe import (
    BoletaDelResumen,
    ComprobanteDeBaja,
    ComunicacionBaja,
    ErrorSunat,
    EstadoItem,
    ResumenDiario,
    TipoDocumento,
    TipoDocumentoIdentidad,
    consultar_ticket,
    emitir_lote,
)

from app.core.config import settings
from app.core.fechas import hoy_local
from app.models.comprobante import (
    ComprobanteElectronico,
    EstadoComprobante,
    EstadoLote,
    LoteSunat,
    TipoComprobante,
    TipoLote,
)
from app.services import configuracion_sunat, sunat_adaptador
from app.services.facturacion import certificado_de_la_empresa, credenciales_sol, en_simulacion

#: Plazo de SUNAT para comunicar el resumen. Se usa sólo para avisar: pasado
#: este margen, lo pendiente deja de ser un olvido y pasa a ser un problema.
DIAS_PLAZO_RESUMEN = 7

TIPO_DOC_RECEPTOR = {
    "1": TipoDocumentoIdentidad.DNI,
    "4": TipoDocumentoIdentidad.CARNET_EXTRANJERIA,
    "6": TipoDocumentoIdentidad.RUC,
    "7": TipoDocumentoIdentidad.PASAPORTE,
}


def boletas_sin_informar(db: Session, dia: date | None = None) -> list[ComprobanteElectronico]:
    """Boletas emitidas que todavía no han entrado en ningún resumen.

    Se excluyen las que fallaron y las que siguen en la cola de reenvío: sólo se
    declara lo que SUNAT ya tiene. Meter en el resumen una boleta que el
    servicio aún no ha recibido es declarar algo que podría acabar rechazado.
    """
    stmt = select(ComprobanteElectronico).where(
        ComprobanteElectronico.tipo == TipoComprobante.BOLETA,
        ComprobanteElectronico.lote_id.is_(None),
        ComprobanteElectronico.envio_pendiente.is_(False),
        ComprobanteElectronico.estado.in_(
            [EstadoComprobante.ACEPTADO, EstadoComprobante.REGISTRADO]
        ),
    )
    if dia is not None:
        stmt = stmt.where(ComprobanteElectronico.fecha_emision == dia)
    return list(
        db.scalars(stmt.order_by(ComprobanteElectronico.fecha_emision, ComprobanteElectronico.numero))
        .unique()
        .all()
    )


def dias_pendientes(db: Session) -> list[dict]:
    """Días con boletas sin declarar, con su antigüedad.

    Es lo que alimenta el aviso: un día que se pasa de plazo no se recupera
    solo, y cuanto antes se vea, mejor.
    """
    filas = db.execute(
        select(
            ComprobanteElectronico.fecha_emision,
            func.count(ComprobanteElectronico.id),
            func.sum(ComprobanteElectronico.total),
        )
        .where(
            ComprobanteElectronico.tipo == TipoComprobante.BOLETA,
            ComprobanteElectronico.lote_id.is_(None),
            ComprobanteElectronico.envio_pendiente.is_(False),
            ComprobanteElectronico.estado.in_(
                [EstadoComprobante.ACEPTADO, EstadoComprobante.REGISTRADO]
            ),
        )
        .group_by(ComprobanteElectronico.fecha_emision)
        .order_by(ComprobanteElectronico.fecha_emision)
    ).all()

    hoy = hoy_local()
    return [
        {
            "fecha": fecha,
            "boletas": cantidad,
            "total": total,
            "dias_transcurridos": (hoy - fecha).days,
            "fuera_de_plazo": (hoy - fecha).days > DIAS_PLAZO_RESUMEN,
        }
        for fecha, cantidad, total in filas
    ]


def facturas_por_dar_de_baja(db: Session) -> list[ComprobanteElectronico]:
    """Facturas anuladas en el ERP que aún no se comunicaron a SUNAT."""
    return list(
        db.scalars(
            select(ComprobanteElectronico).where(
                ComprobanteElectronico.baja_pendiente.is_(True),
                ComprobanteElectronico.lote_id.is_(None),
                ComprobanteElectronico.tipo != TipoComprobante.BOLETA,
            )
        )
        .unique()
        .all()
    )


def _siguiente_correlativo(db: Session, tipo: TipoLote, dia: date) -> int:
    """Correlativo del lote dentro del día. SUNAT los numera por jornada."""
    usados = (
        db.scalar(
            select(func.count(LoteSunat.id)).where(
                LoteSunat.tipo == tipo, LoteSunat.fecha_emision == dia
            )
        )
        or 0
    )
    return usados + 1


def _linea_de_boleta(comprobante: ComprobanteElectronico) -> BoletaDelResumen:
    """Traduce una boleta ya emitida a su línea del resumen.

    Una boleta anulada se informa con estado 3 en vez de con un RA: es la vía
    que SUNAT admite para ellas.
    """
    return BoletaDelResumen(
        tipo_documento=TipoDocumento.BOLETA,
        serie_numero=comprobante.numero_completo,
        estado=EstadoItem.ANULAR if comprobante.baja_pendiente else EstadoItem.ADICIONAR,
        receptor_tipo_documento=TIPO_DOC_RECEPTOR.get(comprobante.cliente_tipo_documento),
        receptor_numero_documento=comprobante.cliente_numero_documento,
        total=comprobante.total or 0,
        gravado=comprobante.base_imponible or 0,
        igv=comprobante.igv or 0,
    )


def _enviar(
    db: Session,
    lote: LoteSunat,
    documento: ResumenDiario | ComunicacionBaja,
    comprobantes: list[ComprobanteElectronico],
) -> LoteSunat:
    """Firma y manda el lote, y deja atado lo que se informó.

    Los comprobantes se enlazan **antes** de enviar y sólo se desenlazan si el
    envío falla: si se hiciera al revés y el proceso muriera entre el envío y el
    commit, esas boletas volverían a entrar en el siguiente resumen y SUNAT las
    vería duplicadas.
    """
    for comprobante in comprobantes:
        comprobante.lote_id = lote.id

    if en_simulacion(db):
        lote.estado = EstadoLote.ACEPTADO
        lote.es_simulado = True
        lote.codigo_sunat = "0"
        lote.descripcion_sunat = "SIMULACIÓN: lote aceptado sin envío a SUNAT"
        db.commit()
        db.refresh(lote)
        return lote

    try:
        ticket, xml = emitir_lote(documento, certificado_de_la_empresa(db), credenciales_sol(db))
    except ErrorSunat as exc:
        lote.estado = EstadoLote.ERROR
        lote.mensaje_error = exc.mensaje[:1000]
        lote.codigo_sunat = (exc.codigo or "")[:10] or None
        # El lote falló: lo informado sigue pendiente y debe reintentarse.
        for comprobante in comprobantes:
            comprobante.lote_id = None
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"SUNAT rechazó el envío: {exc.mensaje}",
        ) from exc

    lote.ticket = ticket
    lote.estado = EstadoLote.ENVIADO
    lote.xml_firmado = xml.decode("utf-8", errors="replace")
    lote.descripcion_sunat = "Enviado; pendiente de recoger el CDR"
    db.commit()
    db.refresh(lote)
    return lote


def generar_resumen(
    db: Session, dia: date, actor_id: uuid.UUID | None
) -> LoteSunat:
    """Arma y envía el resumen diario de las boletas de `dia`."""
    boletas = boletas_sin_informar(db, dia)
    if not boletas:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No hay boletas sin declarar del {dia:%d/%m/%Y}",
        )

    hoy = hoy_local()
    if dia > hoy:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No se puede declarar un día que todavía no ha ocurrido",
        )

    correlativo = _siguiente_correlativo(db, TipoLote.RESUMEN, hoy)
    documento = ResumenDiario(
        emisor=sunat_adaptador.emisor_configurado(db),
        fecha_referencia=dia,
        fecha_emision=hoy,
        correlativo=correlativo,
        boletas=[_linea_de_boleta(b) for b in boletas],
    )

    lote = LoteSunat(
        tipo=TipoLote.RESUMEN,
        estado=EstadoLote.PENDIENTE,
        identificador=documento.identificador,
        fecha_referencia=dia,
        fecha_emision=hoy,
        correlativo=correlativo,
        emitido_en_produccion=configuracion_sunat.resolver(db).produccion,
        usuario_id=actor_id,
    )
    db.add(lote)
    db.flush()

    return _enviar(db, lote, documento, boletas)


def generar_baja(db: Session, actor_id: uuid.UUID | None) -> LoteSunat:
    """Comunica la baja de las facturas anuladas que siguen sin informar."""
    facturas = facturas_por_dar_de_baja(db)
    if not facturas:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No hay facturas anuladas pendientes de comunicar",
        )

    hoy = hoy_local()
    # SUNAT agrupa la baja por el día de emisión de lo que se anula.
    dia = min(f.fecha_emision for f in facturas)
    correlativo = _siguiente_correlativo(db, TipoLote.BAJA, hoy)

    documento = ComunicacionBaja(
        emisor=sunat_adaptador.emisor_configurado(db),
        fecha_referencia=dia,
        fecha_emision=hoy,
        correlativo=correlativo,
        documentos=[
            ComprobanteDeBaja(
                tipo_documento=(
                    TipoDocumento.FACTURA
                    if f.tipo is TipoComprobante.FACTURA
                    else TipoDocumento.NOTA_CREDITO
                ),
                serie=f.serie,
                correlativo=f.numero,
                motivo=(f.motivo_anulacion or "Error en el documento")[:100],
            )
            for f in facturas
        ],
    )

    lote = LoteSunat(
        tipo=TipoLote.BAJA,
        estado=EstadoLote.PENDIENTE,
        identificador=documento.identificador,
        fecha_referencia=dia,
        fecha_emision=hoy,
        correlativo=correlativo,
        emitido_en_produccion=configuracion_sunat.resolver(db).produccion,
        usuario_id=actor_id,
    )
    db.add(lote)
    db.flush()

    return _enviar(db, lote, documento, facturas)


def recoger_cdr(db: Session, lote: LoteSunat) -> LoteSunat:
    """Consulta el ticket y guarda el CDR si SUNAT ya terminó.

    Que siga en proceso no es un error: se devuelve el lote sin cambios y se
    vuelve a intentar más tarde.
    """
    if not lote.pendiente_de_cdr:
        return lote

    try:
        respuesta = consultar_ticket(credenciales_sol(db), lote.ticket)
    except ErrorSunat as exc:
        # No se marca el lote como fallido: el envío sí llegó y el ticket sigue
        # siendo válido. Lo que falló es la consulta, y se reintenta.
        lote.mensaje_error = f"No se pudo consultar el ticket: {exc.mensaje}"[:1000]
        db.commit()
        return lote

    if respuesta is None:
        return lote

    lote.codigo_sunat = (respuesta.codigo or "")[:10] or None
    lote.descripcion_sunat = (respuesta.descripcion or "")[:500] or None
    lote.estado = EstadoLote.ACEPTADO if respuesta.aceptado else EstadoLote.RECHAZADO
    if respuesta.cdr_xml:
        lote.cdr_xml = respuesta.cdr_xml.decode("utf-8", errors="replace")
    if respuesta.notas:
        lote.mensaje_error = " | ".join(respuesta.notas)[:1000]

    if not respuesta.aceptado:
        # Rechazado: lo informado vuelve a estar pendiente, o quedaría sin
        # declarar creyendo que ya se hizo.
        for comprobante in lote.comprobantes:
            comprobante.lote_id = None
    else:
        # Aceptado: las boletas anuladas quedan anuladas también ante SUNAT.
        for comprobante in lote.comprobantes:
            if comprobante.baja_pendiente:
                comprobante.estado = EstadoComprobante.ANULADO
                comprobante.baja_pendiente = False

    db.commit()
    db.refresh(lote)
    return lote


def recoger_pendientes(db: Session) -> list[LoteSunat]:
    """Recorre los lotes enviados sin CDR y trata de cerrarlos.

    Pensado para un proceso programado: los tickets no se resuelven solos y
    nadie va a estar pulsando un botón cada mañana.
    """
    lotes = list(
        db.scalars(
            select(LoteSunat).where(
                LoteSunat.estado == EstadoLote.ENVIADO,
                LoteSunat.ticket.is_not(None),
            )
        )
        .unique()
        .all()
    )
    return [recoger_cdr(db, lote) for lote in lotes]


def resumen_de_ayer_pendiente(db: Session) -> bool:
    """¿Quedan boletas de días anteriores sin declarar?

    Las de hoy no cuentan: la jornada sigue abierta y se declaran mañana.
    """
    ayer = hoy_local() - timedelta(days=1)
    return bool(
        db.scalar(
            select(func.count(ComprobanteElectronico.id)).where(
                ComprobanteElectronico.tipo == TipoComprobante.BOLETA,
                ComprobanteElectronico.lote_id.is_(None),
                ComprobanteElectronico.envio_pendiente.is_(False),
                ComprobanteElectronico.fecha_emision <= ayer,
                ComprobanteElectronico.estado.in_(
                    [EstadoComprobante.ACEPTADO, EstadoComprobante.REGISTRADO]
                ),
            )
        )
    )
