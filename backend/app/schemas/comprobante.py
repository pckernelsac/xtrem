import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.comprobante import EstadoComprobante, TipoComprobante


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
    xml_url: str | None
    pdf_url: str | None
    cdr_url: str | None
    es_simulado: bool
    mensaje_error: str | None
    motivo_anulacion: str | None
    created_at: datetime


class ComprobanteDetail(ComprobanteOut):
    qr: str | None
    venta: VentaBrief | None
    usuario: UsuarioBrief | None
    payload_enviado: dict | None
    respuesta: dict | None


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
