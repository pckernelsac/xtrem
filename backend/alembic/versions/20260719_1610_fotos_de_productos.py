"""fotos de productos

Revision ID: e73b2f5a1c48
Revises: d41f7a3c9e02
Create Date: 2026-07-19 16:10:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e73b2f5a1c48'
down_revision: str | None = 'd41f7a3c9e02'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "productos",
        sa.Column("foto_actualizada_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "producto_fotos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("producto_id", sa.Uuid(), nullable=False),
        sa.Column("contenido", sa.LargeBinary(), nullable=False),
        sa.Column("mime", sa.String(length=40), nullable=False),
        sa.Column(
            "actualizado_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["producto_id"], ["productos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # Una foto por ítem: reemplazar la imagen sustituye la fila.
        sa.UniqueConstraint("producto_id", name="uq_producto_fotos_producto"),
    )


def downgrade() -> None:
    op.drop_table("producto_fotos")
    op.drop_column("productos", "foto_actualizada_at")
