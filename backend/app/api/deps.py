import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)

CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Credenciales inválidas o expiradas",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise CREDENTIALS_ERROR

    payload = decode_token(credentials.credentials, expected_type="access")
    if payload is None:
        raise CREDENTIALS_ERROR

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise CREDENTIALS_ERROR from None

    user = db.get(User, user_id)
    if user is None:
        raise CREDENTIALS_ERROR
    # Un token emitido antes de un cambio de contraseña queda invalidado: su `tv`
    # ya no coincide con el del usuario. Los tokens previos a esta función no
    # traen `tv` y valen como 0, igual que el token_version inicial.
    if payload.get("tv", 0) != user.token_version:
        raise CREDENTIALS_ERROR
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="El usuario está desactivado"
        )
    return user


def require_permission(*codes: str):
    """Exige que el usuario tenga TODOS los permisos indicados.

    Uso: `dependencies=[Depends(require_permission("clientes.crear"))]`
    """

    def dependency(user: User = Depends(get_current_user)) -> User:
        granted = set(user.permission_codes)
        missing = [c for c in codes if c not in granted]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permiso requerido: {', '.join(missing)}",
            )
        return user

    return dependency
