"""tipo producto o servicio

Revision ID: d41f7a3c9e02
Revises: c0ca8dcbbeb1
Create Date: 2026-07-19 15:20:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd41f7a3c9e02'
down_revision: str | None = 'c0ca8dcbbeb1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

tipo_item = sa.Enum("PRODUCTO", "SERVICIO", name="tipo_item")


def upgrade() -> None:
    tipo_item.create(op.get_bind(), checkfirst=True)
    # Todo lo ya catalogado nació como producto de almacén; el server_default
    # deja las filas existentes en PRODUCTO sin necesidad de un UPDATE aparte.
    op.add_column(
        "productos",
        sa.Column("tipo", tipo_item, nullable=False, server_default="PRODUCTO"),
    )
    op.create_index("ix_productos_tipo", "productos", ["tipo"])


def downgrade() -> None:
    op.drop_index("ix_productos_tipo", table_name="productos")
    op.drop_column("productos", "tipo")
    tipo_item.drop(op.get_bind(), checkfirst=True)
