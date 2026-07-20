import enum

from sqlalchemy import Boolean, Enum, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class TipoDocumento(str, enum.Enum):
    DNI = "DNI"
    RUC = "RUC"
    CE = "CE"  # Carné de extranjería
    PASAPORTE = "PASAPORTE"


class Cliente(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "clientes"
    __table_args__ = (
        # Un mismo número puede repetirse entre tipos distintos, pero no dentro
        # del mismo tipo. Se valida a nivel de BD, no sólo en el endpoint.
        Index(
            "uq_clientes_documento",
            "tipo_documento",
            "numero_documento",
            unique=True,
        ),
        Index("ix_clientes_nombre", "nombre"),
    )

    nombre: Mapped[str] = mapped_column(String(160))
    tipo_documento: Mapped[TipoDocumento] = mapped_column(
        Enum(TipoDocumento, name="tipo_documento"), default=TipoDocumento.DNI
    )
    numero_documento: Mapped[str] = mapped_column(String(15), index=True)

    telefono: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(160))
    direccion: Mapped[str | None] = mapped_column(String(240))
    notas: Mapped[str | None] = mapped_column(Text)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    bicicletas: Mapped[list["Bicicleta"]] = relationship(  # noqa: F821
        back_populates="cliente", cascade="all, delete-orphan", lazy="selectin"
    )
