"""asientos de apertura para el inventario heredado

Evita que el primer movimiento nuevo reemplace el stock legado por la cantidad de ese
único movimiento. Desde esta revisión, todo stock tiene respaldo en el libro.

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        WITH saldos AS (
          SELECT p.id, p.stock, COALESCE(sum(m.cantidad), 0)::integer AS libro
            FROM productos p LEFT JOIN movimientos_stock m ON m.producto_id = p.id
           WHERE p.estado <> 'fusionado'
           GROUP BY p.id, p.stock
        )
        INSERT INTO movimientos_stock
          (producto_id, tipo, cantidad, saldo_despues, referencia_tabla, notas)
        SELECT id, 'carga_inicial', stock - libro, stock, 'migracion_0010',
               'Asiento de apertura para conservar el inventario existente'
          FROM saldos WHERE stock <> libro;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE TEMP TABLE restaurar_stock_0010 ON COMMIT DROP AS
        SELECT producto_id, saldo_despues AS stock
          FROM movimientos_stock WHERE referencia_tabla = 'migracion_0010';
        DELETE FROM movimientos_stock WHERE referencia_tabla = 'migracion_0010';
        UPDATE productos p SET stock = r.stock
          FROM restaurar_stock_0010 r WHERE r.producto_id = p.id;
        """
    )
