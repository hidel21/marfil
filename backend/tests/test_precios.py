"""El guardia de precio. Es la regla que pierde dinero si esta mal.

El informe midio $123 perdidos en 56 dias —26 % de la ganancia— porque 14 ventas
marcadas BCV se cobraron al nivel divisa. Estos tests son el contrato de que eso no
puede volver a pasar en silencio.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errors import (
    CODIGO_COSTO_DESCONOCIDO,
    CODIGO_PRECIO_BAJO_COSTO,
    CODIGO_PRECIO_FUERA_DE_BANDA,
    CODIGO_PRECIO_NIVEL_INCORRECTO,
    CODIGO_PRECIO_SOBRE_POLITICA,
)
from app.services.precios import evaluar_precio, precio_politica

pytestmark = pytest.mark.usefixtures("engine")


@pytest.fixture
def sesion(conn) -> Session:
    """Sesion sobre la conexion del test, para que todo caiga en el mismo rollback."""
    s = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        yield s
    finally:
        s.close()


def _producto(conn, nombre, *, costo=None, original=None, es_original=False):
    modelo = "lista" if original is not None else "costo"
    return conn.execute(
        text(
            "INSERT INTO productos (nombre, es_original, modelo_precio, costo_usd, "
            "precio_original_usd, costo, precio_divisa, precio_bcv, stock, "
            "precio_unitario, precio_original, precio_team, precio_revendedor) "
            "VALUES (:n, :eo, :m, :c, :o, 0,0,0,0,0,0,0,0) RETURNING id"
        ),
        {"n": nombre, "eo": es_original, "m": modelo, "c": costo, "o": original},
    ).scalar_one()


# ------------------------------------------------------------- precio de politica
def test_la_politica_es_sobre_el_costo_no_sobre_la_venta(conn, sesion):
    """+70 % y +120 % se miden sobre el COSTO. Confirmado por el dueno.

    Medidos sobre el precio de venta esos mismos precios serian 41,2 % y 54,5 %,
    pero no es como el negocio los define.
    """
    p = _producto(conn, "Cloud Test", costo=12)
    bcv = precio_politica(sesion, p, moneda_cotizacion="VES")
    divisa = precio_politica(sesion, p, moneda_cotizacion="USD")
    assert bcv.precio_usd == Decimal("26.40"), "12 x 2,20"
    assert divisa.precio_usd == Decimal("20.40"), "12 x 1,70"


def test_la_politica_ofrece_el_nivel_alternativo(conn, sesion):
    """Sin el alternativo no se puede ofrecer 'cambiá el nivel' como salida."""
    p = _producto(conn, "Alternativo Test", costo=12)
    bcv = precio_politica(sesion, p, moneda_cotizacion="VES")
    assert bcv.precio_alternativo_usd == Decimal("20.40")
    assert bcv.nivel_alternativo == "USD"


def test_los_originales_se_calculan_por_descuento(conn, sesion):
    p = _producto(conn, "Original Test", original=50, es_original=True)
    assert precio_politica(sesion, p, moneda_cotizacion="USD",
                           nivel="publico").precio_usd == Decimal("50.00")
    assert precio_politica(sesion, p, moneda_cotizacion="USD",
                           nivel="team").precio_usd == Decimal("37.50"), "50 x 0,75"
    assert precio_politica(sesion, p, moneda_cotizacion="USD",
                           nivel="revendedor").precio_usd == Decimal("42.50"), "50 x 0,85"


def test_sin_costo_no_hay_precio_calculable(conn, sesion):
    p = _producto(conn, "Sin Costo Test")
    assert precio_politica(sesion, p, moneda_cotizacion="VES").calculable is False


# ------------------------------------------------------- LA FUGA: nivel incorrecto
def test_declarar_bcv_y_cobrar_divisa_se_detecta(conn, sesion):
    """El caso exacto del informe, y la linea mas repetida de los datos reales.

    Costo $12: BCV son $26,40 y divisa $20,40. Cobrar $22 esta a $1,60 del nivel
    divisa y a $4,40 del BCV: es una venta divisa mal etiquetada, no un descuento.
    """
    p = _producto(conn, "Fuga Test", costo=12)
    ev = evaluar_precio(
        sesion, producto_id=p, precio_unitario_usd=Decimal("22.00"), moneda_cotizacion="VES"
    )
    assert CODIGO_PRECIO_NIVEL_INCORRECTO in ev.codigos
    assert ev.bloqueada, "no se puede guardar sin resolverlo"

    aviso = next(a for a in ev.advertencias if a.codigo == CODIGO_PRECIO_NIVEL_INCORRECTO)
    assert aviso.detalles["precio_esperado"] == "26.40"
    assert aviso.detalles["precio_del_otro_nivel"] == "20.40"
    assert aviso.detalles["diferencia"] == "4.40"
    assert aviso.detalles["moneda_sugerida"] == "USD", "la salida correcta: cambiar el nivel"


def test_un_descuento_sobre_bcv_no_es_confusion_de_nivel(conn, sesion):
    """$24 esta mas cerca del BCV ($26,40) que del divisa ($20,40): es un descuento."""
    p = _producto(conn, "Descuento Test", costo=12)
    ev = evaluar_precio(
        sesion, producto_id=p, precio_unitario_usd=Decimal("24.00"), moneda_cotizacion="VES"
    )
    assert CODIGO_PRECIO_NIVEL_INCORRECTO not in ev.codigos
    assert CODIGO_PRECIO_FUERA_DE_BANDA in ev.codigos


def test_cobrar_el_precio_de_politica_pasa_sin_ruido(conn, sesion):
    p = _producto(conn, "Correcto Test", costo=12)
    ev = evaluar_precio(
        sesion, producto_id=p, precio_unitario_usd=Decimal("26.40"), moneda_cotizacion="VES"
    )
    assert ev.advertencias == []
    assert not ev.bloqueada


def test_declarar_divisa_y_cobrar_ese_precio_no_bloquea(conn, sesion):
    """La otra salida del panel: cambiar el nivel hace que el registro sea honesto.

    $22 con nivel divisa esta 7,8 % ARRIBA de $20,40: se avisa por si es un tipeo,
    pero no se bloquea. El negocio no pierde nada cobrando de mas.
    """
    p = _producto(conn, "Honesto Test", costo=12)
    ev = evaluar_precio(
        sesion, producto_id=p, precio_unitario_usd=Decimal("22.00"), moneda_cotizacion="USD"
    )
    assert not ev.bloqueada
    assert ev.codigos == [CODIGO_PRECIO_SOBRE_POLITICA]


def test_cobrar_por_encima_nunca_bloquea(conn, sesion):
    """Pedirle a un vendedor que justifique haber vendido bien no tiene sentido."""
    p = _producto(conn, "Arriba Test", costo=12)
    for precio in ("27.00", "30.00", "50.00"):
        ev = evaluar_precio(
            sesion, producto_id=p, precio_unitario_usd=Decimal(precio), moneda_cotizacion="VES"
        )
        assert not ev.bloqueada, f"${precio} no debe bloquear"


def test_un_precio_absurdamente_alto_igual_se_avisa(conn, sesion):
    """$220 en vez de $22 es el tipeo tipico: no bloquea, pero se ve."""
    p = _producto(conn, "Tipeo Test", costo=12)
    ev = evaluar_precio(
        sesion, producto_id=p, precio_unitario_usd=Decimal("220.00"), moneda_cotizacion="VES"
    )
    assert ev.codigos == [CODIGO_PRECIO_SOBRE_POLITICA]
    assert not ev.bloqueada
    assert "tipeo" in ev.advertencias[0].mensaje


def test_un_precio_disparatado_no_se_etiqueta_como_nivel(conn, sesion):
    """$5 sobre un costo de $12 no es 'el nivel divisa': es un error o una perdida."""
    p = _producto(conn, "Disparate Test", costo=12)
    ev = evaluar_precio(
        sesion,
        producto_id=p,
        precio_unitario_usd=Decimal("5.00"),
        costo_unitario_usd=Decimal("12.00"),
        moneda_cotizacion="VES",
    )
    assert CODIGO_PRECIO_NIVEL_INCORRECTO not in ev.codigos
    assert CODIGO_PRECIO_BAJO_COSTO in ev.codigos


# ---------------------------------------------------------------- bajo costo
def test_vender_bajo_costo_bloquea_y_exige_admin(conn, sesion):
    """El caso que el informe marco en rojo: 212 Vip a $9,50 costando $22."""
    p = _producto(conn, "Bajo Costo Test", costo=22)
    ev = evaluar_precio(
        sesion,
        producto_id=p,
        precio_unitario_usd=Decimal("9.50"),
        costo_unitario_usd=Decimal("22.00"),
        moneda_cotizacion="VES",
    )
    aviso = next(a for a in ev.advertencias if a.codigo == CODIGO_PRECIO_BAJO_COSTO)
    assert aviso.bloqueante
    assert aviso.exige_admin, "un vendedor no puede autorizar una perdida"
    assert aviso.detalles["perdida_por_unidad"] == "12.50"


def test_vender_al_costo_exacto_no_es_bajo_costo(conn, sesion):
    """Ganancia cero no es perdida. Hay 3 casos asi en los datos reales."""
    p = _producto(conn, "Al Costo Test", costo=22)
    ev = evaluar_precio(
        sesion,
        producto_id=p,
        precio_unitario_usd=Decimal("22.00"),
        costo_unitario_usd=Decimal("22.00"),
        moneda_cotizacion="VES",
    )
    assert CODIGO_PRECIO_BAJO_COSTO not in ev.codigos


# ------------------------------------------------------------- costo desconocido
def test_sin_costo_se_acepta_pero_se_marca(conn, sesion):
    """177 productos estan asi. Bloquearlos seria bloquear la mitad del catalogo."""
    p = _producto(conn, "Desconocido Test")
    ev = evaluar_precio(
        sesion, producto_id=p, precio_unitario_usd=Decimal("30.00"), moneda_cotizacion="VES"
    )
    assert ev.codigos == [CODIGO_COSTO_DESCONOCIDO]
    assert not ev.bloqueada, "se acepta: es trabajo pendiente, no un error del vendedor"
    assert ev.politica.precio_usd is None


# --------------------------------------------------- los parametros son historicos
def test_el_precio_se_valua_con_los_parametros_de_su_fecha(conn, sesion):
    """Si el dueno sube la ganancia hoy, el margen historico no puede cambiar."""
    p = _producto(conn, "Historico Test", costo=12)
    conn.execute(
        text(
            "UPDATE parametros_precio SET vigencia = daterange('2026-06-01','2026-08-01') "
            "WHERE clave = 'GANANCIA_BCV'"
        )
    )
    conn.execute(
        text(
            "INSERT INTO parametros_precio (clave, valor, vigencia) "
            "VALUES ('GANANCIA_BCV', 1.50, daterange('2026-08-01', NULL))"
        )
    )
    antes = precio_politica(sesion, p, moneda_cotizacion="VES", en_fecha=date(2026, 7, 15))
    despues = precio_politica(sesion, p, moneda_cotizacion="VES", en_fecha=date(2026, 8, 15))
    assert antes.precio_usd == Decimal("26.40"), "12 x 2,20 con la ganancia vieja"
    assert despues.precio_usd == Decimal("30.00"), "12 x 2,50 con la nueva"
