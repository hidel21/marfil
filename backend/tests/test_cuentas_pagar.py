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
