"""Cuentas por pagar: que la condicion decida quien es deuda de verdad.

La vista `v_cuentas_pagar` trataba a las cuatro condiciones igual, asi que cualquier
lote sin pagar figuraba como deuda al proveedor. Eso inflaba el total por pagar con
compras que ya se habian pagado y con consignaciones que pueden no deberse nunca.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.usefixtures("engine")


def _lote(conn, codigo: str, condicion: str | None, total: str = "100.00") -> int:
    """Un lote con una linea, sin pagos. `subtotal_calculado_usd` lo pone el trigger."""
    producto = conn.execute(
        text(
            "INSERT INTO productos (nombre, costo_usd, stock, costo, precio_divisa, "
            "precio_bcv, precio_unitario, precio_original, precio_team, precio_revendedor) "
            "VALUES (:n, 10, 0, 0,0,0,0,0,0,0) RETURNING id"
        ),
        {"n": f"Producto {codigo}"},
    ).scalar_one()
    lote = conn.execute(
        text(
            "INSERT INTO lotes_compra (codigo, fecha, condicion) "
            "VALUES (:c, CURRENT_DATE, CAST(:cond AS condicion_compra)) RETURNING id"
        ),
        {"c": codigo, "cond": condicion},
    ).scalar_one()
    conn.execute(
        text(
            "INSERT INTO compras (lote_id, producto_id, descripcion_libre, cantidad, "
            "costo_unitario_usd) VALUES (:l, :p, :d, 1, :t)"
        ),
        {"l": lote, "p": producto, "d": f"Producto {codigo}", "t": Decimal(total)},
    )
    conn.execute(
        text(
            "UPDATE lotes_compra SET subtotal_calculado_usd = :t WHERE id = :l"
        ),
        {"t": Decimal(total), "l": lote},
    )
    return lote


def _fila(conn, lote_id: int):
    return conn.execute(
        text(
            "SELECT condicion, saldo_usd, exigible_usd FROM v_cuentas_pagar "
            "WHERE lote_id = :l"
        ),
        {"l": lote_id},
    ).one_or_none()


def test_una_compra_de_contado_no_es_cuenta_por_pagar(conn):
    """Ya salio del fondo. Si figura con saldo, alguien la paga dos veces."""
    fila = _fila(conn, _lote(conn, "L-CONTADO", "contado"))
    assert fila.saldo_usd == Decimal("100.00"), "el saldo contable sigue siendo la diferencia"
    assert fila.exigible_usd == Decimal("0"), "pero no hay nada que pagarle a nadie"


def test_una_consignacion_no_se_debe_hasta_venderla(conn):
    """Es lo que la distingue del credito: lo que no se vende se devuelve."""
    fila = _fila(conn, _lote(conn, "L-CONSIG", "consignacion"))
    assert fila.exigible_usd == Decimal("0")


def test_una_compra_a_credito_si_es_exigible(conn):
    fila = _fila(conn, _lote(conn, "L-CREDITO", "credito"))
    assert fila.exigible_usd == Decimal("100.00")


def test_un_anticipo_es_exigible_hasta_que_se_pague(conn):
    fila = _fila(conn, _lote(conn, "L-ANTICIPO", "anticipo"))
    assert fila.exigible_usd == Decimal("100.00")


def test_un_lote_sin_condicion_se_trata_como_exigible(conn):
    """Los lotes migrados no dicen en que condicion se compraron.

    Suponer que ya se pagaron es mas peligroso que suponer que no: esconderia una
    deuda real.
    """
    fila = _fila(conn, _lote(conn, "L-VIEJO", None))
    assert fila.exigible_usd == Decimal("100.00")


def test_un_lote_anulado_sale_de_cuentas_por_pagar(conn):
    lote = _lote(conn, "L-ANULADO", "credito")
    assert _fila(conn, lote) is not None
    conn.execute(
        text("UPDATE lotes_compra SET anulada_at = now() WHERE id = :l"), {"l": lote}
    )
    assert _fila(conn, lote) is None, "una compra anulada no se le debe a nadie"


def test_lo_pagado_baja_lo_exigible(conn):
    lote = _lote(conn, "L-PARCIAL", "credito")
    conn.execute(
        text(
            "INSERT INTO pagos_compra (lote_id, fecha, monto_usd, canal) "
            "VALUES (:l, CURRENT_DATE, 40, 'transferencia')"
        ),
        {"l": lote},
    )
    fila = _fila(conn, lote)
    assert fila.exigible_usd == Decimal("60.00")


# --------------------------------------------------- las finanzas del mes (0014)
def _finanzas(conn, mes: str):
    return conn.execute(
        text(
            "SELECT compras_usd, compras_pagadas_usd FROM v_finanzas_mensuales "
            "WHERE mes = CAST(:m AS date)"
        ),
        {"m": mes},
    ).one_or_none()


def test_una_compra_anulada_no_infla_las_compras_del_mes(conn):
    """El agujero que abrio poder anular: la vista no excluia lotes anulados."""
    lote = _lote(conn, "L-FIN", "contado")
    conn.execute(
        text("UPDATE lotes_compra SET fecha = CAST('2026-04-15' AS date) WHERE id = :l"),
        {"l": lote},
    )
    antes = _finanzas(conn, "2026-04-01")
    assert antes is not None and antes.compras_usd == Decimal("100.00")

    conn.execute(
        text("UPDATE lotes_compra SET anulada_at = now() WHERE id = :l"), {"l": lote}
    )
    despues = _finanzas(conn, "2026-04-01")
    assert despues is None or despues.compras_usd == Decimal("0")


def test_lo_pagado_al_proveedor_se_cuenta_en_el_mes_del_pago(conn):
    """Una compra a credito de enero pagada en marzo salio de caja en marzo."""
    lote = _lote(conn, "L-CAJA", "credito")
    conn.execute(
        text("UPDATE lotes_compra SET fecha = CAST('2026-01-10' AS date) WHERE id = :l"),
        {"l": lote},
    )
    conn.execute(
        text(
            "INSERT INTO pagos_compra (lote_id, fecha, monto_usd, canal) "
            "VALUES (:l, CAST('2026-03-05' AS date), 100, 'transferencia')"
        ),
        {"l": lote},
    )
    enero = _finanzas(conn, "2026-01-01")
    marzo = _finanzas(conn, "2026-03-01")
    assert enero.compras_usd == Decimal("100.00"), "la mercancia entro en enero"
    assert enero.compras_pagadas_usd == Decimal("0"), "pero no salio plata en enero"
    assert marzo.compras_pagadas_usd == Decimal("100.00"), "salio en marzo"
