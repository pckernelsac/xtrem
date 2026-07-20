"""ventas y caja

Revision ID: 04c3b1af2303
Revises: daa635063a68
Create Date: 2026-07-19 04:02:32.318763
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '04c3b1af2303'
down_revision: str | None = 'daa635063a68'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Correlativos independientes: las cotizaciones llevan su propia serie,
    # igual que el talonario de proformas en papel.
    op.execute("CREATE SEQUENCE IF NOT EXISTS venta_numero_seq START 1")
    op.execute("CREATE SEQUENCE IF NOT EXISTS cotizacion_numero_seq START 1")
    op.execute("CREATE SEQUENCE IF NOT EXISTS caja_numero_seq START 1")

    op.create_table('sesiones_caja',
    sa.Column('numero', sa.String(length=20), nullable=False),
    sa.Column('estado', sa.Enum('ABIERTA', 'CERRADA', name='estado_caja'), nullable=False),
    sa.Column('monto_inicial', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('fecha_apertura', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('usuario_apertura_id', sa.Uuid(), nullable=True),
    sa.Column('fecha_cierre', sa.DateTime(timezone=True), nullable=True),
    sa.Column('usuario_cierre_id', sa.Uuid(), nullable=True),
    sa.Column('monto_declarado', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('monto_esperado', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('observaciones', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['usuario_apertura_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['usuario_cierre_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_sesiones_caja_estado', 'sesiones_caja', ['estado'], unique=False)
    op.create_index(op.f('ix_sesiones_caja_numero'), 'sesiones_caja', ['numero'], unique=True)
    op.create_table('movimientos_caja',
    sa.Column('sesion_id', sa.Uuid(), nullable=False),
    sa.Column('tipo', sa.Enum('INGRESO', 'EGRESO', name='tipo_movimiento_caja'), nullable=False),
    sa.Column('metodo', sa.Enum('EFECTIVO', 'YAPE', 'PLIN', 'TRANSFERENCIA', 'TARJETA', name='metodo_pago'), nullable=False),
    sa.Column('monto', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('concepto', sa.String(length=200), nullable=False),
    sa.Column('referencia', sa.String(length=80), nullable=True),
    sa.Column('usuario_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['sesion_id'], ['sesiones_caja.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['usuario_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_movimientos_caja_created_at'), 'movimientos_caja', ['created_at'], unique=False)
    op.create_index(op.f('ix_movimientos_caja_metodo'), 'movimientos_caja', ['metodo'], unique=False)
    op.create_index(op.f('ix_movimientos_caja_referencia'), 'movimientos_caja', ['referencia'], unique=False)
    op.create_index(op.f('ix_movimientos_caja_sesion_id'), 'movimientos_caja', ['sesion_id'], unique=False)
    op.create_table('ventas',
    sa.Column('numero', sa.String(length=20), nullable=False),
    sa.Column('tipo', sa.Enum('VENTA', 'COTIZACION', name='tipo_venta'), nullable=False),
    sa.Column('estado', sa.Enum('PENDIENTE', 'CONFIRMADA', 'ANULADA', 'RECHAZADA', name='estado_venta'), nullable=False),
    sa.Column('cliente_id', sa.Uuid(), nullable=True),
    sa.Column('ficha_id', sa.Uuid(), nullable=True),
    sa.Column('sesion_caja_id', sa.Uuid(), nullable=True),
    sa.Column('descuento', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('valido_hasta', sa.Date(), nullable=True),
    sa.Column('notas', sa.Text(), nullable=True),
    sa.Column('usuario_id', sa.Uuid(), nullable=True),
    sa.Column('fecha_anulacion', sa.DateTime(timezone=True), nullable=True),
    sa.Column('motivo_anulacion', sa.String(length=300), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('descuento >= 0', name='ck_ventas_descuento_no_negativo'),
    sa.ForeignKeyConstraint(['cliente_id'], ['clientes.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['ficha_id'], ['fichas.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['sesion_caja_id'], ['sesiones_caja.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['usuario_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ventas_cliente_id'), 'ventas', ['cliente_id'], unique=False)
    op.create_index('ix_ventas_fecha', 'ventas', ['created_at'], unique=False)
    op.create_index(op.f('ix_ventas_ficha_id'), 'ventas', ['ficha_id'], unique=False)
    op.create_index(op.f('ix_ventas_numero'), 'ventas', ['numero'], unique=True)
    op.create_index(op.f('ix_ventas_sesion_caja_id'), 'ventas', ['sesion_caja_id'], unique=False)
    op.create_index('ix_ventas_tipo_estado', 'ventas', ['tipo', 'estado'], unique=False)
    op.create_table('venta_items',
    sa.Column('venta_id', sa.Uuid(), nullable=False),
    sa.Column('orden', sa.Integer(), nullable=False),
    sa.Column('producto_id', sa.Uuid(), nullable=True),
    sa.Column('descripcion', sa.String(length=200), nullable=False),
    sa.Column('cantidad', sa.Numeric(precision=12, scale=3), nullable=False),
    sa.Column('precio_unitario', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('descuento', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['producto_id'], ['productos.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['venta_id'], ['ventas.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_venta_items_producto_id'), 'venta_items', ['producto_id'], unique=False)
    op.create_index(op.f('ix_venta_items_venta_id'), 'venta_items', ['venta_id'], unique=False)
    op.create_table('venta_pagos',
    sa.Column('venta_id', sa.Uuid(), nullable=False),
    sa.Column('metodo', sa.Enum('EFECTIVO', 'YAPE', 'PLIN', 'TRANSFERENCIA', 'TARJETA', name='metodo_pago'), nullable=False),
    sa.Column('monto', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('referencia', sa.String(length=80), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['venta_id'], ['ventas.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_venta_pagos_venta_id'), 'venta_pagos', ['venta_id'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS venta_numero_seq")
    op.execute("DROP SEQUENCE IF EXISTS cotizacion_numero_seq")
    op.execute("DROP SEQUENCE IF EXISTS caja_numero_seq")
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_venta_pagos_venta_id'), table_name='venta_pagos')
    op.drop_table('venta_pagos')
    op.drop_index(op.f('ix_venta_items_venta_id'), table_name='venta_items')
    op.drop_index(op.f('ix_venta_items_producto_id'), table_name='venta_items')
    op.drop_table('venta_items')
    op.drop_index('ix_ventas_tipo_estado', table_name='ventas')
    op.drop_index(op.f('ix_ventas_sesion_caja_id'), table_name='ventas')
    op.drop_index(op.f('ix_ventas_numero'), table_name='ventas')
    op.drop_index(op.f('ix_ventas_ficha_id'), table_name='ventas')
    op.drop_index('ix_ventas_fecha', table_name='ventas')
    op.drop_index(op.f('ix_ventas_cliente_id'), table_name='ventas')
    op.drop_table('ventas')
    op.drop_index(op.f('ix_movimientos_caja_sesion_id'), table_name='movimientos_caja')
    op.drop_index(op.f('ix_movimientos_caja_referencia'), table_name='movimientos_caja')
    op.drop_index(op.f('ix_movimientos_caja_metodo'), table_name='movimientos_caja')
    op.drop_index(op.f('ix_movimientos_caja_created_at'), table_name='movimientos_caja')
    op.drop_table('movimientos_caja')
    op.drop_index(op.f('ix_sesiones_caja_numero'), table_name='sesiones_caja')
    op.drop_index('ix_sesiones_caja_estado', table_name='sesiones_caja')
    op.drop_table('sesiones_caja')
    # ### end Alembic commands ###
