"""Pone al día el catálogo de permisos y los roles de sistema.

Corre en **cada arranque**, a diferencia del seed completo, que crea además el
usuario administrador y va detrás de `RUN_SEED`.

El motivo es concreto: una actualización que añade un permiso nuevo no sirve de
nada si nadie lo tiene asignado. Al administrador le corresponden todos, pero
esa asignación vive en la base, no en el código, así que sin sincronizar el menú
correspondiente sencillamente no aparece —y el síntoma («no está la opción») no
apunta en absoluto a su causa.

Es idempotente y no pisa nada ajustado a mano: los roles que no son el
administrador sólo reciben su plantilla al crearse.
"""

from app.db.seed import sync_permissions, sync_roles
from app.db.session import SessionLocal


def run() -> None:
    db = SessionLocal()
    try:
        permisos = sync_permissions(db)
        sync_roles(db, permisos)
        db.commit()
        print(f"Permisos sincronizados: {len(permisos)}")
    finally:
        db.close()


if __name__ == "__main__":
    run()
