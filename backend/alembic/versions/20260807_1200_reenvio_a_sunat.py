"""cola de reenvio cuando sunat no responde

Revision ID: d1a7c46b8f20
Revises: c8f3a2d19e54
Create Date: 2026-08-07 12:00:00.000000

Que SUNAT no conteste no es un rechazo del documento. El comprobante ya esta
emitido y firmado, asi que se queda REGISTRADO con el envio pendiente y se
reintenta con el mismo XML y el mismo correlativo hasta que haya respuesta.

Antes ese caso caia en ERROR: quien atendia volvia a emitir y, cuando SUNAT
regresaba, la serie acababa con dos documentos para el mismo numero.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd1a7c46b8f20'
down_revision: str | None = 'c8f3a2d19e54'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'comprobantes',
        sa.Column(
            'envio_pendiente', sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        'comprobantes',
        sa.Column('intentos_envio', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'comprobantes',
        sa.Column('ultimo_intento_envio', sa.DateTime(timezone=True), nullable=True),
    )

    # La cola se recorre cada pocos minutos y casi siempre esta vacia: parcial,
    # para resolverla sin recorrer la tabla entera.
    op.create_index(
        'ix_comprobantes_envio_pendiente',
        'comprobantes',
        ['envio_pendiente'],
        postgresql_where=sa.text('envio_pendiente'),
    )

    # Los ya emitidos entregaron su CDR en el mismo envio: ninguno esta en cola.
    # El intento cuenta como hecho para que la cifra no arranque en cero.
    op.execute(
        "UPDATE comprobantes SET intentos_envio = 1 WHERE xml_firmado IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_index('ix_comprobantes_envio_pendiente', table_name='comprobantes')
    op.drop_column('comprobantes', 'ultimo_intento_envio')
    op.drop_column('comprobantes', 'intentos_envio')
    op.drop_column('comprobantes', 'envio_pendiente')
