"""servicio: cobro (mano de obra, adelanto) y bicicleta opcional

Revision ID: d4e2f8a91c73
Revises: c3f1a9d47b02
Create Date: 2026-07-23 12:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'd4e2f8a91c73'
down_revision: str | None = 'c3f1a9d47b02'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # La bicicleta deja de ser obligatoria: un servicio puede ser sólo mano de obra.
    op.alter_column("fichas", "bicicleta_id", existing_type=sa.UUID(), nullable=True)

    # Mano de obra y adelanto, con default en el servidor para las filas ya existentes.
    op.add_column(
        "fichas",
        sa.Column(
            "costo_servicio",
            sa.Numeric(10, 2),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "fichas",
        sa.Column(
            "adelanto",
            sa.Numeric(10, 2),
            nullable=False,
            server_default="0",
        ),
    )
    # Reutiliza el enum metodo_pago ya creado por la migración de ventas y caja;
    # create_type=False evita que alembic intente volver a crear el tipo.
    metodo_pago = postgresql.ENUM(
        "EFECTIVO",
        "YAPE",
        "PLIN",
        "TRANSFERENCIA",
        "TARJETA",
        name="metodo_pago",
        create_type=False,
    )
    op.add_column("fichas", sa.Column("adelanto_metodo", metodo_pago, nullable=True))


def downgrade() -> None:
    op.drop_column("fichas", "adelanto_metodo")
    op.drop_column("fichas", "adelanto")
    op.drop_column("fichas", "costo_servicio")
    op.alter_column("fichas", "bicicleta_id", existing_type=sa.UUID(), nullable=False)
