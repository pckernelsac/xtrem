import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models.cliente import TipoDocumento

# Longitudes oficiales SUNAT/RENIEC. Se validan aquí para que el dato ya entre
# limpio, no recién al momento de facturar (Fase 6).
LONGITUD_DOCUMENTO: dict[TipoDocumento, tuple[int, int]] = {
    TipoDocumento.DNI: (8, 8),
    TipoDocumento.RUC: (11, 11),
    TipoDocumento.CE: (9, 12),
    TipoDocumento.PASAPORTE: (6, 12),
}


class ClienteBase(BaseModel):
    nombre: str = Field(min_length=2, max_length=160)
    tipo_documento: TipoDocumento = TipoDocumento.DNI
    numero_documento: str = Field(min_length=6, max_length=15)
    telefono: str | None = Field(default=None, max_length=20)
    email: EmailStr | None = None
    direccion: str | None = Field(default=None, max_length=240)
    notas: str | None = None
    is_active: bool = True

    @field_validator("numero_documento")
    @classmethod
    def solo_alfanumerico(cls, v: str) -> str:
        v = v.strip().upper()
        if not v.isalnum():
            raise ValueError("El número de documento sólo admite letras y números")
        return v

    @field_validator("nombre")
    @classmethod
    def limpiar_nombre(cls, v: str) -> str:
        return " ".join(v.split())

    @model_validator(mode="after")
    def validar_longitud_documento(self):
        minimo, maximo = LONGITUD_DOCUMENTO[self.tipo_documento]
        largo = len(self.numero_documento)
        if not minimo <= largo <= maximo:
            esperado = f"{minimo}" if minimo == maximo else f"entre {minimo} y {maximo}"
            raise ValueError(
                f"Un {self.tipo_documento.value} debe tener {esperado} caracteres "
                f"(recibido: {largo})"
            )
        if self.tipo_documento in (TipoDocumento.DNI, TipoDocumento.RUC):
            if not self.numero_documento.isdigit():
                raise ValueError(f"Un {self.tipo_documento.value} sólo admite dígitos")
        return self


class ClienteCreate(ClienteBase):
    pass


class ClienteUpdate(BaseModel):
    """Todos los campos opcionales. La validación cruzada de documento se hace
    en el endpoint, que conoce el estado actual del registro."""

    nombre: str | None = Field(default=None, min_length=2, max_length=160)
    tipo_documento: TipoDocumento | None = None
    numero_documento: str | None = Field(default=None, min_length=6, max_length=15)
    telefono: str | None = Field(default=None, max_length=20)
    email: EmailStr | None = None
    direccion: str | None = Field(default=None, max_length=240)
    notas: str | None = None
    is_active: bool | None = None


class BicicletaBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    marca: str
    modelo: str | None
    color: str | None
    numero_serie: str | None
    tipo: str
    is_active: bool


class ClienteOut(ClienteBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    bicicletas_count: int = 0


class ClienteDetail(ClienteOut):
    bicicletas: list[BicicletaBrief] = Field(default_factory=list)


class ClientePage(BaseModel):
    items: list[ClienteOut]
    total: int
    page: int
    page_size: int
