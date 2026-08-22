"""Resumen ejecutivo y operativo de la aplicación."""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import text

from app.api.deps import SesionDb, Usuario

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/resumen")
def resumen(db: SesionDb, actual: Usuario, dias: int = Query(default=30, ge=7, le=365)):
    """KPIs, serie diaria y rankings con el mismo contrato para web y móvil."""
    if actual.rol.value == "afiliado":
        metricas = (
            db.execute(
                text(
                    """
                SELECT COALESCE(sum(total_usd), 0) AS ventas_mes_usd,
                       0::numeric AS ganancia_bruta_mes_usd,
                       COALESCE(sum(saldo_usd), 0) AS por_cobrar_usd,
                       count(*) FILTER (WHERE saldo_usd > 0) AS clientes_deudores,
                       0 AS stock_bajo, 0 AS productos_sin_costo,
                       COALESCE(sum(total_usd - saldo_usd), 0) AS cobrado_mes_usd
                  FROM ventas
                 WHERE cliente_id = :cliente AND estado_cobro <> 'anulada'
                   AND date_trunc('month', fecha) = date_trunc('month', CURRENT_DATE)
                """
                ),
                {"cliente": actual.cliente_id},
            )
            .mappings()
            .one()
        )
        condicion, params = (
            "v.cliente_id = :cliente",
            {
                "cliente": actual.cliente_id,
                "dias": dias,
            },
        )
    else:
        metricas = db.execute(text("SELECT * FROM v_dashboard_operativo")).mappings().one()
        condicion, params = "TRUE", {"dias": dias}

    actividad = (
        db.execute(
            text(
                f"""
            WITH dias AS (
              SELECT generate_series(CURRENT_DATE - (:dias - 1), CURRENT_DATE,
                                     interval '1 day')::date AS fecha
            ), vd AS (
              SELECT v.fecha, sum(v.total_usd) AS ventas_usd, count(*) AS ventas
                FROM ventas v WHERE {condicion} AND v.estado_cobro <> 'anulada'
               GROUP BY v.fecha
            ), pd AS (
              SELECT p.fecha, sum(p.monto_usd) AS cobrado_usd
                FROM pagos p JOIN ventas v ON v.id = p.venta_id
               WHERE {condicion} GROUP BY p.fecha
            )
            SELECT d.fecha, COALESCE(vd.ventas_usd, 0) AS ventas_usd,
                   COALESCE(pd.cobrado_usd, 0) AS cobrado_usd,
                   COALESCE(vd.ventas, 0) AS ventas
              FROM dias d LEFT JOIN vd USING (fecha) LEFT JOIN pd USING (fecha)
             ORDER BY d.fecha
            """
            ),
            params,
        )
        .mappings()
        .all()
    )

    top = (
        db.execute(
            text(
                f"""
            SELECT pr.nombre, sum(i.cantidad) AS unidades, sum(i.subtotal_usd) AS ventas_usd
              FROM venta_items i JOIN ventas v ON v.id = i.venta_id
              JOIN productos pr ON pr.id = i.producto_id
             WHERE {condicion} AND v.estado_cobro <> 'anulada'
               AND v.fecha >= CURRENT_DATE - (:dias - 1)
             GROUP BY pr.id, pr.nombre ORDER BY ventas_usd DESC LIMIT 6
            """
            ),
            params,
        )
        .mappings()
        .all()
    )

    recientes = (
        db.execute(
            text(
                f"""
            SELECT v.id, v.codigo, v.fecha, c.nombre AS cliente, v.total_usd,
                   v.saldo_usd, v.estado_cobro::text AS estado
              FROM ventas v JOIN clientes c ON c.id = v.cliente_id
             WHERE {condicion} ORDER BY v.created_at DESC LIMIT 8
            """
            ),
            params,
        )
        .mappings()
        .all()
    )
    return {
        "metricas": dict(metricas),
        "actividad": [dict(f) for f in actividad],
        "top_productos": [dict(f) for f in top],
        "ventas_recientes": [dict(f) for f in recientes],
        "dias": dias,
    }
