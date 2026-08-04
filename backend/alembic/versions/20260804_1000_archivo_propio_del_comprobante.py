"""guardar el XML firmado y el CDR en la base, y marcar la baja pendiente

Revision ID: e4b8d2c61a95
Revises: d1a7c3e58b46
Create Date: 2026-08-04 10:00:00.000000

Al emitir directo a SUNAT el archivo es nuestro: la respuesta trae el CDR y el
XML lo firmamos aquí. Guardarlos en la base cierra el problema que originó todo
esto —que los PDF vivían en el servidor de un proveedor que dejó de responder— y
cubre la obligación de conservarlos cinco años. El contenedor es desechable, así
que el disco no es sitio.

`baja_pendiente` existe porque anular no es inmediato: las facturas se comunican
en un lote (RA) y las boletas se anulan en el resumen diario con estado 3. Entre
que el usuario anula y SUNAT lo confirma hay un intervalo que hay que poder ver.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e4b8d2c61a95'
down_revision: str | None = 'd1a7c3e58b46'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('comprobantes', sa.Column('xml_firmado', sa.Text(), nullable=True))
    op.add_column('comprobantes', sa.Column('cdr_xml', sa.Text(), nullable=True))
    op.add_column(
        'comprobantes',
        sa.Column(
            'baja_pendiente', sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    # El server_default sólo hacía falta para poder crear la columna NOT NULL
    # sobre una tabla con filas; el modelo pone el valor en los INSERT nuevos.
    op.alter_column('comprobantes', 'baja_pendiente', server_default=None)


def downgrade() -> None:
    op.drop_column('comprobantes', 'baja_pendiente')
    op.drop_column('comprobantes', 'cdr_xml')
    op.drop_column('comprobantes', 'xml_firmado')
