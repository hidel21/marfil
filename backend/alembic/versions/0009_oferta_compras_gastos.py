"""bloque de proveedores, compras y gastos

Conserva las tablas de Streamlit con sufijo ``_legacy`` y migra sus filas a la forma
canónica. Así el corte es reversible y nunca borra silenciosamente datos del negocio.

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.db.sql import leer_sql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _existe(conexion, tabla: str) -> bool:
    return bool(
        conexion.execute(
            sa.text("SELECT to_regclass(:t) IS NOT NULL"), {"t": f"public.{tabla}"}
        ).scalar()
    )


def _renombrar_legacy(conexion, tabla: str) -> None:
    destino = f"{tabla}_legacy"
    if _existe(conexion, tabla) and not _existe(conexion, destino):
        op.rename_table(tabla, destino)
        secuencia = conexion.execute(
            sa.text("SELECT pg_get_serial_sequence(:t, 'id')"), {"t": destino}
        ).scalar()
        if secuencia:
            nombre = str(secuencia).split(".")[-1]
            esperado = f"{destino}_id_seq"
            if nombre != esperado:
                op.execute(f'ALTER SEQUENCE "{nombre}" RENAME TO "{esperado}"')


def _ajustar_secuencia(tabla: str) -> None:
    op.execute(
        f"SELECT setval(pg_get_serial_sequence('{tabla}', 'id'), "
        f"COALESCE((SELECT max(id) FROM {tabla}), 1), "
        f"EXISTS (SELECT 1 FROM {tabla}))"
    )


def upgrade() -> None:
    conexion = op.get_bind()
    for tabla in ("pagos_compra", "compras", "proveedores", "gastos_generales"):
        _renombrar_legacy(conexion, tabla)

    op.execute(leer_sql("esquema_0009"))
    op.execute(leer_sql("triggers_lotes"))
    op.execute(
        """
        CREATE TRIGGER trg_compras_recalcular_lote
        AFTER INSERT OR UPDATE OR DELETE ON compras
        FOR EACH ROW EXECUTE FUNCTION fn_recalcular_subtotal_lote();
        """
    )

    if _existe(conexion, "proveedores_legacy"):
        op.execute(
            """
            INSERT INTO proveedores
                (id, nombre, nombre_normalizado, contacto, telefono, email, notas, created_at)
            SELECT id, nombre, clave_nombre(nombre), contacto, telefono, email, notas,
                   COALESCE(created_at, now())
              FROM proveedores_legacy
            ON CONFLICT (id) DO NOTHING
            """
        )

    if _existe(conexion, "compras_legacy"):
        op.execute(
            """
            INSERT INTO lotes_compra
                (id, codigo, fecha, proveedor_id, subtotal_declarado_usd, notas, created_at)
            SELECT id, 'LEGACY-COMPRA-' || id, fecha, proveedor_id, monto_total,
                   concat_ws(' · ', 'Migrado desde la compra de Streamlit',
                             CASE WHEN estatus IS NOT NULL THEN 'Estado: ' || estatus END,
                             CASE WHEN referencia IS NOT NULL THEN 'Ref: ' || referencia END),
                   COALESCE(created_at, now())
              FROM compras_legacy
            ON CONFLICT (id) DO NOTHING;

            INSERT INTO compras
                (id, lote_id, producto_id, descripcion_libre, cantidad,
                 costo_unitario_usd, texto_original, created_at)
            SELECT id, id, producto_id, producto_nombre, GREATEST(cantidad, 1),
                   costo_unitario,
                   concat_ws(' · ', 'Proveedor: ' || proveedor_nombre,
                             'Total original: $' || monto_total,
                             'Pagado original: $' || monto_pagado),
                   COALESCE(created_at, now())
              FROM compras_legacy
            ON CONFLICT (id) DO NOTHING
            """
        )

    if _existe(conexion, "pagos_compra_legacy"):
        op.execute(
            """
            INSERT INTO pagos_compra (id, lote_id, fecha, monto_usd, referencia, created_at)
            SELECT p.id, p.compra_id, COALESCE(p.fecha, CURRENT_DATE), p.monto,
                   p.referencia, COALESCE(p.created_at, now())
              FROM pagos_compra_legacy p
              JOIN lotes_compra l ON l.id = p.compra_id
            ON CONFLICT (id) DO NOTHING
            """
        )

    if _existe(conexion, "gastos_generales_legacy"):
        op.execute(
            """
            INSERT INTO gastos (id, fecha, categoria, descripcion, monto_usd, created_at)
            SELECT id, COALESCE(fecha, CURRENT_DATE), categoria,
                   COALESCE(NULLIF(descripcion, ''), categoria), monto,
                   COALESCE(created_at, now())
              FROM gastos_generales_legacy
            ON CONFLICT (id) DO NOTHING
            """
        )

    op.execute(
        """
        UPDATE lotes_compra l SET subtotal_calculado_usd = COALESCE(
          (SELECT sum(cantidad * costo_unitario_usd) FROM compras c WHERE c.lote_id = l.id), 0
        );

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
    )

    for tabla in ("proveedores", "lotes_compra", "compras", "pagos_compra", "gastos"):
        _ajustar_secuencia(tabla)
        op.execute(
            f"CREATE TRIGGER trg_auditar_{tabla} AFTER INSERT OR UPDATE OR DELETE ON {tabla} "
            "FOR EACH ROW EXECUTE FUNCTION fn_auditar()"
        )


def downgrade() -> None:
    conexion = op.get_bind()
    op.execute("DROP VIEW IF EXISTS v_finanzas_mensuales")
    op.execute("DROP VIEW IF EXISTS v_cuentas_pagar")
    op.execute("DROP FUNCTION IF EXISTS fn_recalcular_subtotal_lote() CASCADE")
    for tabla in ("gastos", "pagos_compra", "compras", "lotes_compra", "proveedores"):
        op.execute(f"DROP TABLE IF EXISTS {tabla} CASCADE")
    for original in ("proveedores", "compras", "pagos_compra", "gastos_generales"):
        legacy = f"{original}_legacy"
        if _existe(conexion, legacy):
            op.rename_table(legacy, original)
