"""Tipos de columna reutilizables.

Las precisiones están decididas en el plan y no se eligen caso por caso:
- USD  -> NUMERIC(14,2)
- VES  -> NUMERIC(18,2)  (un solo pago ya llega a 18.183,00 contra el techo de 10,2)
- tasa -> NUMERIC(18,8)  (el BCV publica 4+ decimales)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from sqlalchemy import Numeric
from sqlalchemy.orm import mapped_column

MontoUsd = Annotated[Decimal, mapped_column(Numeric(14, 2))]
MontoVes = Annotated[Decimal, mapped_column(Numeric(18, 2))]
Tasa = Annotated[Decimal, mapped_column(Numeric(18, 8))]
Porcentaje = Annotated[Decimal, mapped_column(Numeric(7, 4))]

NUMERIC_USD = Numeric(14, 2)
NUMERIC_VES = Numeric(18, 2)
NUMERIC_TASA = Numeric(18, 8)
NUMERIC_PARAMETRO = Numeric(12, 6)
