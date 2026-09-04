"""USDT/VES desde el mercado P2P publico de Binance.

dolarapi no publica USDT, y el paralelo no es un sustituto exacto: se mueven juntos
pero no son el mismo precio, y es USDT lo que efectivamente recibe el negocio.

**De donde sale el numero.** El P2P no tiene "una" cotizacion sino un libro de
anuncios. Se toma la *mediana* de los primeros anuncios de venta, no el mejor precio
ni el promedio:

- el mejor precio suele ser un anuncio de volumen minimo irrelevante;
- el promedio lo arrastra cualquier anuncio disparatado que nadie va a tomar;
- la mediana ignora los extremos y es lo mas cercano a "a como esta hoy".

Se filtran ademas los anuncios cuyo minimo por operacion es absurdo para el negocio,
porque cotizan otro mercado.

Es un endpoint interno de Binance, sin contrato publicado: puede cambiar sin aviso.
Por eso el job lo trata como una fuente que puede fallar sin arrastrar a las demas, y
la tasa queda marcada con confianza `media`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from statistics import median

import requests

URL = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
TIEMPO_LIMITE = 20
#: Cuantos anuncios se miran. Suficiente para una mediana estable sin pedir de mas.
ANUNCIOS = 20
#: Anuncios con un minimo por operacion mayor a esto cotizan mayoreo, no el mercado
#: al que accede el negocio. En bolivares.
MINIMO_MAXIMO_ACEPTADO = Decimal("5000000")


@dataclass(frozen=True)
class Cotizacion:
    tipo: str
    fecha: date
    valor: Decimal
    payload: dict


class ErrorTasa(RuntimeError):
    """Binance respondio, pero no con algo que se pueda guardar como tasa."""


def _decimal(bruto: object) -> Decimal | None:
    try:
        valor = Decimal(str(bruto))
    except (InvalidOperation, TypeError):
        return None
    return valor if valor > 0 else None


def cotizacion_usdt() -> Cotizacion:
    """Mediana de los anuncios de venta de USDT contra bolivares."""
    respuesta = requests.post(
        URL,
        json={
            "asset": "USDT",
            "fiat": "VES",
            # SELL: lo que pide quien vende USDT, que es el precio al que el negocio
            # convierte lo que recibe.
            "tradeType": "SELL",
            "page": 1,
            "rows": ANUNCIOS,
            "payTypes": [],
            "publisherType": None,
        },
        headers={"Content-Type": "application/json", "User-Agent": "Marfil/1.0"},
        timeout=TIEMPO_LIMITE,
    )
    respuesta.raise_for_status()
    cuerpo = respuesta.json()
    if not cuerpo.get("success"):
        raise ErrorTasa("Binance respondio sin exito.")

    precios: list[Decimal] = []
    for entrada in cuerpo.get("data") or []:
        anuncio = entrada.get("adv") or {}
        precio = _decimal(anuncio.get("price"))
        if precio is None:
            continue
        minimo = _decimal(anuncio.get("minSingleTransAmount"))
        if minimo is not None and minimo > MINIMO_MAXIMO_ACEPTADO:
            continue
        precios.append(precio)

    if len(precios) < 3:
        raise ErrorTasa(
            f"Solo {len(precios)} anuncios utilizables; muy poco para una mediana fiable."
        )

    valor = Decimal(str(median(sorted(precios)))).quantize(Decimal("0.0001"))
    return Cotizacion(
        tipo="usdt_ve",
        fecha=date.today(),
        valor=valor,
        payload={
            "fuente": "binance_p2p",
            "anuncios_considerados": len(precios),
            "minimo": str(min(precios)),
            "maximo": str(max(precios)),
            "mediana": str(valor),
        },
    )
