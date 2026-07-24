from __future__ import annotations

from typing import Tuple

import requests
import streamlit as st

DEFAULT_BCV_USD_RATE = 732.48
DEFAULT_BCV_EUR_RATE = 805.50
DEFAULT_BINANCE_USDT_RATE = 838.00
DEFAULT_USDT_COM_VE_RATE = 870.00
USDT_COM_VE_URL = "https://www.usdt.com.ve/api/v1/rates/current"


def _parse_positive_float(value):
    try:
        number = float(value)
        return number if number > 0 else None
    except Exception:
        return None


@st.cache_data(ttl=1800)
def obtener_todas_las_tasas() -> Tuple[float, float, float, float]:
    """Consultar BCV USD, BCV EUR, Binance USDT y USDT.com.ve con fallback local."""
    tasa_bcv_usd = DEFAULT_BCV_USD_RATE
    tasa_bcv_eur = DEFAULT_BCV_EUR_RATE
    tasa_binance = DEFAULT_BINANCE_USDT_RATE
    tasa_usdt_com_ve = DEFAULT_USDT_COM_VE_RATE

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
        if binance_buy is not None:
            tasa_binance = binance_buy
        if best_buy is not None:
            tasa_usdt_com_ve = best_buy
    except Exception:
        tasa_bcv_usd = DEFAULT_BCV_USD_RATE
        tasa_binance = DEFAULT_BINANCE_USDT_RATE
        tasa_usdt_com_ve = DEFAULT_USDT_COM_VE_RATE

    try:
        response = requests.get("https://pydolarve.org/api/v1/dollar?page=bcv", timeout=5)
        response.raise_for_status()
        data = response.json()
        monedas = data.get("monedas", {})
        eur_data = monedas.get("eur", {})
        if isinstance(eur_data, dict):
            price = _parse_positive_float(eur_data.get("price"))
            if price is not None:
                tasa_bcv_eur = price
    except Exception:
        tasa_bcv_eur = DEFAULT_BCV_EUR_RATE

    return (
        round(tasa_bcv_usd, 2),
        round(tasa_bcv_eur, 2),
        round(tasa_binance, 2),
        round(tasa_usdt_com_ve, 2),
    )


def format_currency(value: float, prefix: str = "Bs. ", decimals: int = 2) -> str:
    return f"{prefix}{value:,.{decimals}f}"
