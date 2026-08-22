"""La capa de compatibilidad: que Streamlit siga vivo durante la convivencia.

Desde la revision 0005 el modelo canonico de una venta es
`ventas` + `venta_items` + `cuotas`, y el saldo lo calcula un trigger desde el libro
de pagos. Pero Streamlit sigue siendo el escritor durante las fases 2 y 3 y escribe
una venta plana. Estos tests comprueban que los triggers traducen esa escritura al
modelo canonico y devuelven el resultado a las columnas viejas.

Se escribe con el mismo SQL que emite `database.py`, a proposito: lo que se prueba es
que la base acepte exactamente lo que la app vieja manda, sin tocar la app vieja.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.usefixtures("engine")

# El INSERT literal de register_sale (database.py:454).
SQL_REGISTER_SALE = text(
    "INSERT INTO ventas (fecha, cliente, vendedor, producto, cantidad, precio_venta, "
    "costo, ganancia, moneda, deuda, estatus, total) "
    "VALUES (:fecha, :cliente, :vendedor, :producto, :cantidad, :precio_venta, :costo, "
    ":ganancia, 'BCV', :deuda, 'PENDIENTE', :precio_venta) RETURNING id"
)

# El INSERT literal de register_payment (database.py:723).
SQL_REGISTER_PAYMENT = text(
    "INSERT INTO pagos (venta_id, fecha, cliente, producto, monto_bs, monto_usd, "
    "referencia, tasa_bcv, nro_cuota) "
    "VALUES (:venta_id, :fecha, :cliente, :producto, :monto_bs, :monto_usd, "
    ":referencia, :tasa_bcv, :nro_cuota) RETURNING id"
)

# El INSERT literal de create_product (database.py:394).
SQL_CREATE_PRODUCT = text(
    "INSERT INTO productos (nombre, categoria, costo, precio_divisa, precio_bcv, stock, "
    "precio_unitario, precio_original, precio_team, precio_revendedor) "
    "VALUES (:nombre, NULL, :costo, :divisa, :bcv, :stock, 0, 0, 0, 0) RETURNING id"
)


def _crear_producto(conn, nombre, costo=10, divisa=17, bcv=22, stock=5):
    return conn.execute(
        SQL_CREATE_PRODUCT,
        {"nombre": nombre, "costo": costo, "divisa": divisa, "bcv": bcv, "stock": stock},
    ).scalar_one()


def _vender(conn, producto, **extra):
    datos = {
        "fecha": extra.get("fecha", date(2026, 8, 20)),
        "cliente": extra.get("cliente", "Cliente Compat"),
        "vendedor": extra.get("vendedor", "Gregor"),
        "producto": producto,
        "cantidad": extra.get("cantidad", 2),
        "precio_venta": extra.get("precio_venta", 44),
        "costo": extra.get("costo", 20),
        "ganancia": extra.get("ganancia", 24),
        "deuda": extra.get("deuda", 44),
    }
    return conn.execute(SQL_REGISTER_SALE, datos).scalar_one()


def _abonar(conn, venta_id, **extra):
    datos = {
        "venta_id": venta_id,
        "fecha": extra.get("fecha", date(2026, 8, 21)),
        "cliente": extra.get("cliente", "Cliente Compat"),
        "producto": extra.get("producto", "Compat"),
        "monto_bs": extra.get("monto_bs", 15599.04),
        "monto_usd": extra.get("monto_usd", 20),
        "referencia": extra.get("referencia", "COMPAT-1"),
        "tasa_bcv": extra.get("tasa_bcv", 779.9522),
        "nro_cuota": extra.get("nro_cuota", 1),
    }
    return conn.execute(SQL_REGISTER_PAYMENT, datos).scalar_one()


def _venta(conn, venta_id):
    return conn.execute(
        text(
            "SELECT codigo, cliente_id, vendedor_usuario_id, moneda_cotizacion::text AS moneda, "
            "total_usd, costo_usd, saldo_usd, estado_cobro::text AS estado, plazo_dias, "
            "fecha_vencimiento, deuda, estatus, total FROM ventas WHERE id = :i"
        ),
        {"i": venta_id},
    ).one()


# --------------------------------------------------------------- venta plana -> canonico
def test_una_venta_plana_se_completa_sola(conn):
    p = _crear_producto(conn, "Compat Completar")
    del p
    v = _vender(conn, "Compat Completar")
    r = _venta(conn, v)

    assert r.codigo.startswith("V-2026-"), "codigo legible asignado"
    assert r.cliente_id is not None, "cliente resuelto o creado"
    assert r.vendedor_usuario_id is not None, "vendedor resuelto"
    assert r.moneda == "VES", "'BCV' significa tasa BCV"
    assert r.plazo_dias == 15, "plazo por defecto del parametro"
    assert r.fecha_vencimiento == date(2026, 8, 20) + timedelta(days=15)


def test_la_linea_se_crea_con_el_texto_tecleado(conn):
    _crear_producto(conn, "Compat Linea")
    v = _vender(conn, "Compat Linea", cantidad=2, precio_venta=44, costo=20)
    linea = conn.execute(
        text(
            "SELECT descripcion_libre, cantidad, precio_unitario_usd, costo_unitario_usd, "
            "subtotal_usd, precio_lista_usd FROM venta_items WHERE venta_id = :i"
        ),
        {"i": v},
    ).one()
    assert linea.descripcion_libre == "Compat Linea"
    assert linea.cantidad == 2
    assert linea.precio_unitario_usd == Decimal("22.00")
    assert linea.costo_unitario_usd == Decimal("10.00")
    assert linea.subtotal_usd == Decimal("44.00")


def test_el_total_y_el_costo_los_calcula_el_trigger(conn):
    _crear_producto(conn, "Compat Totales")
    v = _vender(conn, "Compat Totales", cantidad=2, precio_venta=44, costo=20)
    r = _venta(conn, v)
    assert (r.total_usd, r.costo_usd, r.saldo_usd) == (
        Decimal("44.00"),
        Decimal("20.00"),
        Decimal("44.00"),
    )
    assert r.estado == "pendiente_sin_abonos", "el tercer estado, desde el primer momento"


def test_un_cliente_nuevo_se_crea_en_vez_de_bloquear(conn):
    _crear_producto(conn, "Compat Cliente")
    v = _vender(conn, "Compat Cliente", cliente="  CLIENTA  Recien  Llegada ")
    cliente = conn.execute(
        text(
            "SELECT c.nombre, c.nombre_normalizado FROM ventas v "
            "JOIN clientes c ON c.id = v.cliente_id WHERE v.id = :i"
        ),
        {"i": v},
    ).one()
    assert cliente.nombre_normalizado == "clientarecienllegada"


def test_un_producto_fuera_del_catalogo_entra_como_borrador(conn):
    """El requerimiento explicito: registrar una venta no puede bloquearse."""
    v = _vender(conn, "Perfume Que No Existe En Ningun Lado")
    fila = conn.execute(
        text(
            "SELECT i.descripcion_libre, p.nombre, p.estado::text AS estado, p.origen_alta, "
            "p.costo_usd FROM venta_items i JOIN productos p ON p.id = i.producto_id "
            "WHERE i.venta_id = :i"
        ),
        {"i": v},
    ).one()
    assert fila.descripcion_libre == "Perfume Que No Existe En Ningun Lado"
    assert fila.estado == "borrador_por_revisar"
    assert fila.origen_alta == "venta_rapida"
    assert fila.costo_usd is None, "sin costo inventado: queda para revisar"


def test_se_crea_la_cuota_implicita(conn):
    """Una cuota siempre, con plan o sin plan: un solo camino para la antiguedad."""
    _crear_producto(conn, "Compat Cuota")
    v = _vender(conn, "Compat Cuota", precio_venta=44)
    cuota = conn.execute(
        text(
            "SELECT numero, fecha_vencimiento, monto_usd, implicita "
            "FROM cuotas WHERE venta_id = :i"
        ),
        {"i": v},
    ).one()
    assert (cuota.numero, cuota.monto_usd, cuota.implicita) == (1, Decimal("44.00"), True)


# ------------------------------------------------------------- pago plano -> libro
def test_un_abono_en_bolivares_se_traduce_al_libro(conn):
    _crear_producto(conn, "Compat Abono")
    v = _vender(conn, "Compat Abono")
    _abonar(conn, v, monto_bs=15599.04, monto_usd=20, tasa_bcv=779.9522)

    pago = conn.execute(
        text(
            "SELECT moneda::text AS moneda, monto_moneda, tasa_aplicada, canal::text AS canal, "
            "tipo::text AS tipo, cuota_id, nro_bloque, monto_bs, tasa_bcv "
            "FROM pagos WHERE venta_id = :i"
        ),
        {"i": v},
    ).one()
    assert pago.moneda == "VES"
    assert pago.monto_moneda == Decimal("15599.04")
    assert pago.tasa_aplicada == Decimal("779.95220000"), "sin perder decimales"
    assert pago.canal == "pago_movil"
    assert pago.tipo == "abono"
    assert pago.cuota_id is not None, "el abono se aplica a la cuota abierta"
    assert pago.nro_bloque == 1, "el viejo 'bloque de pago' queda como linaje"
    assert pago.monto_bs == Decimal("15599.04"), "la columna legacy se conserva"


def test_el_saldo_vuelve_a_las_columnas_viejas(conn):
    """12 de las 28 consultas de Streamlit leen `deuda` y `estatus`."""
    _crear_producto(conn, "Compat Espejo")
    v = _vender(conn, "Compat Espejo", precio_venta=44, deuda=44)
    _abonar(conn, v, monto_usd=20)

    r = _venta(conn, v)
    assert r.saldo_usd == Decimal("24.00")
    assert r.deuda == Decimal("24.00"), "el espejo sigue al saldo canonico"
    assert r.estado == "pendiente_parcial"
    assert r.estatus == "PENDIENTE", "el espejo habla el vocabulario que Streamlit entiende"


def test_al_completarse_el_espejo_dice_ya_pago(conn):
    _crear_producto(conn, "Compat Completa")
    v = _vender(conn, "Compat Completa", precio_venta=44, deuda=44)
    _abonar(conn, v, monto_usd=44, referencia="FULL-1")
    r = _venta(conn, v)
    assert (r.saldo_usd, r.estado, r.estatus) == (Decimal("0.00"), "pagada", "YA PAGO")


def test_el_espejo_nunca_escribe_el_tercer_estado(conn):
    """Escribirlo romperia los filtros de Streamlit, que comparan por igualdad exacta."""
    _crear_producto(conn, "Compat Tercer")
    v = _vender(conn, "Compat Tercer")
    r = _venta(conn, v)
    assert r.estado == "pendiente_sin_abonos"
    assert r.estatus in {"PENDIENTE", "YA PAGO"}


def test_el_efectivo_en_dolares_se_detecta_por_la_tasa_1(conn):
    """Era el hack de la app vieja: 28 Bs que nunca fueron bolivares."""
    _crear_producto(conn, "Compat Efectivo")
    v = _vender(conn, "Compat Efectivo", precio_venta=44, deuda=44)
    _abonar(conn, v, monto_bs=24, monto_usd=24, tasa_bcv=1.0, referencia="SIN REFERENCIA")

    pago = conn.execute(
        text(
            "SELECT moneda::text AS moneda, monto_moneda, tasa_aplicada, "
            "canal::text AS canal, referencia FROM pagos WHERE venta_id = :i"
        ),
        {"i": v},
    ).one()
    assert pago.moneda == "USD"
    assert pago.monto_moneda == Decimal("24.00")
    assert pago.tasa_aplicada == Decimal("1.00000000")
    assert pago.canal == "efectivo_usd"
    assert pago.referencia is None, "'SIN REFERENCIA' no es una referencia"


def test_los_dolares_no_contaminan_el_total_en_bolivares(conn):
    _crear_producto(conn, "Compat Mezcla")
    v = _vender(conn, "Compat Mezcla", precio_venta=44, deuda=44)
    _abonar(conn, v, monto_bs=15599.04, monto_usd=20, tasa_bcv=779.9522, referencia="MIX-1")
    _abonar(conn, v, monto_bs=24, monto_usd=24, tasa_bcv=1.0, referencia="MIX-2")

    totales = conn.execute(
        text(
            "SELECT coalesce(sum(monto_moneda) FILTER (WHERE moneda = 'VES'), 0) AS ves, "
            "coalesce(sum(monto_moneda) FILTER (WHERE moneda = 'USD'), 0) AS usd "
            "FROM pagos WHERE venta_id = :i"
        ),
        {"i": v},
    ).one()
    assert totales.ves == Decimal("15599.04")
    assert totales.usd == Decimal("24.00")


# ------------------------------------------------------------------- integridad
def test_el_libro_y_el_saldo_no_se_pueden_desincronizar(conn):
    _crear_producto(conn, "Compat Conciliar")
    v = _vender(conn, "Compat Conciliar", precio_venta=44, deuda=44)
    _abonar(conn, v, monto_usd=10, referencia="C-1")
    _abonar(conn, v, monto_usd=15, referencia="C-2")

    fila = conn.execute(
        text(
            "SELECT v.total_usd, v.saldo_usd, coalesce(sum(p.monto_usd), 0) AS abonado "
            "FROM ventas v LEFT JOIN pagos p ON p.venta_id = v.id "
            "WHERE v.id = :i GROUP BY v.id, v.total_usd, v.saldo_usd"
        ),
        {"i": v},
    ).one()
    assert fila.saldo_usd == fila.total_usd - fila.abonado


def test_una_referencia_repetida_se_rechaza(conn):
    """Contabilizar dos veces la misma transferencia es un error caro y silencioso."""
    from sqlalchemy.exc import IntegrityError

    _crear_producto(conn, "Compat Duplicado")
    v = _vender(conn, "Compat Duplicado", precio_venta=44, deuda=44)
    _abonar(conn, v, monto_bs=1000, monto_usd=10, referencia="REPETIDA")
    with pytest.raises(IntegrityError):
        _abonar(conn, v, monto_bs=1000, monto_usd=10, referencia="REPETIDA")
