"""detalle libre por línea de venta, visible en el comprobante

Revision ID: a8b3c1f6e920
Revises: f7a1c2e93d84
Create Date: 2026-07-24 10:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a8b3c1f6e920'
down_revision: str | None = 'f7a1c2e93d84'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "venta_items",
        sa.Column("detalle", sa.String(length=300), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("venta_items", "detalle")
