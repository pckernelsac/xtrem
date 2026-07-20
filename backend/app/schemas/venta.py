import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.caja import MetodoPago
from app.models.inventario import TipoItem
from app.models.venta import EstadoVenta, TipoVenta


class ItemIn(BaseModel):
    producto_id: uuid.UUID | None = None
    descripcion: str = Field(min_length=1, max_length=200)
    cantidad: Decimal = Field(default=Decimal("1"), gt=0, max_digits=12, decimal_places=3)
    precio_unitario: Decimal = Field(default=Decimal("0"), ge=0, max_digits=10, decimal_places=2)
    descuento: Decimal = Field(default=Decimal("0"), ge=0, max_digits=10, decimal_places=2)

    @model_validator(mode="after")
    def descuento_no_supera_linea(self):
        if self.descuento > self.cantidad * self.precio_unitario:
            raise ValueError("El descuento de la línea supera su importe")
        return self


class PagoIn(BaseModel):
    metodo: MetodoPago
    monto: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    referencia: str | None = Field(
        default=None, max_length=80, description="N° de operación Yape/Plin o voucher"
    )


class VentaCreate(BaseModel):
    tipo: TipoVenta = TipoVenta.VENTA
    cliente_id: uuid.UUID | None = None
    ficha_id: uuid.UUID | None = None
    descuento: Decimal = Field(default=Decimal("0"), ge=0, max_digits=10, decimal_places=2)
    notas: str | None = None
    valido_hasta: date | None = None
    items: list[ItemIn] = Field(min_length=1)
    #: Obligatorio para una VENTA; una COTIZACION no se cobra.
    pagos: list[PagoIn] = Field(default_factory=list)


class VentaUpdate(BaseModel):
    """Sólo aplica a cotizaciones pendientes: una venta confirmada no se edita."""

    cliente_id: uuid.UUID | None = None
    descuento: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    notas: str | None = None
    valido_hasta: date | None = None
    items: list[ItemIn] | None = None


class ConvertirIn(BaseModel):
    """Convierte una cotización aceptada en venta cobrada."""

    pagos: list[PagoIn] = Field(min_length=1)


class AnularIn(BaseModel):
    motivo: str | None = Field(default=None, max_length=300)


class ProductoBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sku: str
    nombre: str
    #: El mostrador lo usa para no alertar por "stock 0" en un servicio.
    tipo: TipoItem
    stock_actual: Decimal


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    orden: int
    producto: ProductoBrief | None
    descripcion: str
    cantidad: Decimal
    precio_unitario: Decimal
    descuento: Decimal
    subtotal: Decimal


class PagoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    metodo: MetodoPago
    monto: Decimal
    referencia: str | None
    created_at: datetime


class ClienteBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    tipo_documento: str
    numero_documento: str


class UsuarioBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str


class VentaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    numero: str
    tipo: TipoVenta
    estado: EstadoVenta
    cliente: ClienteBrief | None
    usuario: UsuarioBrief | None
    subtotal: Decimal
    descuento: Decimal
    total: Decimal
    total_pagado: Decimal
    saldo: Decimal
    esta_pagada: bool
    vencida: bool
    valido_hasta: date | None
    archivada: bool = False
    created_at: datetime


class VentaDetail(VentaOut):
    ficha_id: uuid.UUID | None
    sesion_caja_id: uuid.UUID | None
    notas: str | None
    fecha_anulacion: datetime | None
    motivo_anulacion: str | None
    items: list[ItemOut]
    pagos: list[PagoOut]


class VentaPage(BaseModel):
    items: list[VentaOut]
    total: int
    page: int
    page_size: int


class ConteoVentas(BaseModel):
    todas: int
    por_estado: dict[str, int]
    #: Fuera del listado de trabajo; no entran en `todas` ni en `por_estado`.
    archivadas: int = 0
