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
    gastar_verificacion,
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
        access_token=create_access_token(str(user.id), user.token_version),
        refresh_token=create_refresh_token(str(user.id), user.token_version),
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
    # no filtramos qué correos existen en el sistema. Y el mismo coste: sin
    # cuenta se comprueba igualmente contra un hash de descarte, porque
    # responder al instante también delataría que el correo no existe.
    if user is None:
        gastar_verificacion(data.password)

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
    if (
        user is None
        or not user.is_active
        or payload.get("tv", 0) != user.token_version
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token inválido o expirado"
        )
    return _tokens_for(user)


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Invalida todos los tokens del usuario, no sólo el del navegador actual.

    Sin esto, cerrar sesión era un gesto del cliente: borraba los tokens del
    navegador, pero el refresh seguía siendo válido hasta una semana. Quien lo
    hubiera copiado antes —de un equipo compartido, de una copia de seguridad
    del navegador— podía seguir entrando. Subir `token_version` los caduca
    todos de golpe, que es lo que quien pulsa «cerrar sesión» da por hecho.
    """
    user.token_version += 1
    db.commit()


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    data: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    # Mismo freno que el login. Una sesión olvidada en el mostrador permitiría
    # adivinar la contraseña actual a base de intentos y quedarse con la cuenta
    # para siempre; aquí el techo es el mismo que en la puerta de entrada.
    ip = rate_limit_login.ip_de(request)
    rate_limit_login.verificar(db, user.email, ip)

    if not verify_password(data.current_password, user.hashed_password):
        rate_limit_login.registrar(
            db, user.email, ip, exito=False, user_agent=request.headers.get("user-agent")
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="La contraseña actual no es correcta"
        )
    user.hashed_password = hash_password(data.new_password)
    # Invalida las sesiones abiertas con la contraseña anterior.
    user.token_version += 1
    db.commit()
    # Acertar la actual demuestra ser el dueño: no arrastra los fallos previos.
    rate_limit_login.limpiar(db, user.email, ip)
