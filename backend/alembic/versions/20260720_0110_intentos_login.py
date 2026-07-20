"""intentos de login (freno a la fuerza bruta)

Revision ID: b7d5091ae234
Revises: a4e81cc03f76
Create Date: 2026-07-20 01:10:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b7d5091ae234'
down_revision: str | None = 'a4e81cc03f76'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "intentos_login",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=160), nullable=False),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("exito", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("user_agent", sa.String(length=200), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    # Un índice por cada camino de consulta del bloqueo: por cuenta y por IP.
    op.create_index("ix_intentos_login_email_fecha", "intentos_login", ["email", "created_at"])
    op.create_index("ix_intentos_login_ip_fecha", "intentos_login", ["ip", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_intentos_login_ip_fecha", table_name="intentos_login")
    op.drop_index("ix_intentos_login_email_fecha", table_name="intentos_login")
    op.drop_table("intentos_login")
