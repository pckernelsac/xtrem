"""configuracion de facturacion editable desde la interfaz

Revision ID: a3d9f42b8c17
Revises: f7c2a91e4d38
Create Date: 2026-08-04 14:00:00.000000

Hasta ahora el certificado y las claves SOL venian del entorno, lo que obliga a
tocar el despliegue para cambiarlos. Con esta tabla se cargan desde la
aplicacion, que es lo que hace falta cuando el certificado caduca un sabado.

Fila unica, con identificador fijo: el sistema factura para un solo emisor y asi
no depende de que nadie recuerde no insertar una segunda.

Los secretos van CIFRADOS (ver core/cifrado.py). Aun asi, conviene saber que
estan en la base: quien consiga un backup tiene el material, y por eso el
cifrado se deriva del SECRET_KEY del despliegue.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a3d9f42b8c17'
down_revision: str | None = 'f7c2a91e4d38'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'configuracion_sunat',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('certificado', sa.LargeBinary(), nullable=True),
        sa.Column('certificado_clave', sa.LargeBinary(), nullable=True),
        sa.Column('certificado_nombre', sa.String(length=200), nullable=True),
        sa.Column('certificado_vence', sa.Date(), nullable=True),
        sa.Column('certificado_emitido_a', sa.String(length=300), nullable=True),
        sa.Column('certificado_cargado_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sol_usuario', sa.String(length=60), nullable=True),
        sa.Column('sol_clave', sa.LargeBinary(), nullable=True),
        sa.Column('produccion', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('ruc', sa.String(length=11), nullable=True),
        sa.Column('razon_social', sa.String(length=200), nullable=True),
        sa.Column('nombre_comercial', sa.String(length=200), nullable=True),
        sa.Column('ubigeo', sa.String(length=6), nullable=True),
        sa.Column('direccion', sa.String(length=200), nullable=True),
        sa.Column('departamento', sa.String(length=60), nullable=True),
        sa.Column('provincia', sa.String(length=60), nullable=True),
        sa.Column('distrito', sa.String(length=60), nullable=True),
        sa.Column('serie_factura', sa.String(length=4), nullable=True),
        sa.Column('serie_boleta', sa.String(length=4), nullable=True),
        sa.Column('serie_nc_factura', sa.String(length=4), nullable=True),
        sa.Column('serie_nc_boleta', sa.String(length=4), nullable=True),
        sa.Column('declaracion_automatica', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('actualizado_por_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['actualizado_por_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('configuracion_sunat')
