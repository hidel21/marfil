"""Serializacion JSON de la API.

**Garantiza el contrato de "el dinero viaja como string" de forma estructural**, y no
endpoint por endpoint.

Sin esto, un endpoint que devuelve un dict crudo (no un modelo Pydantic) serializa un
`Decimal("68.40")` como el numero `68.4`: se pierde el cero y, peor, del otro lado
queda un float. En JavaScript `0.1 + 0.2 !== 0.3`, asi que un monto que viaja como
numero es exactamente como aparecen los descuadres de un centavo que el panel de
conciliacion tendria que estar detectando.

Con una clase de respuesta por defecto la regla no se puede olvidar: cualquier
Decimal, en cualquier endpoint y a cualquier profundidad, sale como string con dos
decimales.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi.responses import JSONResponse

from app.core.dinero import cuantizar

#: Los Decimal con mas de 2 decimales son tasas, no montos: se preservan enteros.
_MAX_DECIMALES_MONTO = 2


def _serializar(valor: Any) -> Any:
    if isinstance(valor, Decimal):
        exponente = -valor.as_tuple().exponent if valor.as_tuple().exponent < 0 else 0
        if exponente > _MAX_DECIMALES_MONTO:
            # Una tasa: 779.95220000 -> "779.9522", sin ceros de relleno.
            return format(valor.normalize(), "f")
        return f"{cuantizar(valor):.2f}"
    if isinstance(valor, datetime | date | time):
        return valor.isoformat()
    if isinstance(valor, UUID):
        return str(valor)
    raise TypeError(f"No sé serializar {type(valor).__name__}")


def decimal_a_texto(valor: Decimal) -> str:
    """Un Decimal a string. Montos con 2 decimales, tasas con los suyos."""
    exponente = -valor.as_tuple().exponent if valor.as_tuple().exponent < 0 else 0
    if exponente > _MAX_DECIMALES_MONTO:
        return format(valor.normalize(), "f")
    return f"{cuantizar(valor):.2f}"


def instalar_codificador_decimal() -> None:
    """Hace que `jsonable_encoder` de FastAPI convierta Decimal a string.

    Es el punto donde hay que intervenir: FastAPI corre `jsonable_encoder` **antes**
    de entregarle el contenido a la clase de respuesta, y por defecto ese convierte
    Decimal a `float`. Sin esto, la clase de respuesta nunca ve un Decimal y un
    endpoint que devuelve un dict crudo publica `68.4` en vez de `"68.40"`.

    `ENCODERS_BY_TYPE` es el punto de extension publico de FastAPI para esto.
    """
    from fastapi.encoders import ENCODERS_BY_TYPE

    ENCODERS_BY_TYPE[Decimal] = decimal_a_texto


class RespuestaMarfil(JSONResponse):
    """JSONResponse que respeta el contrato del dinero.

    Segunda barrera: si algun camino se saltea `jsonable_encoder`, aca igual no puede
    salir un Decimal como numero.
    """

    def render(self, content: Any) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            default=_serializar,
            separators=(",", ":"),
        ).encode("utf-8")
