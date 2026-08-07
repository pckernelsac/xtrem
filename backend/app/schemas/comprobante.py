import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.comprobante import (
    EstadoComprobante,
    EstadoLote,
    TipoComprobante,
    TipoLote,
)


class EmitirIn(BaseModel):
    venta_id: uuid.UUID


class AnularComprobanteIn(BaseModel):
    motivo: str = Field(min_length=3, max_length=300)


class VentaBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    numero: str
    total: Decimal


class UsuarioBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str


class ComprobanteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: TipoComprobante
    estado: EstadoComprobante
    serie: str
    numero: int
    numero_completo: str
    fecha_emision: date
    moneda: str
    #: Congelados al emitir. Nulos sólo en comprobantes anteriores a ese cambio
    #: cuya venta ya no existe.
    base_imponible: Decimal | None = None
    igv: Decimal | None = None
    total: Decimal | None = None
    cliente_tipo_documento: str
    cliente_numero_documento: str
    cliente_denominacion: str
    tipo_estado_sunat: str | None
    descripcion_estado_sunat: str | None
    hash_cpe: str | None
    #: Código del enlace público (`/c/{codigo}`). Con emisión propia el PDF se
    #: genera al pedirlo, así que reemplaza a las antiguas `pdf_url`/`xml_url`/
    #: `cdr_url`, que apuntaban al servidor del proveedor y hoy están vacías.
    codigo_publico: str
    #: Qué archivos hay realmente, para no ofrecer descargas que darían 404.
    tiene_xml: bool
    tiene_cdr: bool
    es_simulado: bool
    #: Emitido, pero SUNAT no llegó a recibirlo (estaba caído). Se reenvía solo
    #: con el mismo número; la UI tiene que decirlo para que nadie lo reemita.
    envio_pendiente: bool
    intentos_envio: int
    mensaje_error: str | None
    motivo_anulacion: str | None
    created_at: datetime


class ComprobanteDetail(ComprobanteOut):
    qr: str | None
    venta: VentaBrief | None
    usuario: UsuarioBrief | None
    payload_enviado: dict | None
    respuesta: dict | None


class CompartirComprobanteOut(BaseModel):
    """Enlace armado para enviar el PDF del comprobante por WhatsApp."""

    url_pdf: str
    telefono: str | None
    whatsapp_url: str
    mensaje: str


class ComprobantePage(BaseModel):
    items: list[ComprobanteOut]
    total: int
    page: int
    page_size: int


class ConteoComprobantes(BaseModel):
    todas: int
    por_estado: dict[str, int]
    #: Advierte a la UI que estos comprobantes NO son válidos ante SUNAT.
    modo_simulacion: bool
    #: Emitidos y en cola porque SUNAT no respondió. No se filtra por tipo: si
    #: SUNAT está caído lo está para todos, y hay que verlo desde cualquier vista.
    sin_enviar: int


class LoteOut(BaseModel):
    """Un resumen diario o una comunicación de baja enviados a SUNAT."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: TipoLote
    estado: EstadoLote
    identificador: str
    fecha_referencia: date
    fecha_emision: date
    ticket: str | None
    codigo_sunat: str | None
    descripcion_sunat: str | None
    mensaje_error: str | None
    es_simulado: bool
    cantidad: int
    pendiente_de_cdr: bool
    created_at: datetime


class DiaPendienteOut(BaseModel):
    """Un día con boletas emitidas pero todavía sin declarar."""

    fecha: date
    boletas: int
    total: Decimal | None
    dias_transcurridos: int
    #: Pasado el plazo de SUNAT deja de ser un olvido y pasa a ser un problema.
    fuera_de_plazo: bool


class GenerarResumenIn(BaseModel):
    #: Día de las boletas que se declaran. Por defecto, ayer: la jornada de hoy
    #: sigue abierta y se informa mañana.
    fecha: date | None = None
