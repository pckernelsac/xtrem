import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import INET

from app.db.base import Base, UUIDMixin


class RegistroAuditoria(UUIDMixin, Base):
    """Bitácora de acciones que cambian estado.

    Registra el rastro HTTP de cada operación mutante: quién, qué, cuándo y con
    qué resultado. No guarda el cuerpo de la petición —evita filtrar
    contraseñas, firmas o datos personales— sólo los metadatos de la acción.
    """

    __tablename__ = "auditoria"
    __table_args__ = (
        Index("ix_auditoria_fecha", "created_at"),
        Index("ix_auditoria_usuario", "usuario_id"),
        Index("ix_auditoria_entidad", "entidad"),
    )

    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    #: Se guarda el id y también el correo, para que el rastro sobreviva aunque
    #: el usuario se elimine.
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    usuario_email: Mapped[str | None] = mapped_column(String(160))

    metodo: Mapped[str] = mapped_column(String(8))
    ruta: Mapped[str] = mapped_column(String(300))
    #: Módulo afectado, derivado de la ruta (ventas, fichas, caja, …).
    entidad: Mapped[str | None] = mapped_column(String(40))
    status_code: Mapped[int] = mapped_column(Integer)
    duracion_ms: Mapped[int] = mapped_column(Integer)
    ip: Mapped[str | None] = mapped_column(INET)
