"""vistas del panel operativo

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE VIEW v_dashboard_operativo AS
        SELECT
          COALESCE((SELECT sum(total_usd) FROM ventas
                    WHERE estado_cobro <> 'anulada'
                      AND date_trunc('month', fecha) = date_trunc('month', CURRENT_DATE)), 0)
            AS ventas_mes_usd,
          COALESCE((SELECT sum(monto_usd) FROM pagos
                    WHERE date_trunc('month', fecha) = date_trunc('month', CURRENT_DATE)), 0)
            AS cobrado_mes_usd,
          COALESCE((SELECT sum(saldo_usd) FROM ventas
                    WHERE estado_cobro IN ('pendiente_sin_abonos', 'pendiente_parcial')), 0)
            AS por_cobrar_usd,
          (SELECT count(*) FROM v_deuda_cliente WHERE deuda_usd > 0) AS clientes_deudores,
          (SELECT count(*) FROM productos WHERE estado <> 'fusionado' AND stock <= 2)
            AS stock_bajo,
          (SELECT count(*) FROM productos
                    WHERE estado <> 'fusionado' AND costo_usd IS NULL
                      AND precio_original_usd IS NULL) AS productos_sin_costo,
          COALESCE((SELECT sum(total_usd - costo_usd) FROM ventas
                    WHERE estado_cobro <> 'anulada'
                      AND date_trunc('month', fecha) = date_trunc('month', CURRENT_DATE)), 0)
            AS ganancia_bruta_mes_usd;

        CREATE OR REPLACE VIEW v_actividad_diaria AS
        WITH dias AS (
          SELECT generate_series(CURRENT_DATE - 89, CURRENT_DATE, interval '1 day')::date AS fecha
        ), ventas_dia AS (
          SELECT fecha, sum(total_usd) AS ventas_usd, count(*) AS ventas
            FROM ventas WHERE estado_cobro <> 'anulada' GROUP BY fecha
        ), pagos_dia AS (
          SELECT fecha, sum(monto_usd) AS cobrado_usd
            FROM pagos GROUP BY fecha
        )
        SELECT d.fecha, COALESCE(v.ventas_usd, 0) AS ventas_usd,
               COALESCE(p.cobrado_usd, 0) AS cobrado_usd,
               COALESCE(v.ventas, 0) AS ventas
          FROM dias d LEFT JOIN ventas_dia v USING (fecha)
          LEFT JOIN pagos_dia p USING (fecha) ORDER BY d.fecha;

        CREATE OR REPLACE VIEW v_top_productos AS
        SELECT p.id AS producto_id, p.nombre,
               sum(i.cantidad) AS unidades,
               sum(i.subtotal_usd) AS ventas_usd,
               sum(i.subtotal_usd - i.costo_unitario_usd * i.cantidad) AS ganancia_usd
          FROM venta_items i JOIN productos p ON p.id = i.producto_id
          JOIN ventas v ON v.id = i.venta_id
         WHERE v.estado_cobro <> 'anulada'
         GROUP BY p.id, p.nombre;
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_top_productos")
    op.execute("DROP VIEW IF EXISTS v_actividad_diaria")
    op.execute("DROP VIEW IF EXISTS v_dashboard_operativo")
