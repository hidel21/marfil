"""Dinero: redondeo medio-arriba y reparto exacto de cuotas."""

from decimal import Decimal

import pytest

from app.core.dinero import (
    convertir_a_usd,
    cuantizar,
    es_cero,
    formatear_bs,
    formatear_usd,
    repartir,
)


def test_redondea_medio_hacia_arriba():
    assert cuantizar("0.125") == Decimal("0.13")
    assert cuantizar("0.135") == Decimal("0.14")


def test_convierte_bolivares_a_usd():
    assert convertir_a_usd("7466.56", "637.59") == Decimal("11.71")


def test_convertir_exige_tasa_positiva():
    with pytest.raises(ValueError, match="mayor que cero"):
        convertir_a_usd("100", "0")


def test_epsilon_de_medio_centavo():
    assert es_cero("0.004")
    assert not es_cero("0.006")


@pytest.mark.parametrize(
    ("total", "partes", "esperado"),
    [
        ("90.00", 3, ["30.00", "30.00", "30.00"]),
        ("100.00", 3, ["33.33", "33.33", "33.34"]),
        ("22.00", 2, ["11.00", "11.00"]),
        ("359.67", 1, ["359.67"]),
    ],
)
def test_reparto_de_cuotas_suma_exacto(total, partes, esperado):
    cuotas = repartir(total, partes)
    assert cuotas == [Decimal(v) for v in esperado]
    assert sum(cuotas) == Decimal(total)


def test_formato_de_las_dos_convenciones():
    assert formatear_usd("359.67") == "$359.67"
    assert formatear_bs("15679.22") == "Bs. 15.679,22"
