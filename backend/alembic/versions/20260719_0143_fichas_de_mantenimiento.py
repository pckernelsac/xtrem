"""fichas de mantenimiento

Revision ID: d1d86eaa3ddc
Revises: 1f2259bc3de8
Create Date: 2026-07-19 01:43:06.620184
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'd1d86eaa3ddc'
down_revision: str | None = '1f2259bc3de8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Correlativo de ficha. Una secuencia de Postgres es atómica: bajo dos
    # recepciones simultáneas nunca entrega el mismo número, a diferencia de
    # un SELECT MAX(numero)+1.
    op.execute("CREATE SEQUENCE IF NOT EXISTS ficha_numero_seq START 1")

    op.create_table('fichas',
    sa.Column('numero', sa.String(length=20), nullable=False),
    sa.Column('cliente_id', sa.Uuid(), nullable=False),
    sa.Column('bicicleta_id', sa.Uuid(), nullable=False),
    sa.Column('estado', sa.Enum('RECIBIDA', 'EN_REVISION', 'ESPERANDO_REPUESTOS', 'EN_REPARACION', 'LISTA_PARA_ENTREGAR', 'ENTREGADA', 'CANCELADA', name='estado_ficha'), nullable=False),
    sa.Column('fecha_recepcion', sa.DateTime(timezone=True), nullable=False),
    sa.Column('tecnico_recepcion_id', sa.Uuid(), nullable=True),
    sa.Column('canal_referencia', sa.String(length=120), nullable=True),
    sa.Column('servicios', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('servicio_otro', sa.String(length=200), nullable=True),
    sa.Column('diagnostico_inicial', sa.Text(), nullable=True),
    sa.Column('trabajo_realizado', sa.Text(), nullable=True),
    sa.Column('tiempo_invertido_min', sa.Integer(), nullable=True),
    sa.Column('tecnico_responsable_id', sa.Uuid(), nullable=True),
    sa.Column('observaciones', sa.Text(), nullable=True),
    sa.Column('garantia_dias', sa.Integer(), nullable=True),
    sa.Column('fecha_entrega', sa.DateTime(timezone=True), nullable=True),
    sa.Column('tecnico_entrega_id', sa.Uuid(), nullable=True),
    sa.Column('firma_cliente', sa.Text(), nullable=True),
    sa.Column('firma_cliente_dni', sa.String(length=15), nullable=True),
    sa.Column('firma_tecnico', sa.Text(), nullable=True),
    sa.Column('firma_tecnico_dni', sa.String(length=15), nullable=True),
    sa.Column('fecha_firma', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['bicicleta_id'], ['bicicletas.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['cliente_id'], ['clientes.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['tecnico_entrega_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['tecnico_recepcion_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['tecnico_responsable_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_fichas_estado', 'fichas', ['estado'], unique=False)
    op.create_index('ix_fichas_fecha_recepcion', 'fichas', ['fecha_recepcion'], unique=False)
    op.create_index(op.f('ix_fichas_numero'), 'fichas', ['numero'], unique=True)
    op.create_table('ficha_estados_log',
    sa.Column('ficha_id', sa.Uuid(), nullable=False),
    sa.Column('estado_anterior', sa.Enum('RECIBIDA', 'EN_REVISION', 'ESPERANDO_REPUESTOS', 'EN_REPARACION', 'LISTA_PARA_ENTREGAR', 'ENTREGADA', 'CANCELADA', name='estado_ficha'), nullable=True),
    sa.Column('estado_nuevo', sa.Enum('RECIBIDA', 'EN_REVISION', 'ESPERANDO_REPUESTOS', 'EN_REPARACION', 'LISTA_PARA_ENTREGAR', 'ENTREGADA', 'CANCELADA', name='estado_ficha'), nullable=False),
    sa.Column('usuario_id', sa.Uuid(), nullable=True),
    sa.Column('comentario', sa.String(length=300), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['ficha_id'], ['fichas.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['usuario_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ficha_estados_log_ficha_id'), 'ficha_estados_log', ['ficha_id'], unique=False)
    op.create_table('ficha_repuestos',
    sa.Column('ficha_id', sa.Uuid(), nullable=False),
    sa.Column('orden', sa.Integer(), nullable=False),
    sa.Column('cantidad', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('descripcion', sa.String(length=200), nullable=False),
    sa.Column('marca', sa.String(length=80), nullable=True),
    sa.Column('precio_unitario', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['ficha_id'], ['fichas.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ficha_repuestos_ficha_id'), 'ficha_repuestos', ['ficha_id'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    op.execute('DROP SEQUENCE IF EXISTS ficha_numero_seq')
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_ficha_repuestos_ficha_id'), table_name='ficha_repuestos')
    op.drop_table('ficha_repuestos')
    op.drop_index(op.f('ix_ficha_estados_log_ficha_id'), table_name='ficha_estados_log')
    op.drop_table('ficha_estados_log')
    op.drop_index(op.f('ix_fichas_numero'), table_name='fichas')
    op.drop_index('ix_fichas_fecha_recepcion', table_name='fichas')
    op.drop_index('ix_fichas_estado', table_name='fichas')
    op.drop_table('fichas')
    # ### end Alembic commands ###

