"""Aritmética de dinero. Decimal siempre, float nunca.

`ROUND_HALF_UP` y no el banquero de Python por defecto: es lo que hace el negocio
a mano y lo que hacía el Excel, y una diferencia de medio centavo repetida es
exactamente lo que el panel de conciliación tendría que estar detectando.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENTAVO = Decimal("0.01")
EPSILON = Decimal("0.005")
UNO = Decimal("1")


def a_decimal(valor: object) -> Decimal:
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, float):
        return Decimal(str(valor))
    return Decimal(str(valor or "0"))


def cuantizar(valor: object) -> Decimal:
    """Redondea a 2 decimales, medio hacia arriba."""
    return a_decimal(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def convertir_a_usd(monto_moneda: object, tasa: object) -> Decimal:
    """monto / tasa, cuantizado. La tasa tiene que ser positiva."""
    tasa_dec = a_decimal(tasa)
    if tasa_dec <= 0:
        raise ValueError("La tasa tiene que ser mayor que cero.")
    return cuantizar(a_decimal(monto_moneda) / tasa_dec)


def convertir_a_moneda(monto_usd: object, tasa: object) -> Decimal:
    tasa_dec = a_decimal(tasa)
    if tasa_dec <= 0:
        raise ValueError("La tasa tiene que ser mayor que cero.")
    return cuantizar(a_decimal(monto_usd) * tasa_dec)


def es_cero(valor: object) -> bool:
    """Cero con la tolerancia de medio centavo que ya usaba register_payment."""
    return abs(a_decimal(valor)) < EPSILON


def repartir(total: object, partes: int) -> list[Decimal]:
    """Divide en `partes` cuotas exactas: el resto va a la última.

    repartir('90.00', 3)  -> [30.00, 30.00, 30.00]
    repartir('100.00', 3) -> [33.33, 33.33, 33.34]
    """
    if partes < 1:
        raise ValueError("Hacen falta al menos 1 parte.")
    total_dec = cuantizar(total)
    base = cuantizar(total_dec / partes)
    cuotas = [base] * (partes - 1)
    cuotas.append(cuantizar(total_dec - base * (partes - 1)))
    return cuotas


def formatear_usd(valor: object) -> str:
    return f"${cuantizar(valor):,.2f}"


def formatear_bs(valor: object) -> str:
    """Convención venezolana: punto de miles, coma decimal."""
    crudo = f"{cuantizar(valor):,.2f}"
    return "Bs. " + crudo.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
