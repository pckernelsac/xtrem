import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
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

from app.db.base import Base, TimestampMixin, UUIDMixin


class EstadoCaja(str, enum.Enum):
    ABIERTA = "ABIERTA"
    CERRADA = "CERRADA"


class MetodoPago(str, enum.Enum):
    EFECTIVO = "EFECTIVO"
    YAPE = "YAPE"
    PLIN = "PLIN"
    TRANSFERENCIA = "TRANSFERENCIA"
    TARJETA = "TARJETA"


#: Sólo el efectivo entra y sale del cajón físico. Los demás métodos se
#: registran para el reporte, pero no se cuentan en el arqueo.
METODOS_EFECTIVO = {MetodoPago.EFECTIVO}

ETIQUETAS_METODO: dict[str, str] = {
    "EFECTIVO": "Efectivo",
    "YAPE": "Yape",
    "PLIN": "Plin",
    "TRANSFERENCIA": "Transferencia",
    "TARJETA": "Tarjeta",
}


class TipoMovimientoCaja(str, enum.Enum):
    INGRESO = "INGRESO"
    EGRESO = "EGRESO"


class SesionCaja(UUIDMixin, TimestampMixin, Base):
    """Una jornada del cajón: se abre con un monto, se cierra con un arqueo."""

    __tablename__ = "sesiones_caja"
    __table_args__ = (Index("ix_sesiones_caja_estado", "estado"),)

    numero: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    estado: Mapped[EstadoCaja] = mapped_column(
        Enum(EstadoCaja, name="estado_caja"), default=EstadoCaja.ABIERTA, nullable=False
    )

    monto_inicial: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), nullable=False
    )
    fecha_apertura: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    usuario_apertura_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    usuario_apertura: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys=[usuario_apertura_id], lazy="joined"
    )

    fecha_cierre: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    usuario_cierre_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    usuario_cierre: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys=[usuario_cierre_id], lazy="joined"
    )

    #: Lo que el cajero contó físicamente al cerrar.
    monto_declarado: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    #: Lo que el sistema esperaba encontrar. Se congela al cerrar para que el
    #: arqueo no cambie si después se anula una venta de esa jornada.
    monto_esperado: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))

    observaciones: Mapped[str | None] = mapped_column(Text)

    movimientos: Mapped[list["MovimientoCaja"]] = relationship(
        back_populates="sesion",
        cascade="all, delete-orphan",
        order_by="MovimientoCaja.created_at",
    )

    @property
    def diferencia(self) -> Decimal | None:
        """Positiva = sobró dinero; negativa = faltó."""
        if self.monto_declarado is None or self.monto_esperado is None:
            return None
        return self.monto_declarado - self.monto_esperado


class MovimientoCaja(UUIDMixin, Base):
    """Cada entrada o salida de dinero de la sesión."""

    __tablename__ = "movimientos_caja"

    sesion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sesiones_caja.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sesion: Mapped[SesionCaja] = relationship(back_populates="movimientos")

    tipo: Mapped[TipoMovimientoCaja] = mapped_column(
        Enum(TipoMovimientoCaja, name="tipo_movimiento_caja"), nullable=False
    )
    metodo: Mapped[MetodoPago] = mapped_column(
        Enum(MetodoPago, name="metodo_pago"), nullable=False, index=True
    )
    monto: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    concepto: Mapped[str] = mapped_column(String(200))

    #: Documento origen (venta, anulación, retiro). Texto para no atar el
    #: cajón a un único tipo de documento.
    referencia: Mapped[str | None] = mapped_column(String(80), index=True)

    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    usuario: Mapped["User | None"] = relationship(lazy="joined")  # noqa: F821

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
