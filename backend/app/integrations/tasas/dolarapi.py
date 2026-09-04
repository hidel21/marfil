"""Cliente de dolarapi.com para Venezuela.

Publica el dolar y el euro, cada uno en su version oficial (BCV) y paralela, con el
ultimo valor de cada dia hacia atras. Es la fuente de referencia del sistema porque
el valor oficial viene del Banco Central y no de un promedio de anuncios.

Lo que la API **no** trae es USDT; para eso esta `binance.py`. Conviene no confundir
paralelo con USDT: se mueven juntos pero no son el mismo precio.

Las rutas de historico no son las que sugiere el indice de la documentacion
(`/v1/dolares/oficial/historico` da 404): cuelgan de `/v1/historicos/`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import requests

BASE = "https://ve.dolarapi.com/v1"
TIEMPO_LIMITE = 20

#: Cada serie de dolarapi contra el `tipo_tasa` con el que se guarda.
SERIES: dict[str, tuple[str, str]] = {
    # tipo_tasa    : (ruta actual,            ruta de historico)
    "bcv": ("/dolares/oficial", "/historicos/dolares/oficial"),
    "paralelo": ("/dolares/paralelo", "/historicos/dolares/paralelo"),
    "euro": ("/euros/oficial", "/historicos/euros/oficial"),
    "euro_paralelo": ("/euros/paralelo", "/historicos/euros/paralelo"),
}


@dataclass(frozen=True)
class Cotizacion:
    tipo: str
    fecha: date
    valor: Decimal
    payload: dict


class ErrorTasa(RuntimeError):
    """La fuente respondio, pero no con algo que se pueda guardar como tasa."""


def _a_decimal(bruto: object, contexto: str) -> Decimal:
    try:
        valor = Decimal(str(bruto))
    except (InvalidOperation, TypeError) as exc:
        raise ErrorTasa(f"{contexto}: valor no numerico ({bruto!r}).") from exc
    if valor <= 0:
        raise ErrorTasa(f"{contexto}: valor no positivo ({valor}).")
    return valor


def _a_fecha(bruto: object) -> date:
    """Acepta '2026-09-04' y '2026-09-04T00:00:00-04:00'."""
    texto = str(bruto)
    try:
        return date.fromisoformat(texto[:10])
    except ValueError as exc:
        raise ErrorTasa(f"Fecha ilegible en la fuente: {bruto!r}.") from exc


def _pedir(ruta: str) -> object:
    respuesta = requests.get(f"{BASE}{ruta}", timeout=TIEMPO_LIMITE)
    respuesta.raise_for_status()
    return respuesta.json()


def cotizacion_actual(tipo: str) -> Cotizacion:
    """Ultimo valor publicado de una serie."""
    if tipo not in SERIES:
        raise ErrorTasa(f"Serie desconocida para dolarapi: {tipo!r}.")
    payload = _pedir(SERIES[tipo][0])
    if not isinstance(payload, dict):
        raise ErrorTasa(f"{tipo}: se esperaba un objeto y llego {type(payload).__name__}.")
    return Cotizacion(
        tipo=tipo,
        # `fechaActualizacion` es del BCV para las oficiales y del scrapeo para las
        # paralelas; se recorta a dia porque la tabla lleva una fila por fecha.
        fecha=_a_fecha(payload.get("fechaActualizacion") or datetime.now().isoformat()),
        valor=_a_decimal(payload.get("promedio"), tipo),
        payload=payload,
    )


def todas_las_actuales() -> tuple[list[Cotizacion], list[str]]:
    """Devuelve lo que se pudo capturar y los fallos, sin abortar por uno.

    Que el euro paralelo falle no es razon para quedarse sin la tasa BCV del dia,
    que es la que realmente bloquea la operacion.
    """
    capturadas: list[Cotizacion] = []
    fallos: list[str] = []
    for tipo in SERIES:
        try:
            capturadas.append(cotizacion_actual(tipo))
        except (requests.RequestException, ErrorTasa) as exc:
            fallos.append(f"{tipo}: {exc}")
    return capturadas, fallos


def historico(tipo: str, desde: date | None = None) -> list[Cotizacion]:
    """Serie diaria hacia atras, opcionalmente recortada por fecha."""
    if tipo not in SERIES:
        raise ErrorTasa(f"Serie desconocida para dolarapi: {tipo!r}.")
    payload = _pedir(SERIES[tipo][1])
    if not isinstance(payload, list):
        raise ErrorTasa(f"{tipo}: el historico no vino como lista.")

    filas: list[Cotizacion] = []
    for entrada in payload:
        if not isinstance(entrada, dict):
            continue
        try:
            fecha = _a_fecha(entrada.get("fecha"))
            valor = _a_decimal(entrada.get("promedio"), tipo)
        except ErrorTasa:
            # Un dia corrupto en el historico se salta; abortar la carga entera por
            # una fila mala dejaria sin historico a las otras series.
            continue
        if desde is not None and fecha < desde:
            continue
        filas.append(Cotizacion(tipo=tipo, fecha=fecha, valor=valor, payload=entrada))
    return filas
