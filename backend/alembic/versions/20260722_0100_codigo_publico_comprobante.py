"""codigo publico de comprobante

Revision ID: c3f1a9d47b02
Revises: b7d5091ae234
Create Date: 2026-07-22 01:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Se importa la función del modelo para que el backfill use exactamente el
# mismo alfabeto y longitud que los códigos nuevos.
from app.models.ficha import generar_codigo_publico


revision: str = 'c3f1a9d47b02'
down_revision: str | None = 'b7d5091ae234'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # En tres pasos: la columna no puede nacer NOT NULL sobre una tabla que ya
    # tiene comprobantes, y un DEFAULT fijo violaría el índice único al repetirse.
    op.add_column('comprobantes', sa.Column('codigo_publico', sa.String(length=16), nullable=True))

    conexion = op.get_bind()
    ids = conexion.execute(sa.text("SELECT id FROM comprobantes")).scalars().all()
    for comprobante_id in ids:
        conexion.execute(
            sa.text("UPDATE comprobantes SET codigo_publico = :c WHERE id = :i"),
            {"c": generar_codigo_publico(), "i": comprobante_id},
        )

    op.alter_column('comprobantes', 'codigo_publico', nullable=False)
    op.create_index(
        op.f('ix_comprobantes_codigo_publico'), 'comprobantes', ['codigo_publico'], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_comprobantes_codigo_publico'), table_name='comprobantes')
    op.drop_column('comprobantes', 'codigo_publico')
