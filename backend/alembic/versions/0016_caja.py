"""la caja: el fondo del negocio, movimiento por movimiento

Los socios llevaban a mano un "capital disponible": lo que hay para comprar
mercancia, que sube con cada cobro y baja con cada compra o gasto. El sistema tenia
todas las piezas (el libro de pagos, los gastos, los pagos a proveedor) pero ninguna
pantalla las juntaba en un saldo.

**La caja no es una tabla de saldos, es una vista.** Cobros, gastos y pagos a
proveedor ya viven en su propio libro; copiarlos a una tabla de caja seria tener dos
verdades que pueden discrepar. `v_caja_movimientos` los lee de donde estan, con signo:
lo que entra suma, lo que sale resta. Un reverso de abono ya trae su monto negativo,
asi que corregir un cobro corrige la caja sin hacer nada mas.

**Lo que no tenia donde vivir va en `movimientos_caja`.** Los aportes de capital
(con ellos se pagaron los primeros lotes de junio), los retiros de un socio y el
ajuste de arranque o de cuadre. Sin los aportes, la caja de junio daria negativa:
se compraron 335 $ con 73 $ cobrados.

**No se borra ni se edita: se anula.** Igual que una venta o una compra, un
movimiento cargado por error queda con su motivo y deja de contar. La vista solo ve
los vigentes.

**Las compras anuladas no cuentan**, igual que en `v_finanzas_mensuales`: un lote
cargado por error no saco plata de la caja aunque tenga su pago registrado.

Revision ID: 0016
Revises: 0015
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VISTA = """
CREATE OR REPLACE VIEW v_caja_movimientos AS
SELECT 'pago'::text AS origen, p.id AS origen_id, p.fecha,
       CASE WHEN p.tipo = 'reverso' THEN 'reverso_cobro' ELSE 'cobro' END AS tipo,
       c.nombre || ' · ' || v.codigo AS concepto,
       CASE WHEN p.tipo = 'reverso' THEN p.motivo ELSE p.referencia END AS detalle,
       p.canal::text AS canal, p.moneda::text AS moneda, p.monto_moneda,
       p.monto_usd, p.created_at
  FROM pagos p
  JOIN ventas v ON v.id = p.venta_id
  JOIN clientes c ON c.id = v.cliente_id
UNION ALL
SELECT 'gasto', g.id, g.fecha, 'gasto', g.descripcion, g.categoria,
       g.canal::text, CASE WHEN g.monto_bs IS NOT NULL THEN 'VES' ELSE 'USD' END,
       COALESCE(g.monto_bs, g.monto_usd), -g.monto_usd, g.created_at
  FROM gastos g
UNION ALL
SELECT 'pago_compra', pc.id, pc.fecha, 'compra',
       'Compra ' || l.codigo || COALESCE(' · ' || pr.nombre, ''), pc.referencia,
       pc.canal::text, CASE WHEN pc.monto_bs IS NOT NULL THEN 'VES' ELSE 'USD' END,
       COALESCE(pc.monto_bs, pc.monto_usd), -pc.monto_usd, pc.created_at
  FROM pagos_compra pc
  JOIN lotes_compra l ON l.id = pc.lote_id
  LEFT JOIN proveedores pr ON pr.id = l.proveedor_id
 WHERE l.anulada_at IS NULL
UNION ALL
SELECT 'manual', m.id, m.fecha, m.tipo,
       m.concepto || COALESCE(' · ' || s.nombre, ''), m.notas,
       m.canal, 'USD', abs(m.monto_usd), m.monto_usd, m.created_at
  FROM movimientos_caja m
  LEFT JOIN socios s ON s.id = m.socio_id
 WHERE m.anulado_at IS NULL
"""


def upgrade() -> None:
    op.create_table(
        "movimientos_caja",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("tipo", sa.String(16), nullable=False),
        # Con signo: positivo entra a la caja, negativo sale.
        sa.Column("monto_usd", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "socio_id",
            sa.Integer(),
            sa.ForeignKey("socios.id", name="fk_movimientos_caja_socio_id_socios"),
            nullable=True,
        ),
        sa.Column("concepto", sa.String(300), nullable=False),
        sa.Column("canal", sa.String(32), nullable=True),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column(
            "creado_por_usuario_id",
            sa.Integer(),
            sa.ForeignKey("usuarios.id", name="fk_movimientos_caja_creado_por_usuario_id_usuarios"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("anulado_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "anulado_por_usuario_id",
            sa.Integer(),
            sa.ForeignKey(
                "usuarios.id", name="fk_movimientos_caja_anulado_por_usuario_id_usuarios"
            ),
            nullable=True,
        ),
        sa.Column("motivo_anulacion", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "tipo IN ('aporte', 'retiro', 'ajuste')", name="ck_movimientos_caja_tipo"
        ),
        # El tipo fija el sentido: un aporte siempre entra y un retiro siempre sale. El
        # ajuste va para cualquier lado, pero nunca en cero.
        sa.CheckConstraint(
            "(tipo = 'aporte' AND monto_usd > 0) OR (tipo = 'retiro' AND monto_usd < 0) "
            "OR (tipo = 'ajuste' AND monto_usd <> 0)",
            name="ck_movimientos_caja_signo_segun_tipo",
        ),
        sa.CheckConstraint(
            "anulado_at IS NULL OR motivo_anulacion IS NOT NULL",
            name="ck_movimientos_caja_anulacion_con_motivo",
        ),
    )
    op.create_index("ix_movimientos_caja_fecha", "movimientos_caja", ["fecha"])
    op.execute(
        "CREATE TRIGGER trg_auditar_movimientos_caja AFTER INSERT OR UPDATE OR DELETE "
        "ON movimientos_caja FOR EACH ROW EXECUTE FUNCTION fn_auditar()"
    )
    op.execute(VISTA)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_caja_movimientos")
    op.execute("DROP TRIGGER IF EXISTS trg_auditar_movimientos_caja ON movimientos_caja")
    op.drop_index("ix_movimientos_caja_fecha", table_name="movimientos_caja")
    op.drop_table("movimientos_caja")
