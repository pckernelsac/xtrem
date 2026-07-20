import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import ChangePasswordRequest, LoginRequest, RefreshRequest, TokenPair
from app.schemas.user import MeOut
from app.services import rate_limit_login

router = APIRouter(prefix="/auth", tags=["auth"])


def _tokens_for(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/login", response_model=TokenPair)
def login(
    data: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenPair:
    email = data.email.lower()
    ip = rate_limit_login.ip_de(request)
    agente = request.headers.get("user-agent")

    # El freno va antes de tocar la contraseña: comprobarla cuesta un hash de
    # bcrypt, que es precisamente el trabajo que no se le quiere regalar a un
    # atacante que ya está bloqueado.
    rate_limit_login.verificar(db, email, ip)

    user = db.scalar(select(User).where(User.email == email))

    # Mismo mensaje para usuario inexistente y contraseña incorrecta:
    # no filtramos qué correos existen en el sistema.
    if user is None or not verify_password(data.password, user.hashed_password):
        rate_limit_login.registrar(db, email, ip, exito=False, user_agent=agente)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Correo o contraseña incorrectos"
        )
    if not user.is_active:
        # Cuenta la cuenta archivada como fallo: si no, sería un oráculo para
        # confirmar qué correos existen probando sin límite.
        rate_limit_login.registrar(db, email, ip, exito=False, user_agent=agente)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="El usuario está desactivado"
        )

    rate_limit_login.registrar(db, email, ip, exito=True, user_agent=agente)
    rate_limit_login.limpiar(db, email, ip)
    # Aprovechando que alguien entró bien, se poda lo viejo: la tabla no tiene
    # otro momento natural de limpieza y así no crece sin techo.
    rate_limit_login.purgar_antiguos(db)

    user.last_login_at = datetime.now(UTC)
    db.commit()
    return _tokens_for(user)


@router.post("/refresh", response_model=TokenPair)
def refresh(data: RefreshRequest, db: Session = Depends(get_db)) -> TokenPair:
    payload = decode_token(data.refresh_token, expected_type="refresh")
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token inválido o expirado"
        )
    try:
        user = db.get(User, uuid.UUID(payload["sub"]))
    except (KeyError, ValueError):
        user = None
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token inválido o expirado"
        )
    return _tokens_for(user)


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    data: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if not verify_password(data.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="La contraseña actual no es correcta"
        )
    user.hashed_password = hash_password(data.new_password)
    db.commit()
