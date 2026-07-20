"""Seed idempotente: sincroniza el catálogo de permisos, crea los roles base
y el usuario administrador inicial.

Correr con:  docker compose exec zx_api python -m app.db.seed
"""

import os
import secrets
import string

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import DEFAULT_ROLES, PERMISSIONS
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.role import Permission, Role
from app.models.user import User


def sync_permissions(db: Session) -> dict[str, Permission]:
    """Alta de permisos nuevos y actualización de descripciones.

    No borra permisos que ya no estén en el catálogo: si un rol los tiene
    asignados, eliminarlos en silencio cambiaría accesos sin aviso.
    """
    existing = {p.code: p for p in db.scalars(select(Permission)).all()}

    for definition in PERMISSIONS:
        current = existing.get(definition.code)
        if current is None:
            current = Permission(
                code=definition.code,
                module=definition.module,
                description=definition.description,
            )
            db.add(current)
            existing[definition.code] = current
            print(f"  + permiso {definition.code}")
        else:
            current.module = definition.module
            current.description = definition.description

    db.flush()

    huerfanos = sorted(set(existing) - {p.code for p in PERMISSIONS})
    if huerfanos:
        print(f"  ! permisos en BD fuera del catálogo (revisar): {', '.join(huerfanos)}")

    return existing


def sync_roles(db: Session, permissions: dict[str, Permission]) -> dict[str, Role]:
    roles: dict[str, Role] = {}

    for slug, spec in DEFAULT_ROLES.items():
        role = db.scalar(select(Role).where(Role.slug == slug))
        if role is None:
            role = Role(
                slug=slug,
                name=str(spec["name"]),
                description=str(spec["description"]),
                is_system=True,
            )
            db.add(role)
            print(f"  + rol {slug}")
        role.is_system = True

        wanted = spec["permissions"]
        if wanted == "*":
            role.permissions = list(permissions.values())
        else:
            assert isinstance(wanted, list)
            faltantes = [c for c in wanted if c not in permissions]
            if faltantes:
                raise RuntimeError(
                    f"El rol '{slug}' referencia permisos inexistentes: {faltantes}"
                )
            # Sólo en la primera creación se fija la plantilla; después
            # respetamos lo que el administrador haya ajustado desde la UI.
            if not role.permissions:
                role.permissions = [permissions[c] for c in wanted]

        roles[slug] = role

    db.flush()
    return roles


def ensure_admin(db: Session, roles: dict[str, Role]) -> None:
    email = os.getenv("ADMIN_EMAIL", "admin@zonaxtrema.pe").lower()

    if db.scalar(select(User).where(User.email == email)):
        print(f"  = admin {email} ya existe (sin cambios)")
        return

    password = os.getenv("ADMIN_PASSWORD") or "".join(
        secrets.choice(string.ascii_letters + string.digits) for _ in range(14)
    )

    db.add(
        User(
            email=email,
            full_name=os.getenv("ADMIN_NAME", "Administrador Zona Xtrema"),
            hashed_password=hash_password(password),
            is_active=True,
            role_id=roles["administrador"].id,
        )
    )
    print(f"  + admin creado: {email}")
    if not os.getenv("ADMIN_PASSWORD"):
        print(f"\n  >>> CONTRASEÑA GENERADA: {password}")
        print("  >>> Guárdala ahora y cámbiala tras el primer login.\n")


def run() -> None:
    with SessionLocal() as db:
        print("Sincronizando permisos...")
        permissions = sync_permissions(db)
        print("Sincronizando roles...")
        roles = sync_roles(db, permissions)
        print("Verificando administrador...")
        ensure_admin(db, roles)
        db.commit()
    print("Seed completado.")


if __name__ == "__main__":
    run()
