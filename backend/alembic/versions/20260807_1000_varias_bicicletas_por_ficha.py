"""varias bicicletas por ficha

Revision ID: c8f3a2d19e54
Revises: b5e1c937f6a2
Create Date: 2026-08-07 10:00:00.000000

Un cliente deja dos o tres bicicletas a mantenimiento de una sola vez y el
taller las atiende juntas, con un presupuesto y una entrega. La ficha guardaba
una sola (`fichas.bicicleta_id`), asi que el mostrador tenia que abrir un
servicio por maquina y partir el cobro.

El enlace pasa a tabla propia. Cada ficha existente se traslada tal cual: su
bicicleta se convierte en la primera —y unica— fila de la nueva tabla, asi que
ninguna pierde el dato ni cambia de aspecto al imprimirse.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c8f3a2d19e54'
down_revision: str | None = 'b5e1c937f6a2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'ficha_bicicletas',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('ficha_id', sa.UUID(), nullable=False),
        sa.Column('bicicleta_id', sa.UUID(), nullable=False),
        sa.Column('orden', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['ficha_id'], ['fichas.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['bicicleta_id'], ['bicicletas.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ficha_bicicletas_ficha_id', 'ficha_bicicletas', ['ficha_id'])
    op.create_index('ix_ficha_bicicletas_bicicleta_id', 'ficha_bicicletas', ['bicicleta_id'])
    op.create_index(
        'ux_ficha_bicicletas', 'ficha_bicicletas', ['ficha_id', 'bicicleta_id'], unique=True
    )

    # Traslado del dato viejo antes de soltar la columna: si se hiciera al
    # reves, las fichas ya emitidas se quedarian sin su bicicleta.
    op.execute(
        """
        INSERT INTO ficha_bicicletas (id, ficha_id, bicicleta_id, orden)
        SELECT gen_random_uuid(), id, bicicleta_id, 0
        FROM fichas
        WHERE bicicleta_id IS NOT NULL
        """
    )

    op.drop_column('fichas', 'bicicleta_id')


def downgrade() -> None:
    """Vuelve a una bicicleta por ficha.

    Las fichas con varias conservan solo la primera: la columna no da para mas.
    """
    op.add_column('fichas', sa.Column('bicicleta_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fichas_bicicleta_id_fkey', 'fichas', 'bicicletas', ['bicicleta_id'], ['id'],
        ondelete='RESTRICT',
    )
    op.execute(
        """
        UPDATE fichas f
        SET bicicleta_id = (
            SELECT fb.bicicleta_id
            FROM ficha_bicicletas fb
            WHERE fb.ficha_id = f.id
            ORDER BY fb.orden
            LIMIT 1
        )
        """
    )

    op.drop_index('ux_ficha_bicicletas', table_name='ficha_bicicletas')
    op.drop_index('ix_ficha_bicicletas_bicicleta_id', table_name='ficha_bicicletas')
    op.drop_index('ix_ficha_bicicletas_ficha_id', table_name='ficha_bicicletas')
    op.drop_table('ficha_bicicletas')
