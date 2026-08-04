"""registrar en que ambiente se emitio cada comprobante

Revision ID: b5e1c937f6a2
Revises: a3d9f42b8c17
Create Date: 2026-08-04 16:00:00.000000

Hasta ahora el ambiente se deducia del ajuste actual, y eso rompe en cuanto se
pasa a produccion: los comprobantes emitidos en pruebas dejarian de aparecer
como tales y se colarian en el registro de ventas del contador, que filtra por
fecha de emision y no tiene forma de distinguirlos.

Todo lo que existe hoy se marca como NO produccion, que es lo correcto: se emitio
contra el ambiente de pruebas.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b5e1c937f6a2'
down_revision: str | None = 'a3d9f42b8c17'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for tabla in ('comprobantes', 'lotes_sunat'):
        op.add_column(
            tabla,
            sa.Column(
                'emitido_en_produccion', sa.Boolean(), nullable=False,
                server_default=sa.false(),
            ),
        )
        op.alter_column(tabla, 'emitido_en_produccion', server_default=None)


def downgrade() -> None:
    op.drop_column('lotes_sunat', 'emitido_en_produccion')
    op.drop_column('comprobantes', 'emitido_en_produccion')
