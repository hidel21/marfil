"""Piezas compartidas de los esquemas.

**El dinero viaja como string.** `"359.67"`, no `359.67`. Un float de ida y vuelta
por JSON es exactamente como aparecen los descuadres de un centavo que el panel de
conciliacion tendria que estar detectando, y JavaScript no tiene decimales exactos.
El frontend lo parsea con una libreria de decimales.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from app.core.dinero import cuantizar

#: Monto de dinero. Se serializa como string con 2 decimales, siempre.
Money = Annotated[
    Decimal,
    PlainSerializer(lambda v: f"{cuantizar(v):.2f}" if v is not None else None, return_type=str),
]

#: Tasa de cambio: 8 decimales, tambien como string.
Tasa = Annotated[
    Decimal,
    PlainSerializer(lambda v: f"{v:.8f}".rstrip("0").rstrip(".") if v is not None else None,
                    return_type=str),
]

#: Porcentaje ya en base 1 (0.1667 = 16,67 %).
Porcentaje = Annotated[
    Decimal,
    PlainSerializer(lambda v: f"{v:.4f}" if v is not None else None, return_type=str),
]


class Esquema(BaseModel):
    """Base de todos los esquemas de salida."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class Pagina[T](Esquema):
    items: list[T]
    total: int
    pagina: int = Field(default=1, ge=1)
    por_pagina: int = Field(default=50, ge=1, le=500)

    @property
    def paginas(self) -> int:
        return max(1, -(-self.total // self.por_pagina))


class Drill(Esquema):
    """Como abrir un numero agregado en las filas que lo produjeron.

    Es un contrato, no una convencion: el frontend nunca reimplementa una consulta,
    llama a `endpoint`. Asi el numero de la tarjeta y las filas del detalle no pueden
    discrepar.
    """

    endpoint: str
    params: dict[str, Any] = Field(default_factory=dict)


class Metrica(Esquema):
    """Un numero con todo lo que hace falta para confiar en el.

    `valor` es siempre string y `es_monto` dice como formatearlo. Con una union
    `Money | int` Pydantic coercionaba los conteos a monto y un "14 deudores" salia
    como "14.00": el tipo lo decide el productor del dato, no el serializador.
    """

    clave: str
    etiqueta: str
    valor: str | None = None
    es_monto: bool = True
    moneda: str | None = None
    #: En espanol llano: "Suma de ventas.saldo_usd donde saldo_usd > 0".
    definicion: str
    calculado_at: datetime
    drill: Drill | None = None
    variacion_pct: Porcentaje | None = None


class RangoFechas(Esquema):
    desde: date | None = None
    hasta: date | None = None
