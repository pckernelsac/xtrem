"""token_version en usuarios para invalidar sesiones al cambiar la contraseña

Revision ID: f7a1c2e93d84
Revises: d4e2f8a91c73
Create Date: 2026-07-23 15:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f7a1c2e93d84'
down_revision: str | None = 'd4e2f8a91c73'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
