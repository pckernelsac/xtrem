"""resumen diario de boletas y comunicacion de baja

Revision ID: f7c2a91e4d38
Revises: e4b8d2c61a95
Create Date: 2026-08-04 12:00:00.000000

Emitir una boleta no la declara: SUNAT sólo la da por informada cuando llega en
un resumen diario, y hay plazo. Esta tabla registra esos envíos.

Se guarda como entidad propia porque el proceso es asíncrono: se manda el lote,
SUNAT devuelve un ticket y el CDR se recoge después. Sin persistir el ticket no
hay forma de saber si lo enviado llegó a declararse.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f7c2a91e4d38'
down_revision: str | None = 'e4b8d2c61a95'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    tipo_lote = sa.Enum('RC', 'RA', name='tipo_lote')
    estado_lote = sa.Enum(
        'PENDIENTE', 'ENVIADO', 'ACEPTADO', 'RECHAZADO', 'ERROR', name='estado_lote'
    )

    op.create_table(
        'lotes_sunat',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tipo', tipo_lote, nullable=False),
        sa.Column('estado', estado_lote, nullable=False),
        sa.Column('identificador', sa.String(length=30), nullable=False),
        sa.Column('fecha_referencia', sa.Date(), nullable=False),
        sa.Column('fecha_emision', sa.Date(), nullable=False),
        sa.Column('correlativo', sa.Integer(), nullable=False),
        sa.Column('ticket', sa.String(length=40), nullable=True),
        sa.Column('codigo_sunat', sa.String(length=10), nullable=True),
        sa.Column('descripcion_sunat', sa.String(length=500), nullable=True),
        sa.Column('mensaje_error', sa.Text(), nullable=True),
        sa.Column('xml_firmado', sa.Text(), nullable=True),
        sa.Column('cdr_xml', sa.Text(), nullable=True),
        sa.Column('es_simulado', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('usuario_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['usuario_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_lotes_sunat_estado', 'lotes_sunat', ['estado'])
    op.create_index('ix_lotes_sunat_ticket', 'lotes_sunat', ['ticket'])
    # Único: SUNAT rechaza un identificador repetido, y repetirlo suele
    # significar que se mandó dos veces lo mismo.
    op.create_index(
        'ux_lotes_sunat_identificador', 'lotes_sunat', ['identificador'], unique=True
    )

    op.add_column('comprobantes', sa.Column('lote_id', sa.UUID(), nullable=True))
    op.create_index('ix_comprobantes_lote_id', 'comprobantes', ['lote_id'])
    op.create_foreign_key(
        'fk_comprobantes_lote', 'comprobantes', 'lotes_sunat', ['lote_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_comprobantes_lote', 'comprobantes', type_='foreignkey')
    op.drop_index('ix_comprobantes_lote_id', table_name='comprobantes')
    op.drop_column('comprobantes', 'lote_id')

    op.drop_index('ux_lotes_sunat_identificador', table_name='lotes_sunat')
    op.drop_index('ix_lotes_sunat_ticket', table_name='lotes_sunat')
    op.drop_index('ix_lotes_sunat_estado', table_name='lotes_sunat')
    op.drop_table('lotes_sunat')

    sa.Enum(name='estado_lote').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='tipo_lote').drop(op.get_bind(), checkfirst=True)
