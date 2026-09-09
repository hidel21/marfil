"""las compras anuladas salen de las finanzas, y se separa lo que si salio del fondo

Dos correcciones a `v_finanzas_mensuales`.

**Una compra anulada seguia contando.** La vista excluia las ventas anuladas
(`estado_cobro <> 'anulada'`) pero de las compras no habia nada que excluir, porque
hasta la revision 0012 no se podian anular. Ahora que si, un lote cargado por error e
inmediatamente anulado seguia inflando las compras del mes.

**`compras_usd` no es dinero que salio.** Suma todo lo comprado sin mirar la
condicion, asi que mezcla lo que se pago con lo que se debe y con la consignacion, que
puede no pagarse nunca. Para la pregunta "cuanto salio de caja este mes" se agrega
`compras_pagadas_usd`, que suma el libro de pagos al proveedor: lo unico que consta
que se pago de verdad, con su fecha real, que no es la del lote cuando hubo credito.

Se conservan las dos columnas a proposito. `compras_usd` responde "cuanta mercancia
entro" y `compras_pagadas_usd` responde "cuanto salio de caja". Colapsarlas en una
haria imposible una de las dos preguntas.

Revision ID: 0014
Revises: 0013
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CUERPO_COMUN = """
WITH meses AS (
  SELECT date_trunc('month', fecha)::date AS mes FROM ventas
  UNION SELECT date_trunc('month', fecha)::date FROM pagos
  UNION SELECT date_trunc('month', fecha)::date FROM gastos
  UNION SELECT date_trunc('month', fecha)::date FROM lotes_compra WHERE fecha IS NOT NULL
  UNION SELECT date_trunc('month', fecha)::date FROM pagos_compra
), v AS (
  SELECT date_trunc('month', fecha)::date AS mes, sum(total_usd) AS ventas_usd,
         sum(costo_usd) AS costo_vendido_usd
    FROM ventas WHERE estado_cobro <> 'anulada' GROUP BY 1
), p AS (
  SELECT date_trunc('month', fecha)::date AS mes, sum(monto_usd) AS cobrado_usd
    FROM pagos GROUP BY 1
), g AS (
  SELECT date_trunc('month', fecha)::date AS mes, sum(monto_usd) AS gastos_usd
    FROM gastos GROUP BY 1
), c AS (
  SELECT date_trunc('month', l.fecha)::date AS mes,
         sum(co.cantidad * co.costo_unitario_usd) AS compras_usd
    FROM lotes_compra l JOIN compras co ON co.lote_id = l.id
   WHERE l.fecha IS NOT NULL AND l.anulada_at IS NULL GROUP BY 1
), pc AS (
  -- Por la fecha del pago, no la del lote: una compra a credito de enero pagada en
  -- marzo salio de caja en marzo.
  SELECT date_trunc('month', pc.fecha)::date AS mes,
         sum(pc.monto_usd) AS compras_pagadas_usd
    FROM pagos_compra pc JOIN lotes_compra l ON l.id = pc.lote_id
   WHERE l.anulada_at IS NULL GROUP BY 1
)
SELECT m.mes, COALESCE(v.ventas_usd, 0) AS ventas_usd,
       COALESCE(p.cobrado_usd, 0) AS cobrado_usd,
       COALESCE(v.costo_vendido_usd, 0) AS costo_vendido_usd,
       COALESCE(g.gastos_usd, 0) AS gastos_usd,
       COALESCE(c.compras_usd, 0) AS compras_usd,
       COALESCE(pc.compras_pagadas_usd, 0) AS compras_pagadas_usd,
       COALESCE(v.ventas_usd, 0) - COALESCE(v.costo_vendido_usd, 0)
         AS utilidad_bruta_usd,
       COALESCE(v.ventas_usd, 0) - COALESCE(v.costo_vendido_usd, 0)
         - COALESCE(g.gastos_usd, 0) AS utilidad_neta_usd
  FROM meses m LEFT JOIN v USING (mes) LEFT JOIN p USING (mes)
  LEFT JOIN g USING (mes) LEFT JOIN c USING (mes) LEFT JOIN pc USING (mes)
 ORDER BY m.mes;
"""

VISTA_ANTERIOR = """
CREATE OR REPLACE VIEW v_finanzas_mensuales AS
WITH meses AS (
  SELECT date_trunc('month', fecha)::date AS mes FROM ventas
  UNION SELECT date_trunc('month', fecha)::date FROM pagos
  UNION SELECT date_trunc('month', fecha)::date FROM gastos
  UNION SELECT date_trunc('month', fecha)::date FROM lotes_compra WHERE fecha IS NOT NULL
), v AS (
  SELECT date_trunc('month', fecha)::date AS mes, sum(total_usd) AS ventas_usd,
         sum(costo_usd) AS costo_vendido_usd
    FROM ventas WHERE estado_cobro <> 'anulada' GROUP BY 1
), p AS (
  SELECT date_trunc('month', fecha)::date AS mes, sum(monto_usd) AS cobrado_usd
    FROM pagos GROUP BY 1
), g AS (
  SELECT date_trunc('month', fecha)::date AS mes, sum(monto_usd) AS gastos_usd
    FROM gastos GROUP BY 1
), c AS (
  SELECT date_trunc('month', l.fecha)::date AS mes,
         sum(co.cantidad * co.costo_unitario_usd) AS compras_usd
    FROM lotes_compra l JOIN compras co ON co.lote_id = l.id
   WHERE l.fecha IS NOT NULL GROUP BY 1
)
SELECT m.mes, COALESCE(v.ventas_usd, 0) AS ventas_usd,
       COALESCE(p.cobrado_usd, 0) AS cobrado_usd,
       COALESCE(v.costo_vendido_usd, 0) AS costo_vendido_usd,
       COALESCE(g.gastos_usd, 0) AS gastos_usd,
       COALESCE(c.compras_usd, 0) AS compras_usd,
       COALESCE(v.ventas_usd, 0) - COALESCE(v.costo_vendido_usd, 0)
         AS utilidad_bruta_usd,
       COALESCE(v.ventas_usd, 0) - COALESCE(v.costo_vendido_usd, 0)
         - COALESCE(g.gastos_usd, 0) AS utilidad_neta_usd
  FROM meses m LEFT JOIN v USING (mes) LEFT JOIN p USING (mes)
  LEFT JOIN g USING (mes) LEFT JOIN c USING (mes) ORDER BY m.mes;
"""


def upgrade() -> None:
    # Gana una columna, asi que CREATE OR REPLACE no alcanza.
    op.execute("DROP VIEW IF EXISTS v_finanzas_mensuales")
    op.execute(f"CREATE VIEW v_finanzas_mensuales AS {CUERPO_COMUN}")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_finanzas_mensuales")
    op.execute(VISTA_ANTERIOR)
