import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    LargeBinary,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class UnidadMedida(str, enum.Enum):
    UNIDAD = "UNIDAD"
    PAR = "PAR"
    JUEGO = "JUEGO"
    METRO = "METRO"
    LITRO = "LITRO"
    KIT = "KIT"


class TipoItem(str, enum.Enum):
    """Qué se está catalogando.

    Un servicio (mano de obra, calibración, lavado) se vende y se cotiza igual
    que un producto, pero no ocupa estante: no tiene existencias, no entra al
    kardex ni a la valorización del almacén.
    """

    PRODUCTO = "PRODUCTO"
    SERVICIO = "SERVICIO"


class TipoMovimiento(str, enum.Enum):
    ENTRADA = "ENTRADA"      # compra a proveedor, devolución de cliente
    SALIDA = "SALIDA"        # venta, consumo en taller, merma
    AJUSTE = "AJUSTE"        # corrección tras conteo físico


ETIQUETAS_MOVIMIENTO: dict[str, str] = {
    "ENTRADA": "Entrada",
    "SALIDA": "Salida",
    "AJUSTE": "Ajuste",
}


class Categoria(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "categorias"

    nombre: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    descripcion: Mapped[str | None] = mapped_column(String(240))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    productos: Mapped[list["Producto"]] = relationship(back_populates="categoria")


class Producto(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "productos"
    __table_args__ = (
        # El stock nunca debe quedar negativo: si una salida lo dejaría bajo
        # cero, es un error de captura, no un estado válido del almacén.
        CheckConstraint("stock_actual >= 0", name="ck_productos_stock_no_negativo"),
        CheckConstraint("stock_minimo >= 0", name="ck_productos_minimo_no_negativo"),
        Index("ix_productos_nombre", "nombre"),
    )

    tipo: Mapped[TipoItem] = mapped_column(
        Enum(TipoItem, name="tipo_item"),
        default=TipoItem.PRODUCTO,
        server_default=TipoItem.PRODUCTO.value,
        nullable=False,
        index=True,
    )

    sku: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(160))
    descripcion: Mapped[str | None] = mapped_column(Text)
    marca: Mapped[str | None] = mapped_column(String(80), index=True)

    categoria_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categorias.id", ondelete="SET NULL"), index=True
    )
    categoria: Mapped[Categoria | None] = relationship(back_populates="productos", lazy="joined")

    unidad: Mapped[UnidadMedida] = mapped_column(
        Enum(UnidadMedida, name="unidad_medida"), default=UnidadMedida.UNIDAD, nullable=False
    )

    # 3 decimales: hay insumos que se venden fraccionados (cable, aceite).
    stock_actual: Mapped[Decimal] = mapped_column(
        Numeric(12, 3), default=Decimal("0"), nullable=False
    )
    stock_minimo: Mapped[Decimal] = mapped_column(
        Numeric(12, 3), default=Decimal("0"), nullable=False
    )

    precio_compra: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), nullable=False
    )
    precio_venta: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), nullable=False
    )

    codigo_barras: Mapped[str | None] = mapped_column(String(64), index=True)
    ubicacion: Mapped[str | None] = mapped_column(String(60))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    #: Marca de tiempo de la última foto subida. Vive aquí, y no en
    #: `producto_fotos`, para que un listado sepa si hay foto sin cargar los
    #: bytes ni pagar un JOIN por fila.
    foto_actualizada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    movimientos: Mapped[list["MovimientoKardex"]] = relationship(
        back_populates="producto", cascade="all, delete-orphan"
    )

    @property
    def es_servicio(self) -> bool:
        return self.tipo is TipoItem.SERVICIO

    @property
    def foto_url(self) -> str | None:
        """Ruta pública de la foto, versionada por fecha.

        El `?v=` cambia al reemplazar la imagen; sin él, el navegador seguiría
        mostrando la anterior porque la respuesta se cachea de forma agresiva.
        """
        if self.foto_actualizada_at is None:
            return None
        return (
            f"/api/v1/inventario/productos/{self.id}/foto"
            f"?v={int(self.foto_actualizada_at.timestamp())}"
        )

    @property
    def bajo_minimo(self) -> bool:
        """El mínimo en 0 significa 'sin control de stock', no 'alertar siempre'."""
        if self.es_servicio:
            return False
        return self.stock_minimo > 0 and self.stock_actual <= self.stock_minimo

    @property
    def sin_stock(self) -> bool:
        # Un servicio nunca se agota: siempre se puede vender otra hora de taller.
        if self.es_servicio:
            return False
        return self.stock_actual <= 0

    @property
    def valor_stock(self) -> Decimal:
        """Valorizado a precio de compra, que es lo que costó tenerlo."""
        if self.es_servicio:
            return Decimal("0.00")
        return (self.stock_actual * self.precio_compra).quantize(Decimal("0.01"))

    @property
    def margen(self) -> Decimal | None:
        if self.precio_compra <= 0:
            return None
        bruto = (self.precio_venta - self.precio_compra) / self.precio_compra * 100
        return bruto.quantize(Decimal("0.1"))


class ProductoFoto(UUIDMixin, Base):
    """Imagen del ítem, una por producto o servicio.

    Los bytes viven en su propia tabla para que ningún SELECT del catálogo los
    arrastre sin querer: el listado del mostrador pide 24 ítems y traer las
    imágenes embebidas multiplicaría por mil el tamaño de la respuesta.

    Se guarda en la base y no en disco a propósito: el respaldo del sistema es
    el dump de Postgres, así que la foto viaja con el resto del catálogo y el
    despliegue no necesita un volumen aparte.
    """

    __tablename__ = "producto_fotos"

    producto_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("productos.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    contenido: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    mime: Mapped[str] = mapped_column(String(40), nullable=False)
    actualizado_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MovimientoKardex(UUIDMixin, Base):
    """Kardex: libro de movimientos del almacén.

    Es append-only y guarda el stock antes y después de cada movimiento. Así el
    saldo de `productos.stock_actual` siempre se puede auditar y reconstruir,
    incluso si alguien lo tocara por fuera del sistema.
    """

    __tablename__ = "movimientos_kardex"
    __table_args__ = (Index("ix_kardex_producto_fecha", "producto_id", "created_at"),)

    producto_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("productos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    producto: Mapped[Producto] = relationship(back_populates="movimientos", lazy="joined")

    tipo: Mapped[TipoMovimiento] = mapped_column(
        Enum(TipoMovimiento, name="tipo_movimiento"), nullable=False, index=True
    )
    #: Siempre positiva; el signo lo determina `tipo`.
    cantidad: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    stock_anterior: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    stock_posterior: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)

    costo_unitario: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    motivo: Mapped[str | None] = mapped_column(String(200))

    #: Documento que originó el movimiento (ficha, venta). Texto libre por
    #: ahora; en Fase 5 se enlazará con la venta correspondiente.
    referencia: Mapped[str | None] = mapped_column(String(80), index=True)

    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    usuario: Mapped["User | None"] = relationship(lazy="joined")  # noqa: F821

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
