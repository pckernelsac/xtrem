import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.caja import EstadoCaja, MetodoPago, TipoMovimientoCaja


class AbrirCajaIn(BaseModel):
    monto_inicial: Decimal = Field(default=Decimal("0"), ge=0, max_digits=10, decimal_places=2)
    observaciones: str | None = None


class CerrarCajaIn(BaseModel):
    #: Lo que el cajero contó en el cajón, no lo que el sistema calcula.
    monto_declarado: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    observaciones: str | None = None


class MovimientoCajaIn(BaseModel):
    """Ingresos y egresos manuales: retiro a banco, pago a proveedor, propina."""

    tipo: TipoMovimientoCaja
    metodo: MetodoPago = MetodoPago.EFECTIVO
    monto: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    concepto: str = Field(min_length=2, max_length=200)


class UsuarioBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str


class MovimientoCajaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: TipoMovimientoCaja
    metodo: MetodoPago
    monto: Decimal
    concepto: str
    referencia: str | None
    usuario: UsuarioBrief | None
    created_at: datetime


class TotalMetodo(BaseModel):
    ingresos: Decimal
    egresos: Decimal


class SesionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    numero: str
    estado: EstadoCaja
    monto_inicial: Decimal
    fecha_apertura: datetime
    fecha_cierre: datetime | None
    usuario_apertura: UsuarioBrief | None
    usuario_cierre: UsuarioBrief | None
    monto_declarado: Decimal | None
    monto_esperado: Decimal | None
    diferencia: Decimal | None
    observaciones: str | None


class SesionPage(BaseModel):
    items: list[SesionOut]
    total: int
    page: int
    page_size: int


class ArqueoOut(SesionOut):
    """Sesión con el detalle que necesita el cierre."""

    #: Efectivo que debería haber ahora mismo en el cajón.
    efectivo_esperado: Decimal
    totales: dict[str, TotalMetodo]
    cantidad_ventas: int
    movimientos: list[MovimientoCajaOut]
