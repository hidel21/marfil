"""Parseo de números en convención venezolana.

Portado textualmente de `parse_numeric_value` de app.py, que está probado contra
los formatos reales del libro: '15.679,22' -> 15679.22, 'Bs. 15.932,00' -> 15932.0,
y —lo más importante— **rechaza** los casos mixtos ('12 EFECTIVO', '18.GM',
'19 usdt P.M') devolviendo None en vez de inventar un número.

Dos diferencias con el original, ambas deliberadas:
- devuelve `Decimal`, no `float`: es dinero;
- no depende de pandas.

Riesgo conocido y conservado: '1.700' -> 1700, porque se asume que 3 decimales son
separador de miles. Correcto para bolívares, equivocado si alguien escribe el
factor 1.700 queriendo decir 1,7.
"""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation

_PREFIJOS_MONEDA = ("$", "Bs.", "bs.", "BS.", "Bs", "bs", "BS", " ", " ")


def _es_vacio(valor: object) -> bool:
    if valor is None:
        return True
    if isinstance(valor, float) and math.isnan(valor):
        return True
    return str(valor).strip() == ""


def parsear_numero(valor: object) -> Decimal | None:
    """None cuando no hay un número limpio. Nunca adivina."""
    if _es_vacio(valor):
        return None
    if isinstance(valor, Decimal):
        return valor if valor.is_finite() else None
    if isinstance(valor, int) and not isinstance(valor, bool):
        return Decimal(valor)
    if isinstance(valor, float):
        return Decimal(str(valor)) if math.isfinite(valor) else None

    texto = str(valor).strip()
    for prefijo in _PREFIJOS_MONEDA:
        texto = texto.replace(prefijo, "")

    if "," in texto and "." in texto:
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif "," in texto:
        entero, decimal = texto.rsplit(",", 1)
        if len(decimal) <= 2:
            texto = f"{entero.replace(',', '')}.{decimal}"
        else:
            texto = texto.replace(",", "")
    elif texto.count(".") > 1:
        entero, decimal = texto.rsplit(".", 1)
        texto = f"{entero.replace('.', '')}.{decimal}"
    elif "." in texto:
        entero, decimal = texto.rsplit(".", 1)
        if len(decimal) == 3:
            texto = entero + decimal

    try:
        numero = Decimal(texto)
    except InvalidOperation:
        return None
    return numero if numero.is_finite() else None


def parsear_entero(valor: object) -> int | None:
    numero = parsear_numero(valor)
    if numero is None:
        return None
    if numero != numero.to_integral_value():
        raise ValueError(f"Se esperaba un número entero y se recibió: {valor!r}")
    return int(numero)
