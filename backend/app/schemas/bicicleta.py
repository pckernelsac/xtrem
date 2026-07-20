import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.bicicleta import TipoBicicleta


class BicicletaBase(BaseModel):
    marca: str = Field(min_length=1, max_length=80)
    modelo: str | None = Field(default=None, max_length=80)
    color: str | None = Field(default=None, max_length=40)
    numero_serie: str | None = Field(default=None, max_length=60)
    tipo: TipoBicicleta = TipoBicicleta.MTB
    rodado: str | None = Field(default=None, max_length=10)
    talla: str | None = Field(default=None, max_length=10)
    anio: int | None = Field(default=None, ge=1950)
    notas: str | None = None
    is_active: bool = True

    @field_validator("numero_serie")
    @classmethod
    def normalizar_serie(cls, v: str | None) -> str | None:
        """Las series se comparan en mayúsculas y sin espacios: evita duplicados
        que sólo difieren en formato al tipearlas en el mostrador."""
        if v is None:
            return None
        v = v.strip().upper().replace(" ", "")
        return v or None

    @field_validator("anio")
    @classmethod
    def anio_no_futuro(cls, v: int | None) -> int | None:
        if v is not None and v > date.today().year + 1:
            raise ValueError("El año no puede ser posterior al próximo año")
        return v


class BicicletaCreate(BicicletaBase):
    cliente_id: uuid.UUID


class BicicletaUpdate(BaseModel):
    marca: str | None = Field(default=None, min_length=1, max_length=80)
    modelo: str | None = Field(default=None, max_length=80)
    color: str | None = Field(default=None, max_length=40)
    numero_serie: str | None = Field(default=None, max_length=60)
    tipo: TipoBicicleta | None = None
    rodado: str | None = Field(default=None, max_length=10)
    talla: str | None = Field(default=None, max_length=10)
    anio: int | None = Field(default=None, ge=1950)
    notas: str | None = None
    is_active: bool | None = None
    # Permite reasignar la bici a otro cliente (venta de segunda mano, error de carga).
    cliente_id: uuid.UUID | None = None

    @field_validator("numero_serie")
    @classmethod
    def normalizar_serie(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip().upper().replace(" ", "") or None


class ClienteBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    tipo_documento: str
    numero_documento: str
    telefono: str | None


class BicicletaOut(BicicletaBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    cliente_id: uuid.UUID
    cliente: ClienteBrief
    descripcion: str
    created_at: datetime


class EventoHistorial(BaseModel):
    """Entrada del historial de la bicicleta.

    Hoy sólo registra el alta. Las fichas de mantenimiento (Fase 3) y las
    ventas de repuestos (Fase 5) se sumarán a este mismo feed.
    """

    fecha: datetime
    tipo: str
    titulo: str
    detalle: str | None = None
    #: Id del documento origen (ficha, venta) para enlazar desde el front.
    referencia_id: uuid.UUID | None = None


class BicicletaDetail(BicicletaOut):
    historial: list[EventoHistorial] = Field(default_factory=list)


class BicicletaPage(BaseModel):
    items: list[BicicletaOut]
    total: int
    page: int
    page_size: int
