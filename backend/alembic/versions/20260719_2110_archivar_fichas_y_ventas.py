"""archivar fichas y ventas

Revision ID: f92c4e77a5d1
Revises: e73b2f5a1c48
Create Date: 2026-07-19 21:10:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f92c4e77a5d1'
down_revision: str | None = 'e73b2f5a1c48'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Fecha y no booleano: además de ocultar el documento queda registrado
    # cuándo se sacó del listado, que es lo que se pregunta al revisarlo.
    for tabla in ("fichas", "ventas"):
        op.add_column(tabla, sa.Column("archivada_at", sa.DateTime(timezone=True), nullable=True))
        op.create_index(f"ix_{tabla}_archivada_at", tabla, ["archivada_at"])


def downgrade() -> None:
    for tabla in ("fichas", "ventas"):
        op.drop_index(f"ix_{tabla}_archivada_at", table_name=tabla)
        op.drop_column(tabla, "archivada_at")
