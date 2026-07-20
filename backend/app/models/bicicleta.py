import enum
import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.models.cliente import Cliente


class TipoBicicleta(str, enum.Enum):
    MTB = "MTB"
    RUTA = "RUTA"
    URBANA = "URBANA"
    BMX = "BMX"
    PLEGABLE = "PLEGABLE"
    ELECTRICA = "ELECTRICA"
    INFANTIL = "INFANTIL"
    OTRA = "OTRA"


class Bicicleta(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "bicicletas"
    __table_args__ = (
        # El N° de serie identifica físicamente a la bici y no debe repetirse.
        # Índice parcial: muchas bicis llegan al taller sin serie legible, y
        # varios NULL no deben chocar entre sí.
        Index(
            "uq_bicicletas_numero_serie",
            "numero_serie",
            unique=True,
            postgresql_where=text("numero_serie IS NOT NULL"),
        ),
        Index("ix_bicicletas_cliente", "cliente_id"),
    )

    cliente_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False
    )
    cliente: Mapped[Cliente] = relationship(back_populates="bicicletas", lazy="joined")

    marca: Mapped[str] = mapped_column(String(80))
    modelo: Mapped[str | None] = mapped_column(String(80))
    color: Mapped[str | None] = mapped_column(String(40))
    numero_serie: Mapped[str | None] = mapped_column(String(60))
    tipo: Mapped[TipoBicicleta] = mapped_column(
        Enum(TipoBicicleta, name="tipo_bicicleta"), default=TipoBicicleta.MTB
    )
    rodado: Mapped[str | None] = mapped_column(String(10))
    talla: Mapped[str | None] = mapped_column(String(10))
    anio: Mapped[int | None] = mapped_column(Integer)
    notas: Mapped[str | None] = mapped_column(Text)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    @property
    def descripcion(self) -> str:
        """Etiqueta corta para listados y para la ficha de taller."""
        partes = [self.marca, self.modelo, self.color]
        return " ".join(p for p in partes if p)
