import enum
import secrets
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


#: Alfabeto sin caracteres que se confunden al dictarlos o leerlos impresos
#: en papel térmico: sin 0/O, 1/I/L, 8/B.
ALFABETO_CODIGO = "ACDEFGHJKMNPQRTUVWXYZ2345679"
LARGO_CODIGO = 10


def generar_codigo_publico() -> str:
    """~48 bits de entropía: no se puede adivinar probando códigos."""
    return "".join(secrets.choice(ALFABETO_CODIGO) for _ in range(LARGO_CODIGO))


class EstadoFicha(str, enum.Enum):
    RECIBIDA = "RECIBIDA"
    EN_REVISION = "EN_REVISION"
    ESPERANDO_REPUESTOS = "ESPERANDO_REPUESTOS"
    EN_REPARACION = "EN_REPARACION"
    LISTA_PARA_ENTREGAR = "LISTA_PARA_ENTREGAR"
    ENTREGADA = "ENTREGADA"
    CANCELADA = "CANCELADA"


#: Estados desde los que ya no se avanza. Una ficha entregada o cancelada
#: sólo se reabre creando una ficha nueva, para no perder la trazabilidad.
ESTADOS_FINALES = {EstadoFicha.ENTREGADA, EstadoFicha.CANCELADA}


class ServicioSolicitado(str, enum.Enum):
    """Checklist de la ficha física. El texto libre va en `servicio_otro`."""

    MANTENIMIENTO_GENERAL = "MANTENIMIENTO_GENERAL"
    MANTENIMIENTO_COMPLETO = "MANTENIMIENTO_COMPLETO"
    AJUSTE_FRENOS = "AJUSTE_FRENOS"
    AJUSTE_CAMBIOS = "AJUSTE_CAMBIOS"
    LIMPIEZA_LUBRICACION = "LIMPIEZA_LUBRICACION"
    CAMBIO_COMPONENTES = "CAMBIO_COMPONENTES"
    ALINEACION_RUEDAS = "ALINEACION_RUEDAS"
    REVISION_SUSPENSION = "REVISION_SUSPENSION"


#: Etiquetas tal como aparecen impresas en la ficha.
ETIQUETAS_SERVICIO: dict[str, str] = {
    "MANTENIMIENTO_GENERAL": "Mantenimiento general",
    "MANTENIMIENTO_COMPLETO": "Mantenimiento completo",
    "AJUSTE_FRENOS": "Ajuste de frenos",
    "AJUSTE_CAMBIOS": "Ajuste de cambios",
    "LIMPIEZA_LUBRICACION": "Limpieza y lubricación",
    "CAMBIO_COMPONENTES": "Cambio de componentes",
    "ALINEACION_RUEDAS": "Alineación de ruedas",
    "REVISION_SUSPENSION": "Revisión de suspensión",
}

ETIQUETAS_ESTADO: dict[str, str] = {
    "RECIBIDA": "Recibida",
    "EN_REVISION": "En revisión",
    "ESPERANDO_REPUESTOS": "Esperando repuestos",
    "EN_REPARACION": "En reparación",
    "LISTA_PARA_ENTREGAR": "Lista para entregar",
    "ENTREGADA": "Entregada",
    "CANCELADA": "Cancelada",
}


