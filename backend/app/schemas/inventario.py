import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.inventario import TipoItem, TipoMovimiento, UnidadMedida


# --------------------------------------------------------------- Categorías
class CategoriaBase(BaseModel):
    nombre: str = Field(min_length=2, max_length=80)
    descripcion: str | None = Field(default=None, max_length=240)
    is_active: bool = True


class CategoriaCreate(CategoriaBase):
    pass


class CategoriaUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=80)
    descripcion: str | None = Field(default=None, max_length=240)
    is_active: bool | None = None


class CategoriaOut(CategoriaBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    productos_count: int = 0


# --------------------------------------------------------------- Productos
class ProductoBase(BaseModel):
    tipo: TipoItem = TipoItem.PRODUCTO
    sku: str = Field(min_length=1, max_length=40)
    nombre: str = Field(min_length=2, max_length=160)
    descripcion: str | None = None
    marca: str | None = Field(default=None, max_length=80)
    categoria_id: uuid.UUID | None = None
    unidad: UnidadMedida = UnidadMedida.UNIDAD
    stock_minimo: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=3)
    precio_compra: Decimal = Field(default=Decimal("0"), ge=0, max_digits=10, decimal_places=2)
    precio_venta: Decimal = Field(default=Decimal("0"), ge=0, max_digits=10, decimal_places=2)
    codigo_barras: str | None = Field(default=None, max_length=64)
    ubicacion: str | None = Field(default=None, max_length=60)
    is_active: bool = True

    @field_validator("sku")
    @classmethod
    def normalizar_sku(cls, v: str) -> str:
        """En mayúsculas y sin espacios: el mismo SKU tipeado distinto en el
        mostrador debe chocar contra el índice único, no crear un duplicado."""
        return v.strip().upper().replace(" ", "")

    @field_validator("codigo_barras")
    @classmethod
    def limpiar_barras(cls, v: str | None) -> str | None:
        return (v.strip() or None) if v else None


class ProductoCreate(ProductoBase):
    #: Stock con el que nace el producto. Genera su primer asiento de kardex.
    stock_inicial: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=3)

    @model_validator(mode="after")
    def servicio_sin_stock(self) -> "ProductoCreate":
        """Un servicio no tiene existencias.

        Se normaliza en silencio en vez de rechazar: el formulario oculta esos
        campos y lo que llegue con valores viejos es ruido, no una intención.
        """
        if self.tipo is TipoItem.SERVICIO:
            self.stock_inicial = Decimal("0")
            self.stock_minimo = Decimal("0")
        return self


class ProductoUpdate(BaseModel):
    """El stock NO se toca por aquí: se mueve con /movimientos, que deja kardex."""

    tipo: TipoItem | None = None
    sku: str | None = Field(default=None, min_length=1, max_length=40)
    nombre: str | None = Field(default=None, min_length=2, max_length=160)
    descripcion: str | None = None
    marca: str | None = Field(default=None, max_length=80)
    categoria_id: uuid.UUID | None = None
    unidad: UnidadMedida | None = None
    stock_minimo: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=3)
    precio_compra: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    precio_venta: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    codigo_barras: str | None = Field(default=None, max_length=64)
    ubicacion: str | None = Field(default=None, max_length=60)
    is_active: bool | None = None

    @field_validator("sku")
    @classmethod
    def normalizar_sku(cls, v: str | None) -> str | None:
        return v.strip().upper().replace(" ", "") if v else v


class CategoriaBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str


class ProductoOut(ProductoBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    categoria: CategoriaBrief | None
    #: Ruta relativa de la imagen, o None si el ítem no tiene foto.
    foto_url: str | None = None
    stock_actual: Decimal
    bajo_minimo: bool
    sin_stock: bool
    valor_stock: Decimal
    margen: Decimal | None
    created_at: datetime


class ProductoPage(BaseModel):
    items: list[ProductoOut]
    total: int
    page: int
    page_size: int


# --------------------------------------------------------------- Kardex
class MovimientoCreate(BaseModel):
    tipo: TipoMovimiento
    cantidad: Decimal = Field(ge=0, max_digits=12, decimal_places=3)
    costo_unitario: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    motivo: str | None = Field(default=None, max_length=200)
    referencia: str | None = Field(default=None, max_length=80)


class UsuarioBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str


class ProductoBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sku: str
    nombre: str
    unidad: UnidadMedida


class MovimientoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    producto: ProductoBrief
    tipo: TipoMovimiento
    cantidad: Decimal
    stock_anterior: Decimal
    stock_posterior: Decimal
    costo_unitario: Decimal | None
    motivo: str | None
    referencia: str | None
    usuario: UsuarioBrief | None
    created_at: datetime


class MovimientoPage(BaseModel):
    items: list[MovimientoOut]
    total: int
    page: int
    page_size: int


# --------------------------------------------------------------- Resumen
class ResumenInventario(BaseModel):
    productos_activos: int
    servicios_activos: int = 0
    #: Productos y servicios dados de baja; siguen citados por sus documentos.
    archivados: int = 0
    bajo_minimo: int
    sin_stock: int
    valor_total: Decimal


# --------------------------------------------------------------- Importación
class FilaImportacion(BaseModel):
    fila: int
    sku: str | None = None
    accion: str  # creado | actualizado | error | omitido
    detalle: str | None = None


class ResultadoImportacion(BaseModel):
    """Reporte de la importación. En modo prueba nada se escribe en la BD."""

    modo_prueba: bool
    total_filas: int
    creados: int
    actualizados: int
    errores: int
    filas: list[FilaImportacion]
