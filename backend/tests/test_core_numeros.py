"""Los formatos reales del libro. Los casos mixtos DEBEN devolver None."""

from decimal import Decimal

import pytest

from app.core.numeros import parsear_entero, parsear_numero


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("15.679,22", Decimal("15679.22")),
        ("8.307,00", Decimal("8307.00")),
        ("$1.234,56", Decimal("1234.56")),
        ("Bs. 15.932,00", Decimal("15932.00")),
        ("1.700", Decimal("1700")),
        ("22", Decimal("22")),
        ("9,50", Decimal("9.50")),
        ("1,234.56", Decimal("1234.56")),
        (Decimal("42.00"), Decimal("42.00")),
        (12, Decimal("12")),
        (9.5, Decimal("9.5")),
    ],
)
def test_parsea_formatos_reales(entrada, esperado):
    assert parsear_numero(entrada) == esperado


@pytest.mark.parametrize(
    "entrada",
    ["12 EFECTIVO", "16 EFECTIVO", "18.GM", "12.GM", "19 usdt P.M", "16 P.M", "listo", "", None],
)
def test_rechaza_en_vez_de_inventar(entrada):
    assert parsear_numero(entrada) is None


def test_parsear_entero_rechaza_fraccion():
    assert parsear_entero("3") == 3
    with pytest.raises(ValueError, match="entero"):
        parsear_entero("3,5")
