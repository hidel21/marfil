"""Lectura de los parametros de precio vigentes.

Se lee por fecha y no "el actual" porque una venta de hace un mes tiene que valuarse
con los parametros que regian ese dia: si el dueno sube la ganancia hoy, el margen
historico no puede cambiar retroactivamente.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.parametro import (
    CLAVE_DESC_REVENDEDOR,
    CLAVE_DESC_TEAM,
    CLAVE_GANANCIA_BCV,
    CLAVE_GANANCIA_DIVISA,
)

#: Valores de respaldo, con los del libro v2. Solo se usan si falta la fila, que no
#: deberia pasar: 0002 los siembra. Estan para que un parametro faltante no tumbe una
#: venta, y quedan avisados en el resultado.
RESPALDO: dict[str, Decimal] = {
    CLAVE_GANANCIA_DIVISA: Decimal("0.70"),
    CLAVE_GANANCIA_BCV: Decimal("1.20"),
    CLAVE_DESC_TEAM: Decimal("0.25"),
    CLAVE_DESC_REVENDEDOR: Decimal("0.15"),
    "PLAZO_CREDITO_DIAS": Decimal("15"),
    "TOLERANCIA_PRECIO_PCT": Decimal("0.05"),
    "DIAS_POR_VENCER": Decimal("3"),
    "DIAS_MORA_PARA_MOROSO": Decimal("15"),
    "DIAS_ENTRE_RECORDATORIOS": Decimal("7"),
    "MAX_RECORDATORIOS_POR_VENTA_MES": Decimal("4"),
    "TASA_COMISION": Decimal("0.10"),
}


def parametros_vigentes(sesion: Session, en_fecha: date | None = None) -> dict[str, Decimal]:
    """Todos los parametros que rigen en esa fecha, con respaldo para los que falten."""
    fecha = en_fecha or date.today()
    filas = sesion.execute(
        text("SELECT clave, valor FROM parametros_precio WHERE vigencia @> CAST(:f AS date)"),
        {"f": fecha},
    ).all()
    valores = dict(RESPALDO)
    valores.update({clave: valor for clave, valor in filas})
    return valores


def parametro(sesion: Session, clave: str, en_fecha: date | None = None) -> Decimal:
    return parametros_vigentes(sesion, en_fecha).get(clave, RESPALDO.get(clave, Decimal(0)))


def entero(sesion: Session, clave: str, en_fecha: date | None = None) -> int:
    return int(parametro(sesion, clave, en_fecha))
