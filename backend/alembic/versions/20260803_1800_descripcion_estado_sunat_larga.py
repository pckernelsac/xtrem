"""ampliar descripcion_estado_sunat para los mensajes de Nubefact

Revision ID: c9e5f1b34a27
Revises: b6c4d2a70f18
Create Date: 2026-08-03 18:00:00.000000

FactPro devolvía etiquetas cortas ("ACEPTADO", "REGISTRADO") y 60 caracteres
sobraban. Nubefact devuelve frases completas —"La Factura numero FFF1-1, ha
sido aceptada"— y los mensajes de rechazo de SUNAT son bastante más largos, así
que el INSERT reventaría con un error de longitud justo al emitir.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c9e5f1b34a27'
down_revision: str | None = 'b6c4d2a70f18'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        'comprobantes',
        'descripcion_estado_sunat',
        existing_type=sa.String(length=60),
        type_=sa.String(length=300),
        existing_nullable=True,
    )


def downgrade() -> None:
    # Al estrechar hay que recortar antes: si algún mensaje ya supera los 60
    # caracteres, el ALTER fallaría con "value too long".
    op.execute(
        "UPDATE comprobantes SET descripcion_estado_sunat = LEFT(descripcion_estado_sunat, 60) "
        "WHERE descripcion_estado_sunat IS NOT NULL"
    )
    op.alter_column(
        'comprobantes',
        'descripcion_estado_sunat',
        existing_type=sa.String(length=300),
        type_=sa.String(length=60),
        existing_nullable=True,
    )
