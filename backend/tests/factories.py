"""Semillas mínimas para los tests de esquema.

Escriben con SQL y no con el ORM a propósito: lo que se prueba son las garantías de
la base de datos, y meter el ORM en el medio agregaría una capa que podría estar
tapando lo que se quiere ver.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import text

from app.core.normalizacion import clave_nombre


def crear_usuario(conn, nombre="Gregory", rol="admin", email=None) -> int:
    return conn.execute(
        text(
            "INSERT INTO usuarios (email,nombre,password_hash,rol) "
            "VALUES (:e,:n,'x',:r) RETURNING id"
        ),
        {"e": email or f"{nombre.lower()}@marfil.test", "n": nombre, "r": rol},
    ).scalar_one()


def crear_cliente(conn, nombre="Anderson", telefono=None, **extra) -> int:
    columnas = {"nombre": nombre, "nombre_normalizado": clave_nombre(nombre)}
    if telefono:
        columnas["telefono_e164"] = telefono
    columnas.update(extra)
    cols = ",".join(columnas)
    vals = ",".join(f":{k}" for k in columnas)
    return conn.execute(
        text(f"INSERT INTO clientes ({cols}) VALUES ({vals}) RETURNING id"), columnas
    ).scalar_one()


def crear_producto_legacy(conn, nombre="Cloud", costo=12, stock=5) -> int:
    """`productos` conserva su forma legacy hasta la revisión 0004."""
    return conn.execute(
        text(
            "INSERT INTO productos (nombre,costo,precio_divisa,precio_bcv,stock,"
            "precio_unitario,precio_original,precio_team,precio_revendedor) "
            "VALUES (:n,:c,0,0,:s,0,0,0,0) RETURNING id"
        ),
        {"n": nombre, "c": costo, "s": stock},
    ).scalar_one()


def crear_venta_legacy(conn, **extra) -> int:
    """Venta con la forma legacy de `ventas`.

    Hasta la revisión 0005 la tabla no tiene `codigo`, `cliente_id`,
    `moneda_cotizacion`, `total_usd` ni `fecha_vencimiento`: los tests del saldo y
    del vencimiento llegan con esa revisión, no antes.
    """
    datos = {
        "fecha": extra.get("fecha", date(2026, 8, 1)),
        "cliente": extra.get("cliente", "Anderson"),
        "vendedor": extra.get("vendedor", "Gregory"),
        "producto": extra.get("producto", "Cloud"),
        "cantidad": extra.get("cantidad", 1),
        "precio_venta": extra.get("precio_venta", 22),
        "costo": extra.get("costo", 12),
        "ganancia": extra.get("ganancia", 10),
        "deuda": extra.get("deuda", 22),
        "estatus": extra.get("estatus", "PENDIENTE"),
    }
    datos["total"] = datos["precio_venta"]
    cols = ",".join(datos)
    vals = ",".join(f":{k}" for k in datos)
    return conn.execute(
        text(f"INSERT INTO ventas ({cols},moneda) VALUES ({vals},'BCV') RETURNING id"), datos
    ).scalar_one()


def crear_pago_legacy(conn, venta_id, **extra) -> int:
    """Pago con la forma legacy de `pagos` (monto_bs / tasa_bcv), como lo escribe
    Streamlit hoy. La forma del libro llega en 0006."""
    datos = {
        "venta_id": venta_id,
        "fecha": extra.get("fecha", date(2026, 8, 5)),
        "cliente": extra.get("cliente", "Anderson"),
        "producto": extra.get("producto", "Cloud"),
        "monto_bs": extra.get("monto_bs", 7799.52),
        "monto_usd": extra.get("monto_usd", 10),
        "referencia": extra.get("referencia", "REF-1"),
        "tasa_bcv": extra.get("tasa_bcv", 779.95),
        "nro_cuota": extra.get("nro_cuota", 1),
    }
    cols = ",".join(datos)
    vals = ",".join(f":{k}" for k in datos)
    return conn.execute(
        text(f"INSERT INTO pagos ({cols}) VALUES ({vals}) RETURNING id"), datos
    ).scalar_one()
