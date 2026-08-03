"""codigo publico de venta, para compartir la nota de venta por WhatsApp

Revision ID: b6c4d2a70f18
Revises: a8b3c1f6e920
Create Date: 2026-08-03 10:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Se importa la función del modelo para que el backfill use exactamente el
# mismo alfabeto y longitud que los códigos nuevos.
from app.models.ficha import generar_codigo_publico

revision: str = 'b6c4d2a70f18'
down_revision: str | None = 'a8b3c1f6e920'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # En tres pasos, igual que en comprobantes: la columna no puede nacer NOT
    # NULL sobre una tabla con filas, y un DEFAULT fijo repetiría el valor y
    # violaría el índice único.
    op.add_column('ventas', sa.Column('codigo_publico', sa.String(length=16), nullable=True))

    conexion = op.get_bind()
    ids = conexion.execute(sa.text("SELECT id FROM ventas")).scalars().all()
    for venta_id in ids:
        conexion.execute(
            sa.text("UPDATE ventas SET codigo_publico = :c WHERE id = :i"),
            {"c": generar_codigo_publico(), "i": venta_id},
        )

    op.alter_column('ventas', 'codigo_publico', nullable=False)
    op.create_index(
        op.f('ix_ventas_codigo_publico'), 'ventas', ['codigo_publico'], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_ventas_codigo_publico'), table_name='ventas')
    op.drop_column('ventas', 'codigo_publico')
