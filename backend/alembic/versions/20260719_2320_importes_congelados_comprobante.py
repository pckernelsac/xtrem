"""importes congelados en el comprobante

Revision ID: a4e81cc03f76
Revises: f92c4e77a5d1
Create Date: 2026-07-19 23:20:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a4e81cc03f76'
down_revision: str | None = 'f92c4e77a5d1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for columna in ("base_imponible", "igv", "total"):
        op.add_column("comprobantes", sa.Column(columna, sa.Numeric(12, 2), nullable=True))

    # Relleno histórico: los comprobantes cuya venta sigue existiendo se
    # completan con su importe. Los que perdieron la venta quedan en NULL, que
    # es la verdad —el dato no existe— y no un cero que subdeclararía el mes.
    op.execute(
        """
        UPDATE comprobantes c
           SET total = v.total,
               base_imponible = ROUND(v.total / 1.18, 2),
               igv = v.total - ROUND(v.total / 1.18, 2)
          FROM (
                SELECT ve.id,
                       GREATEST(
                           0,
                           COALESCE((
                               SELECT SUM(GREATEST(0, i.cantidad * i.precio_unitario - i.descuento))
                                 FROM venta_items i
                                WHERE i.venta_id = ve.id
                           ), 0) - ve.descuento
                       ) AS total
                  FROM ventas ve
               ) v
         WHERE c.venta_id = v.id
        """
    )


def downgrade() -> None:
    for columna in ("base_imponible", "igv", "total"):
        op.drop_column("comprobantes", columna)
