from datetime import datetime

from sqlalchemy import Boolean, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin


class IntentoLogin(UUIDMixin, Base):
    """Intentos de inicio de sesión, para frenar la fuerza bruta.

    Vive en la base y no en memoria del proceso a propósito: en producción hay
    varios workers de uvicorn y un contador en RAM se saltaría con sólo caer en
    otro proceso, además de reiniciarse con cada despliegue.

    Sólo guarda metadatos —correo intentado, IP y si acertó—, nunca la
    contraseña probada.
    """

    __tablename__ = "intentos_login"
    __table_args__ = (
        # El bloqueo consulta por (correo, fecha) y por (ip, fecha); un índice
        # por cada camino evita recorrer la tabla entera en cada login.
        Index("ix_intentos_login_email_fecha", "email", "created_at"),
        Index("ix_intentos_login_ip_fecha", "ip", "created_at"),
    )

    #: Correo tal como se intentó, en minúsculas. Puede no existir como usuario:
    #: justamente eso es lo que se quiere contar.
    email: Mapped[str] = mapped_column(String(160), nullable=False)
    #: Texto y no `inet`: aquí sólo se compara por igualdad, y el tipo `inet`
    #: obliga a castear en cada consulta y revienta si llega una cabecera
    #: `X-Forwarded-For` con basura, que es justo lo que manda un atacante.
    ip: Mapped[str | None] = mapped_column(String(45))
    exito: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    #: Se conserva para distinguir un ataque distribuido de un usuario
    #: despistado al revisar la bitácora.
    user_agent: Mapped[str | None] = mapped_column(String(200))
