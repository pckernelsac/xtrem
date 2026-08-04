"""borrar los comprobantes de FactPro que quedaron sin validar

Revision ID: d1a7c3e58b46
Revises: c9e5f1b34a27
Create Date: 2026-08-03 19:00:00.000000

Al cambiar a Nubefact el correlativo vuelve a empezar en 1, porque la cuenta
nueva no tiene ningún documento emitido. Los comprobantes que dejó FactPro
ocupan esos mismos números (B001-1..16, F001-3..8) y el índice único
`ux_comprobantes_serie_numero` haría fallar la primera emisión.

Esos documentos nunca llegaron a validarse ante SUNAT y sus PDF viven en
servidores de FactPro a los que ya no hay acceso, así que no queda nada que
conservar: se borran por decisión explícita del dueño del sistema.

Las **ventas no se tocan**: siguen contando en caja, kardex y reportes. Lo
único que desaparece es el rastro del comprobante que nunca fue válido.

IRREVERSIBLE: el downgrade no puede recuperar las filas.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd1a7c3e58b46'
down_revision: str | None = 'c9e5f1b34a27'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conexion = op.get_bind()

    # Todo lo que hay en la tabla al aplicar esta migración es de FactPro: se
    # despliega junto con el cambio de proveedor, así que aún no puede existir
    # ningún comprobante de Nubefact.
    total = conexion.execute(sa.text("SELECT count(*) FROM comprobantes")).scalar() or 0

    # La autorreferencia de las notas de crédito impediría el DELETE.
    conexion.execute(
        sa.text("UPDATE comprobantes SET documento_afectado_id = NULL "
                "WHERE documento_afectado_id IS NOT NULL")
    )
    conexion.execute(sa.text("DELETE FROM comprobantes"))
    print(f"Comprobantes de FactPro eliminados: {total}")

    # Las secuencias de correlativo se reinician para que la numeración de
    # Nubefact empiece en 1. Se recrean solas si no existen, pero si el entorno
    # ya las tenía avanzadas por pruebas, dejarlas quemaría números.
    series = conexion.execute(
        sa.text("SELECT sequencename FROM pg_sequences WHERE sequencename LIKE 'comprobante\\_%'")
    ).scalars().all()
    for secuencia in series:
        conexion.execute(sa.text(f"ALTER SEQUENCE {secuencia} RESTART WITH 1"))
        print(f"Secuencia reiniciada: {secuencia}")


def downgrade() -> None:
    # No hay vuelta atrás: las filas se borraron y su contenido vivía en
    # FactPro. Se deja pasar para no bloquear un rollback del esquema.
    pass