class Ficha(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "fichas"
    __table_args__ = (
        Index("ix_fichas_estado", "estado"),
        Index("ix_fichas_fecha_recepcion", "fecha_recepcion"),
    )

    #: Correlativo visible. Lo asigna una secuencia de Postgres, no un
    #: SELECT MAX(...)+1, que bajo concurrencia entrega números repetidos.
    numero: Mapped[str] = mapped_column(String(20), unique=True, index=True)

    #: Código corto e impredecible para el QR del ticket térmico.
    #: Un JWT en la URL da un QR de versión 14 (~0.34 mm por módulo en 26 mm),
    #: al límite de lo que resuelve una térmica de 203 dpi. Con este código la
    #: URL baja a versión 3 (~0.79 mm por módulo), con margen de sobra para
    #: papel gastado o cabezal sucio.
    codigo_publico: Mapped[str] = mapped_column(
        String(16), unique=True, index=True, default=lambda: generar_codigo_publico()
    )

    cliente_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clientes.id", ondelete="RESTRICT"), nullable=False
    )
    bicicleta_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bicicletas.id", ondelete="RESTRICT"), nullable=False
    )
    cliente: Mapped["Cliente"] = relationship(lazy="joined")  # noqa: F821
    bicicleta: Mapped["Bicicleta"] = relationship(lazy="joined")  # noqa: F821

    estado: Mapped[EstadoFicha] = mapped_column(
        Enum(EstadoFicha, name="estado_ficha"), default=EstadoFicha.RECIBIDA, nullable=False
    )

    # --- Recepción ---
    fecha_recepcion: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    tecnico_recepcion_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    tecnico_recepcion: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys=[tecnico_recepcion_id], lazy="joined"
    )
    canal_referencia: Mapped[str | None] = mapped_column(String(120))

    # --- Servicio solicitado ---
    servicios: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    servicio_otro: Mapped[str | None] = mapped_column(String(200))

    # --- Diagnóstico y trabajo ---
    diagnostico_inicial: Mapped[str | None] = mapped_column(Text)
    trabajo_realizado: Mapped[str | None] = mapped_column(Text)
    tiempo_invertido_min: Mapped[int | None] = mapped_column(Integer)
    tecnico_responsable_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    tecnico_responsable: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys=[tecnico_responsable_id], lazy="joined"
    )

    # --- Observaciones ---
    observaciones: Mapped[str | None] = mapped_column(Text)
    garantia_dias: Mapped[int | None] = mapped_column(Integer)

    # --- Entrega ---
    fecha_entrega: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tecnico_entrega_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    tecnico_entrega: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys=[tecnico_entrega_id], lazy="joined"
    )

    #: Cuándo se sacó del tablero del taller. No cambia el estado ni el
    #: historial de la bicicleta: sólo deja de aparecer en el día a día.
    archivada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- Firmas (data URL PNG capturada en canvas) ---
    firma_cliente: Mapped[str | None] = mapped_column(Text)
    firma_cliente_dni: Mapped[str | None] = mapped_column(String(15))
    firma_tecnico: Mapped[str | None] = mapped_column(Text)
    firma_tecnico_dni: Mapped[str | None] = mapped_column(String(15))
    fecha_firma: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    repuestos: Mapped[list["FichaRepuesto"]] = relationship(
        back_populates="ficha",
        cascade="all, delete-orphan",
        order_by="FichaRepuesto.orden",
        lazy="selectin",
    )
    historial_estados: Mapped[list["FichaEstadoLog"]] = relationship(
        back_populates="ficha",
        cascade="all, delete-orphan",
        order_by="FichaEstadoLog.created_at",
        lazy="selectin",
    )

    @property
    def total_repuestos(self) -> Decimal:
        return sum((r.subtotal for r in self.repuestos), Decimal("0.00"))

    @property
    def archivada(self) -> bool:
        return self.archivada_at is not None

    @property
    def esta_firmada(self) -> bool:
        return bool(self.firma_cliente and self.firma_tecnico)


class FichaRepuesto(UUIDMixin, Base):
    """Fila de la tabla "REPUESTOS / COMPONENTES UTILIZADOS" de la ficha.

    Puede apuntar a un producto del inventario (`producto_id`) o ser texto
    libre, igual que en el papel: el taller a veces usa piezas que no están
    catalogadas. Sólo las líneas enlazadas mueven stock.
    """

    __tablename__ = "ficha_repuestos"

    ficha_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fichas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ficha: Mapped[Ficha] = relationship(back_populates="repuestos")

    #: RESTRICT: un producto con consumo histórico no se puede borrar sin
    #: romper la trazabilidad de las fichas que lo usaron.
    producto_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("productos.id", ondelete="RESTRICT"), index=True
    )
    producto: Mapped["Producto | None"] = relationship(lazy="joined")  # noqa: F821

    orden: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cantidad: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("1"))
    descripcion: Mapped[str] = mapped_column(String(200))
    marca: Mapped[str | None] = mapped_column(String(80))
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))

    @property
    def subtotal(self) -> Decimal:
        return (self.cantidad * self.precio_unitario).quantize(Decimal("0.01"))


class FichaEstadoLog(UUIDMixin, Base):
    """Traza de cada cambio de estado: quién, cuándo y por qué."""

    __tablename__ = "ficha_estados_log"

    ficha_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fichas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ficha: Mapped[Ficha] = relationship(back_populates="historial_estados")

    estado_anterior: Mapped[EstadoFicha | None] = mapped_column(
        Enum(EstadoFicha, name="estado_ficha")
    )
    estado_nuevo: Mapped[EstadoFicha] = mapped_column(
        Enum(EstadoFicha, name="estado_ficha"), nullable=False
    )
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    usuario: Mapped["User | None"] = relationship(lazy="joined")  # noqa: F821
    comentario: Mapped[str | None] = mapped_column(String(300))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
