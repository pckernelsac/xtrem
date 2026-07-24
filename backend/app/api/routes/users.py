import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.security import hash_password
from app.db.session import get_db
from app.models.auditoria import RegistroAuditoria
from app.models.caja import SesionCaja
from app.models.ficha import Ficha
from app.models.inventario import MovimientoKardex
from app.models.role import Role
from app.models.user import User
from app.models.venta import Venta
from app.schemas.user import UserCreate, UserOut, UserPage, UserUpdate

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


def _get_role_or_422(db: Session, role_id: uuid.UUID) -> Role:
    role = db.get(Role, role_id)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="El rol indicado no existe"
        )
    return role


def _assert_email_free(db: Session, email: str, exclude_id: uuid.UUID | None = None) -> None:
    stmt = select(User).where(User.email == email)
    if exclude_id:
        stmt = stmt.where(User.id != exclude_id)
    if db.scalar(stmt):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Ya existe un usuario con ese correo"
        )


@router.get("", response_model=UserPage)
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("usuarios.ver")),
    search: str | None = Query(default=None, description="Busca por nombre, correo o DNI"),
    role_slug: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> UserPage:
    stmt = select(User).join(Role)

    if search:
        like = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(User.full_name).like(like),
                func.lower(User.email).like(like),
                User.dni.like(like),
            )
        )
    if role_slug:
        stmt = stmt.where(Role.slug == role_slug)
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(User.full_name).offset((page - 1) * page_size).limit(page_size)
    ).all()

    return UserPage(
        items=[UserOut.model_validate(u) for u in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("usuarios.ver")),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("usuarios.crear")),
) -> User:
    email = data.email.lower()
    _assert_email_free(db, email)
    _get_role_or_422(db, data.role_id)

    user = User(
        email=email,
        full_name=data.full_name,
        dni=data.dni,
        phone=data.phone,
        is_active=data.is_active,
        role_id=data.role_id,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID,
    data: UserUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(require_permission("usuarios.editar")),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Evita que alguien se desactive o se degrade a sí mismo y quede fuera.
    if user.id == current.id:
        if data.is_active is False:
            raise HTTPException(status_code=409, detail="No puedes desactivar tu propia cuenta")
        if data.role_id is not None and data.role_id != user.role_id:
            raise HTTPException(status_code=409, detail="No puedes cambiar tu propio rol")

    if data.email is not None:
        email = data.email.lower()
        _assert_email_free(db, email, exclude_id=user.id)
        user.email = email
    if data.role_id is not None:
        _get_role_or_422(db, data.role_id)
        user.role_id = data.role_id
    if data.full_name is not None:
        user.full_name = data.full_name
    if data.dni is not None:
        user.dni = data.dni
    if data.phone is not None:
        user.phone = data.phone
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.password:
        user.hashed_password = hash_password(data.password)
        # Cerrar las sesiones abiertas con la contraseña anterior (reseteo de admin).
        user.token_version += 1

    db.commit()
    db.refresh(user)
    return user


def _actividad(db: Session, user_id: uuid.UUID) -> int:
    """Cuántas huellas dejó la cuenta en el sistema.

    Las claves foráneas son SET NULL, así que borrar al usuario no rompería
    nada a nivel de base: simplemente dejaría fichas, ventas y asientos de
    kardex sin autor. Eso es justo lo que no se quiere perder.
    """
    conteos = (
        select(func.count()).select_from(Ficha).where(
            or_(
                Ficha.tecnico_recepcion_id == user_id,
                Ficha.tecnico_responsable_id == user_id,
                Ficha.tecnico_entrega_id == user_id,
            )
        ),
        select(func.count()).select_from(Venta).where(Venta.usuario_id == user_id),
        select(func.count())
        .select_from(MovimientoKardex)
        .where(MovimientoKardex.usuario_id == user_id),
        select(func.count())
        .select_from(SesionCaja)
        .where(
            or_(
                SesionCaja.usuario_apertura_id == user_id,
                SesionCaja.usuario_cierre_id == user_id,
            )
        ),
        select(func.count()).select_from(RegistroAuditoria).where(RegistroAuditoria.usuario_id == user_id),
    )
    return sum(db.scalar(c) or 0 for c in conteos)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_permission("usuarios.eliminar")),
) -> None:
    """Borrado definitivo, sólo para la cuenta que nunca llegó a usarse.

    Archivar (`PATCH {is_active: false}`) es la vía normal para quien deja el
    taller: no puede entrar, pero sus fichas y ventas siguen diciendo quién las
    hizo. Aquí se borra de verdad, así que se niega en cuanto haya actividad.
    """
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if user.id == current.id:
        raise HTTPException(status_code=409, detail="No puedes eliminar tu propia cuenta")

    huellas = _actividad(db, user_id)
    if huellas:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{user.full_name} tiene {huellas} registro(s) a su nombre (fichas, ventas, "
                "kardex, caja o auditoría); archívalo en vez de eliminarlo"
            ),
        )

    db.delete(user)
    db.commit()
