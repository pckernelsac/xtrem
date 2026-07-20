import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.permissions import PERMISSION_CODES
from app.db.session import get_db
from app.models.role import Permission, Role
from app.models.user import User
from app.schemas.role import PermissionOut, RoleCreate, RoleOut, RoleUpdate

router = APIRouter(prefix="/roles", tags=["roles"])


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower().strip()).strip("-")
    return slug or "rol"


def _users_count(db: Session, role_id: uuid.UUID) -> int:
    return db.scalar(select(func.count(User.id)).where(User.role_id == role_id)) or 0


def _to_out(db: Session, role: Role) -> RoleOut:
    return RoleOut(
        id=role.id,
        slug=role.slug,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        permission_codes=role.permission_codes,
        users_count=_users_count(db, role.id),
    )


def _resolve_permissions(db: Session, codes: list[str]) -> list[Permission]:
    unknown = sorted(set(codes) - PERMISSION_CODES)
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Permisos desconocidos: {', '.join(unknown)}",
        )
    return list(db.scalars(select(Permission).where(Permission.code.in_(codes))).all())


@router.get("/permissions", response_model=list[PermissionOut])
def list_permissions(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("roles.ver")),
) -> list[Permission]:
    """Catálogo completo de permisos, para pintar la matriz de asignación."""
    return list(db.scalars(select(Permission).order_by(Permission.module, Permission.code)).all())


@router.get("", response_model=list[RoleOut])
def list_roles(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("roles.ver")),
) -> list[RoleOut]:
    roles = db.scalars(select(Role).order_by(Role.name)).all()
    return [_to_out(db, r) for r in roles]


@router.get("/{role_id}", response_model=RoleOut)
def get_role(
    role_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("roles.ver")),
) -> RoleOut:
    role = db.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Rol no encontrado")
    return _to_out(db, role)


@router.post("", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
def create_role(
    data: RoleCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("roles.crear")),
) -> RoleOut:
    slug = _slugify(data.name)
    if db.scalar(select(Role).where(Role.slug == slug)):
        raise HTTPException(status_code=409, detail=f"Ya existe un rol con el slug '{slug}'")

    role = Role(
        slug=slug,
        name=data.name,
        description=data.description,
        is_system=False,
        permissions=_resolve_permissions(db, data.permission_codes),
    )
    db.add(role)
    db.commit()
    db.refresh(role)
    return _to_out(db, role)


@router.patch("/{role_id}", response_model=RoleOut)
def update_role(
    role_id: uuid.UUID,
    data: RoleUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("roles.editar")),
) -> RoleOut:
    role = db.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Rol no encontrado")

    # El administrador debe conservar acceso total: si se le pudieran quitar
    # permisos, un descuido dejaría el sistema sin nadie capaz de repararlo.
    if role.slug == "administrador" and data.permission_codes is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Los permisos del rol Administrador no se pueden modificar",
        )

    if data.name is not None:
        if role.is_system:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No se puede renombrar un rol de sistema",
            )
        role.name = data.name
    if data.description is not None:
        role.description = data.description
    if data.permission_codes is not None:
        role.permissions = _resolve_permissions(db, data.permission_codes)

    db.commit()
    db.refresh(role)
    return _to_out(db, role)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(
    role_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("roles.eliminar")),
) -> None:
    role = db.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Rol no encontrado")
    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="No se puede eliminar un rol de sistema"
        )

    count = _users_count(db, role.id)
    if count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El rol tiene {count} usuario(s) asignado(s); reasígnalos primero",
        )

    db.delete(role)
    db.commit()
