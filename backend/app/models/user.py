import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.models.role import Role


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    dni: Mapped[str | None] = mapped_column(String(12))
    phone: Mapped[str | None] = mapped_column(String(20))
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: Se incrementa al cambiar la contraseña. Los tokens llevan el valor con que
    #: se emitieron; si no coincide con éste, se rechazan. Así un cambio de clave
    #: cierra las sesiones abiertas con la contraseña anterior.
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"))
    role: Mapped[Role] = relationship(back_populates="users", lazy="selectin")

    @property
    def permission_codes(self) -> list[str]:
        return self.role.permission_codes if self.role else []

    def has_permission(self, code: str) -> bool:
        return code in set(self.permission_codes)
