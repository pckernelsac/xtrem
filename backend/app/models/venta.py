import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.fechas import hoy_local
from app.db.base import Base, TimestampMixin, UUIDMixin
from app.models.caja import MetodoPago

CENTIMO = Decimal("0.01")


class TipoVenta(str, enum.Enum):
    VENTA = "VENTA"
    COTIZACION = "COTIZACION"


class EstadoVenta(str, enum.Enum):
    #: Sólo cotizaciones: aún no se convirtió en venta.
    PENDIENTE = "PENDIENTE"
    CONFIRMADA = "CONFIRMADA"
    ANULADA = "ANULADA"
    #: Cotización que venció o que el cliente rechazó.
    RECHAZADA = "RECHAZADA"


ETIQUETAS_ESTADO_VENTA: dict[str, str] = {
    "PENDIENTE": "Pendiente",
    "CONFIRMADA": "Confirmada",
    "ANULADA": "Anulada",
    "RECHAZADA": "Rechazada",
}


class Venta(UUIDMixin, TimestampMixin, Base):
    """Venta o cotización. Comparten estructura porque una cotización es una
    venta que todavía no se cobró: convertirla no debe reescribir sus líneas."""

    __tablename__ = "ventas"
    __table_args__ = (
        CheckConstraint("descuento >= 0", name="ck_ventas_descuento_no_negativo"),
        Index("ix_ventas_tipo_estado", "tipo", "estado"),
        Index("ix_ventas_fecha", "created_at"),
    )

    numero: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    tipo: Mapped[TipoVenta] = mapped_column(
        Enum(TipoVenta, name="tipo_venta"), default=TipoVenta.VENTA, nullable=False
    )
    estado: Mapped[EstadoVenta] = mapped_column(
        Enum(EstadoVenta, name="estado_venta"), default=EstadoVenta.CONFIRMADA, nullable=False
    )

    #: Opcional: en el mostrador se vende sin pedir datos.
    cliente_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clientes.id", ondelete="RESTRICT"), index=True
    )
    cliente: Mapped["Cliente | None"] = relationship(lazy="joined")  # noqa: F821

    #: Si la venta salió de una orden de taller.
    ficha_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("fichas.id", ondelete="SET NULL"), index=True
    )

    sesion_caja_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sesiones_caja.id", ondelete="SET NULL"), index=True
    )

    descuento: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), nullable=False
    )

    #: Vigencia de la cotización.
    valido_hasta: Mapped[datetime | None] = mapped_column(Date)

    notas: Mapped[str | None] = mapped_column(Text)

    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    usuario: Mapped["User | None"] = relationship(lazy="joined")  # noqa: F821

    fecha_anulacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_anulacion: Mapped[str | None] = mapped_column(String(300))

    #: Cuándo se sacó del listado del día a día. Archivar es sólo eso: el
    #: documento sigue contando en caja, kardex, reportes y ante SUNAT.
    archivada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items: Mapped[list["VentaItem"]] = relationship(
        back_populates="venta",
        cascade="all, delete-orphan",
        order_by="VentaItem.orden",
        lazy="selectin",
    )
    pagos: Mapped[list["PagoVenta"]] = relationship(
        back_populates="venta", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def archivada(self) -> bool:
        return self.archivada_at is not None

    @property
    def subtotal(self) -> Decimal:
        return sum((i.subtotal for i in self.items), Decimal("0.00"))

    @property
    def total(self) -> Decimal:
        """Nunca negativo: un descuento mayor al subtotal deja la venta en 0."""
        return max(Decimal("0.00"), self.subtotal - self.descuento)

    @property
    def total_pagado(self) -> Decimal:
        return sum((p.monto for p in self.pagos), Decimal("0.00"))

    @property
    def saldo(self) -> Decimal:
        return self.total - self.total_pagado

    @property
    def esta_pagada(self) -> bool:
        """Tolerancia de un céntimo por los redondeos de un pago mixto."""
        return abs(self.saldo) <= CENTIMO

    @property
    def vencida(self) -> bool:
        if self.tipo is not TipoVenta.COTIZACION or self.valido_hasta is None:
            return False
        if self.estado is not EstadoVenta.PENDIENTE:
            return False
        # Día de Lima: con la fecha del servidor la cotización caducaba a las
        # 7 p. m. del día en que aún era válida.
        return self.valido_hasta < hoy_local()


class VentaItem(UUIDMixin, Base):
    __tablename__ = "venta_items"

    venta_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ventas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    venta: Mapped[Venta] = relationship(back_populates="items")

    orden: Mapped[int] = mapped_column(default=0, nullable=False)

    #: Igual que en las fichas: puede ser un producto del catálogo o texto
    #: libre (un servicio de taller, una pieza sin SKU).
    producto_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("productos.id", ondelete="RESTRICT"), index=True
    )
    producto: Mapped["Producto | None"] = relationship(lazy="joined")  # noqa: F821

    descripcion: Mapped[str] = mapped_column(String(200))
    cantidad: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("1"))
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    #: Descuento por línea, en soles.
    descuento: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))

    @property
    def subtotal(self) -> Decimal:
        bruto = (self.cantidad * self.precio_unitario) - self.descuento
        return max(Decimal("0.00"), bruto).quantize(CENTIMO)


class PagoVenta(UUIDMixin, Base):
    """Un cobro. Una venta admite varios: efectivo + Yape, por ejemplo."""

    __tablename__ = "venta_pagos"

    venta_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ventas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    venta: Mapped[Venta] = relationship(back_populates="pagos")

    metodo: Mapped[MetodoPago] = mapped_column(
        Enum(MetodoPago, name="metodo_pago"), nullable=False
    )
    monto: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    #: N° de operación de Yape/Plin, voucher de tarjeta, etc.
    referencia: Mapped[str | None] = mapped_column(String(80))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
