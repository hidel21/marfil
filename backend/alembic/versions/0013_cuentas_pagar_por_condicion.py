"""cuentas por pagar segun la condicion, sin las compras anuladas

`v_cuentas_pagar` nacio antes de que existiera la condicion de compra, asi que
trataba a las cuatro igual: cualquier lote sin pagar aparecia como deuda al
proveedor. Eso da dos numeros equivocados a la vez.

**Una compra de contado no es una cuenta por pagar.** Ya se pago; si figura con saldo,
el total por pagar sale inflado y alguien va a pagar dos veces.

**Una consignacion tampoco.** La mercancia esta en el negocio pero no se debe hasta
venderla: es lo que la distingue de una compra a credito. Contarla como deuda
adelanta un pasivo que puede no ocurrir nunca, porque lo que no se vende se devuelve.

Se agrega `exigible_usd` en vez de cambiar `saldo_usd`: el saldo sigue siendo la
diferencia contable entre lo comprado y lo pagado —que es la que tiene que cuadrar
contra el libro— y lo exigible es lo que de verdad hay que pagarle a alguien. Dos
preguntas distintas, dos columnas.

Los lotes anulados salen de la vista. Un lote sin condicion (los que venian de antes)
se sigue tratando como exigible: no consta que se haya pagado, y suponer que si es
mas peligroso que suponer que no.

Revision ID: 0013
Revises: 0012
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VISTA_NUEVA = """
CREATE OR REPLACE VIEW v_cuentas_pagar AS
SELECT l.id AS lote_id, l.codigo, l.fecha, p.nombre AS proveedor,
       l.condicion::text AS condicion,
       l.canal::text AS canal,
       l.subtotal_calculado_usd AS total_usd,
       COALESCE(sum(pc.monto_usd), 0) AS pagado_usd,
       greatest(l.subtotal_calculado_usd - COALESCE(sum(pc.monto_usd), 0), 0)
         AS saldo_usd,
       -- Lo que de verdad hay que pagar. `contado` ya salio del fondo y
       -- `consignacion` no se debe hasta vender.
       CASE
         WHEN l.condicion IN ('contado', 'consignacion') THEN 0::numeric
         ELSE greatest(l.subtotal_calculado_usd - COALESCE(sum(pc.monto_usd), 0), 0)
       END AS exigible_usd,
       l.diferencia_usd
  FROM lotes_compra l LEFT JOIN proveedores p ON p.id = l.proveedor_id
  LEFT JOIN pagos_compra pc ON pc.lote_id = l.id
 WHERE l.anulada_at IS NULL
 GROUP BY l.id, l.codigo, l.fecha, p.nombre, l.condicion, l.canal,
          l.subtotal_calculado_usd, l.diferencia_usd;
"""

VISTA_ANTERIOR = """
CREATE OR REPLACE VIEW v_cuentas_pagar AS
SELECT l.id AS lote_id, l.codigo, l.fecha, p.nombre AS proveedor,
       l.subtotal_calculado_usd AS total_usd,
       COALESCE(sum(pc.monto_usd), 0) AS pagado_usd,
       greatest(l.subtotal_calculado_usd - COALESCE(sum(pc.monto_usd), 0), 0)
         AS saldo_usd,
       l.diferencia_usd
  FROM lotes_compra l LEFT JOIN proveedores p ON p.id = l.proveedor_id
  LEFT JOIN pagos_compra pc ON pc.lote_id = l.id
 GROUP BY l.id, l.codigo, l.fecha, p.nombre, l.subtotal_calculado_usd,
          l.diferencia_usd;
"""


def upgrade() -> None:
    # CREATE OR REPLACE no admite agregar columnas al medio, y esta vista gana dos.
    op.execute("DROP VIEW IF EXISTS v_cuentas_pagar")
    op.execute(VISTA_NUEVA)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_cuentas_pagar")
    op.execute(VISTA_ANTERIOR)
