from __future__ import annotations

from typing import Tuple

import requests
import streamlit as st

DEFAULT_BCV_USD_RATE = 732.48
DEFAULT_BCV_EUR_RATE = 805.50
DEFAULT_BINANCE_USDT_RATE = 838.00
DEFAULT_USDT_COM_VE_RATE = 870.00
USDT_COM_VE_URL = "https://www.usdt.com.ve/api/v1/rates/current"
# Reemplaza a pydolarve.org/api/v1/dollar, que devuelve 404: toda llamada caia al
# fallback y el euro quedaba fijo en el valor hardcodeado.
DOLARAPI_EUR_URL = "https://ve.dolarapi.com/v1/euros"
DOLARAPI_USD_URL = "https://ve.dolarapi.com/v1/dolares"


def _parse_positive_float(value):
    try:
        number = float(value)
        return number if number > 0 else None
    except Exception:
        return None


@st.cache_data(ttl=1800, max_entries=1)
def obtener_tasas_con_estado() -> tuple[Tuple[float, float, float, float], tuple[str, ...]]:
    """Consultar BCV USD, BCV EUR, Binance USDT y USDT.com.ve con fallback local."""
    tasa_bcv_usd = DEFAULT_BCV_USD_RATE
    tasa_bcv_eur = DEFAULT_BCV_EUR_RATE
    tasa_binance = DEFAULT_BINANCE_USDT_RATE
    tasa_usdt_com_ve = DEFAULT_USDT_COM_VE_RATE
    tasas_de_respaldo = {"Dólar BCV", "Euro BCV", "Binance USDT", "USDT.com.ve"}

    try:
        response = requests.get(USDT_COM_VE_URL, timeout=5)
        response.raise_for_status()
        data = response.json()
        payload = data.get("data", {}) if isinstance(data, dict) else {}

        bcv_rate = _parse_positive_float(payload.get("bcv", {}).get("rate"))
        binance_buy = _parse_positive_float(payload.get("binance", {}).get("buy_rate"))
        best_buy = _parse_positive_float(payload.get("best", {}).get("buy_rate"))

        if bcv_rate is not None:
            tasa_bcv_usd = bcv_rate
            tasas_de_respaldo.discard("Dólar BCV")
        if binance_buy is not None:
            tasa_binance = binance_buy
            tasas_de_respaldo.discard("Binance USDT")
        if best_buy is not None:
            tasa_usdt_com_ve = best_buy
            tasas_de_respaldo.discard("USDT.com.ve")
    except Exception:
        tasa_bcv_usd = DEFAULT_BCV_USD_RATE
        tasa_binance = DEFAULT_BINANCE_USDT_RATE
        tasa_usdt_com_ve = DEFAULT_USDT_COM_VE_RATE

    def _oficial(url: str) -> float | None:
        """Toma el 'promedio' de la entrada con fuente 'oficial' de ve.dolarapi.com."""
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        entradas = data if isinstance(data, list) else [data]
        for entrada in entradas:
            if isinstance(entrada, dict) and entrada.get("fuente") == "oficial":
                return _parse_positive_float(entrada.get("promedio"))
        return None

    try:
        price = _oficial(DOLARAPI_EUR_URL)
        if price is not None:
            tasa_bcv_eur = price
            tasas_de_respaldo.discard("Euro BCV")
    except Exception:
        tasa_bcv_eur = DEFAULT_BCV_EUR_RATE

    # Segunda fuente para el BCV en dolares: solo si usdt.com.ve no respondio.
    if "Dólar BCV" in tasas_de_respaldo:
        try:
            price = _oficial(DOLARAPI_USD_URL)
            if price is not None:
                tasa_bcv_usd = price
                tasas_de_respaldo.discard("Dólar BCV")
        except Exception:
            tasa_bcv_usd = DEFAULT_BCV_USD_RATE

    return (
        (
            round(tasa_bcv_usd, 2),
            round(tasa_bcv_eur, 2),
            round(tasa_binance, 2),
            round(tasa_usdt_com_ve, 2),
        ),
        tuple(sorted(tasas_de_respaldo)),
    )


def obtener_todas_las_tasas() -> Tuple[float, float, float, float]:
    tasas, _ = obtener_tasas_con_estado()
    return tasas


def format_currency(value: float, prefix: str = "Bs. ", decimals: int = 2) -> str:
    return f"{prefix}{value:,.{decimals}f}"
