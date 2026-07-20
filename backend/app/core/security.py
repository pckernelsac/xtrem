import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

TokenType = Literal["access", "refresh", "print"]


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _create_token(subject: str, token_type: TokenType, expires_delta: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(subject: str) -> str:
    return _create_token(
        subject, "access", timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )


def create_refresh_token(subject: str) -> str:
    return _create_token(subject, "refresh", timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))


def create_print_token(ficha_id: str) -> tuple[str, datetime]:
    """Token de sólo-impresión para una ficha concreta.

    Va en la query string para que el enlace se pueda abrir directamente desde
    WhatsApp o desde una tablet sin sesión. Por eso NO sirve para nada más:
    su `type` es "print" y queda atado al id de una única ficha.
    """
    expira = datetime.now(UTC) + timedelta(minutes=settings.PRINT_TOKEN_EXPIRE_MINUTES)
    token = _create_token(
        ficha_id, "print", timedelta(minutes=settings.PRINT_TOKEN_EXPIRE_MINUTES)
    )
    return token, expira


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any] | None:
    """Devuelve el payload sólo si la firma es válida Y el tipo es el esperado.

    Validar el tipo evita que un refresh token se use como access token.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
    if payload.get("type") != expected_type:
        return None
    return payload
