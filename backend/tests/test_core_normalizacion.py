"""Normalización: la clave de deduplicación y el teléfono para WhatsApp."""

import pytest

from app.core.normalizacion import (
    TelefonoInvalido,
    clave_nombre,
    normalizar_clave,
    normalizar_nombre,
    telefono_e164,
    telefono_e164_o_none,
)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("AQUA DI GIO", "Aqua di Gio"),
        ("ACQUA  DI   GIO ", "acqua di gio"),
        ("La Bomba", "LA BOMBA"),
        ("Khamrah  Qahwa", "khamrah qahwa"),
        ("Gregor ", "gregor"),
    ],
)
def test_colisionan_las_grafias_del_mismo_nombre(a, b):
    assert normalizar_nombre(a) == normalizar_nombre(b)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("212Vip", "212 vip"),
        ("212 Vip", "212vip"),
        ("ULTRA MALE", "ULTRAMALE"),
        ("EROS MEN", "erosmen"),
    ],
)
def test_la_clave_de_unicidad_ignora_espacios(a, b):
    """La auditoria documenta '212 Vip'/'212 vip'/'212Vip' como el mismo producto."""
    assert clave_nombre(a) == clave_nombre(b)
    assert normalizar_nombre(a) != normalizar_nombre(b)


def test_no_colisionan_nombres_distintos():
    for fn in (normalizar_nombre, clave_nombre):
        assert fn("Gregor") != fn("Gregory")
        assert fn("Ricardo") != fn("Ricardo Palacios")
        # 'Very Good Grul' necesita un alias explicito, no una fusion automatica
        assert fn("Very Good Girl") != fn("Very Good Grul")


def test_producto_numerico_no_se_pierde():
    assert normalizar_nombre("360") == "360"
    assert clave_nombre("360.0") == "3600"


@pytest.mark.parametrize(
    ("encabezado", "esperado"),
    [
        ("COSTO ($)", "costo"),
        ("PRECIO TASA BCV ($)", "precio_tasa_bcv"),
        ("PRECIO DIVISA / USDT ($)", "precio_divisa_usdt"),
        ("N° OPERACIÓN", "n_operacion"),
        ("MONTO Bs P1", "monto_bs_p1"),
        ("PRECIO TASA BCV ($)  +120%", "precio_tasa_bcv_120"),
    ],
)
def test_clave_sin_guiones_colgando(encabezado, esperado):
    """El bug original dejaba 'precio_tasa_bcv_' y 'precio_divisa___usdt_'."""
    assert normalizar_clave(encabezado) == esperado


@pytest.mark.parametrize(
    "entrada",
    ["04121234567", "0412-1234567", "0412 123 4567", "+584121234567", "584121234567", "4121234567"],
)
def test_telefono_a_e164(entrada):
    assert telefono_e164(entrada) == "+584121234567"


@pytest.mark.parametrize("prefijo", ["412", "414", "416", "424", "426"])
def test_acepta_las_cinco_operadoras(prefijo):
    assert telefono_e164(f"0{prefijo}1234567") == f"+58{prefijo}1234567"


@pytest.mark.parametrize(
    "entrada",
    ["02121234567", "0499-1234567", "123", "", None, "04XX-XXX-XXXX", "hola"],
)
def test_rechaza_lo_que_no_es_movil_venezolano(entrada):
    with pytest.raises(TelefonoInvalido):
        telefono_e164(entrada)
    assert telefono_e164_o_none(entrada) is None
