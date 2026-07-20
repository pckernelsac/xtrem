import base64
import uuid
from datetime import datetime
from decimal import Decimal
from io import BytesIO

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.models.bicicleta import TipoBicicleta
from app.models.ficha import EstadoFicha, ServicioSolicitado

PREFIJO_PNG = "data:image/png;base64,"


class RepuestoIn(BaseModel):
    cantidad: Decimal = Field(default=Decimal("1"), gt=0, max_digits=10, decimal_places=2)
    descripcion: str = Field(min_length=1, max_length=200)
    marca: str | None = Field(default=None, max_length=80)
    precio_unitario: Decimal = Field(
        default=Decimal("0.00"), ge=0, max_digits=10, decimal_places=2
    )
    #: Enlaza la línea con el inventario. Si viene, la pieza se descuenta del
    #: stock; si no, es texto libre y no mueve el almacén.
    producto_id: uuid.UUID | None = None


class ProductoRepuesto(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sku: str
    nombre: str
    stock_actual: Decimal


class RepuestoOut(RepuestoIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    orden: int
    subtotal: Decimal
    producto: ProductoRepuesto | None = None


class ClienteFicha(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    tipo_documento: str
    numero_documento: str
    telefono: str | None
    email: str | None


class BicicletaFicha(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    marca: str
    modelo: str | None
    color: str | None
    numero_serie: str | None
    tipo: TipoBicicleta


class UsuarioFicha(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str


class FichaBase(BaseModel):
    canal_referencia: str | None = Field(default=None, max_length=120)
    servicios: list[ServicioSolicitado] = Field(default_factory=list)
    servicio_otro: str | None = Field(default=None, max_length=200)
    diagnostico_inicial: str | None = None
    trabajo_realizado: str | None = None
    tiempo_invertido_min: int | None = Field(default=None, ge=0, le=100_000)
    observaciones: str | None = None
    garantia_dias: int | None = Field(default=None, ge=0, le=3650)

    @field_validator("servicios")
    @classmethod
    def sin_duplicados(cls, v: list[ServicioSolicitado]) -> list[ServicioSolicitado]:
        # Se preserva el orden de la ficha impresa pero se descartan repetidos.
        vistos: list[ServicioSolicitado] = []
        for s in v:
            if s not in vistos:
                vistos.append(s)
        return vistos


class FichaCreate(FichaBase):
    cliente_id: uuid.UUID
    bicicleta_id: uuid.UUID
    fecha_recepcion: datetime | None = None
    tecnico_recepcion_id: uuid.UUID | None = None
    tecnico_responsable_id: uuid.UUID | None = None
    repuestos: list[RepuestoIn] = Field(default_factory=list)


class FichaUpdate(FichaBase):
    canal_referencia: str | None = None
    servicios: list[ServicioSolicitado] | None = None  # type: ignore[assignment]
    fecha_recepcion: datetime | None = None
    tecnico_recepcion_id: uuid.UUID | None = None
    tecnico_responsable_id: uuid.UUID | None = None
    tecnico_entrega_id: uuid.UUID | None = None
    #: Si viene, reemplaza la tabla completa de repuestos (no hace merge fila a fila).
    repuestos: list[RepuestoIn] | None = None


class CambioEstadoIn(BaseModel):
    estado: EstadoFicha
    comentario: str | None = Field(default=None, max_length=300)


class FirmaIn(BaseModel):
    """Firmas capturadas en canvas, como data URL PNG."""

    firma_cliente: str | None = None
    firma_cliente_dni: str | None = Field(default=None, max_length=15)
    firma_tecnico: str | None = None
    firma_tecnico_dni: str | None = Field(default=None, max_length=15)

    @field_validator("firma_cliente", "firma_tecnico")
    @classmethod
    def validar_data_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not v.startswith(PREFIJO_PNG):
            raise ValueError("La firma debe ser un data URL PNG en base64")
        # ~1 MB de base64 alcanza de sobra para un trazo de firma; el límite
        # evita que alguien suba una foto completa por este campo.
        if len(v) > 1_400_000:
            raise ValueError("La firma excede el tamaño máximo permitido")

        # Se decodifica de verdad: un PNG truncado pasaría el chequeo de
        # prefijo y luego rompería la generación del PDF, dejando la ficha
        # imposible de imprimir sin forma de corregirla desde la UI.
        try:
            crudo = base64.b64decode(v[len(PREFIJO_PNG) :], validate=True)
            with Image.open(BytesIO(crudo)) as img:
                img.verify()
        except Exception as exc:
            raise ValueError("La firma no es un PNG válido") from exc

        return v


class EstadoLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    estado_anterior: EstadoFicha | None
    estado_nuevo: EstadoFicha
    comentario: str | None
    created_at: datetime
    usuario: UsuarioFicha | None


class FichaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    numero: str
    estado: EstadoFicha
    cliente: ClienteFicha
    bicicleta: BicicletaFicha
    fecha_recepcion: datetime
    fecha_entrega: datetime | None
    tecnico_recepcion: UsuarioFicha | None
    tecnico_responsable: UsuarioFicha | None
    total_repuestos: Decimal
    esta_firmada: bool
    archivada: bool = False
    created_at: datetime


class FichaDetail(FichaOut):
    codigo_publico: str
    canal_referencia: str | None
    servicios: list[str]
    servicio_otro: str | None
    diagnostico_inicial: str | None
    trabajo_realizado: str | None
    tiempo_invertido_min: int | None
    observaciones: str | None
    garantia_dias: int | None
    tecnico_entrega: UsuarioFicha | None
    firma_cliente: str | None
    firma_cliente_dni: str | None
    firma_tecnico: str | None
    firma_tecnico_dni: str | None
    fecha_firma: datetime | None
    repuestos: list[RepuestoOut]
    historial_estados: list[EstadoLogOut]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def servicios_labels(self) -> list[str]:
        from app.models.ficha import ETIQUETAS_SERVICIO

        return [ETIQUETAS_SERVICIO.get(s, s) for s in self.servicios]


class FichaPage(BaseModel):
    items: list[FichaOut]
    total: int
    page: int
    page_size: int


class CompartirOut(BaseModel):
    """Enlaces para entregar la ficha al cliente."""

    url_pdf: str
    expira_en: datetime
    #: Teléfono normalizado a formato internacional, o None si no era usable.
    telefono: str | None
    whatsapp_url: str
    mensaje: str


class ConteoEstados(BaseModel):
    """Contadores para las tabs del listado: Todas (17) · Recibida (11) · ..."""

    todas: int
    por_estado: dict[str, int]
    #: Fuera del tablero; no entran en `todas` ni en `por_estado`.
    archivadas: int = 0
