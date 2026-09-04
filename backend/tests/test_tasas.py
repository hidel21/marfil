"""Las tasas: lo que tiene que valer aunque la fuente cambie.

Nada aca sale a internet. Lo que se prueba es como se interpreta y se guarda lo que
llega, que es donde estan los errores caros: una tasa mal leida convierte mal cada
abono en bolivares de ese dia.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.integrations.tasas import binance, dolarapi

pytestmark = pytest.mark.usefixtures("engine")


# --------------------------------------------------------------------- dolarapi
def test_fecha_acepta_dia_suelto_y_marca_de_tiempo():
    """Las series oficiales traen fecha ISO y las paralelas una marca completa."""
    assert dolarapi._a_fecha("2026-09-04") == date(2026, 9, 4)
    assert dolarapi._a_fecha("2026-09-04T18:01:18.969Z") == date(2026, 9, 4)


@pytest.mark.parametrize("bruto", [None, "", "s/d", 0, -5])
def test_un_valor_no_usable_no_se_guarda_como_tasa(bruto):
    """Cero o negativo no es "sin dato": es una division por cero esperando."""
    with pytest.raises(dolarapi.ErrorTasa):
        dolarapi._a_decimal(bruto, "bcv")


def test_el_valor_conserva_los_decimales_de_la_fuente():
    """Pasa por str y no por float: 807.3862 no puede volverse 807.38619999."""
    assert dolarapi._a_decimal(807.3862, "bcv") == Decimal("807.3862")


def test_todas_las_series_declaradas_tienen_ruta_actual_e_historica():
    for tipo, rutas in dolarapi.SERIES.items():
        assert len(rutas) == 2, tipo
        assert all(r.startswith("/") for r in rutas), tipo


def test_historico_descarta_dias_corruptos_sin_perder_el_resto(monkeypatch):
    """Un dia malo no puede dejar sin historico a los otros ciento sesenta."""
    monkeypatch.setattr(
        dolarapi,
        "_pedir",
        lambda ruta: [
            {"fecha": "2026-01-02", "promedio": 301.37},
            {"fecha": "no-es-fecha", "promedio": 400},
            {"fecha": "2026-01-03", "promedio": None},
            {"fecha": "2026-01-04", "promedio": 310.5},
        ],
    )
    serie = dolarapi.historico("bcv")
    assert [c.fecha.isoformat() for c in serie] == ["2026-01-02", "2026-01-04"]


def test_historico_recorta_por_fecha(monkeypatch):
    monkeypatch.setattr(
        dolarapi,
        "_pedir",
        lambda ruta: [
            {"fecha": "2025-12-31", "promedio": 100},
            {"fecha": "2026-01-02", "promedio": 301.37},
        ],
    )
    serie = dolarapi.historico("bcv", desde=date(2026, 1, 1))
    assert len(serie) == 1


def test_una_serie_caida_no_arrastra_a_las_demas(monkeypatch):
    """La razon de ser de `todas_las_actuales`: el BCV es lo que bloquea cobrar."""

    def falso(tipo: str):
        if tipo == "euro_paralelo":
            raise dolarapi.ErrorTasa("la fuente no respondio")
        return dolarapi.Cotizacion(tipo, date(2026, 9, 4), Decimal("807.3862"), {})

    monkeypatch.setattr(dolarapi, "cotizacion_actual", falso)
    capturadas, fallos = dolarapi.todas_las_actuales()
    assert {c.tipo for c in capturadas} == {"bcv", "paralelo", "euro"}
    assert len(fallos) == 1


# ---------------------------------------------------------------------- binance
def _respuesta(precios, minimo="1000"):
    return {
        "success": True,
        "data": [
            {"adv": {"price": p, "minSingleTransAmount": minimo}} for p in precios
        ],
    }


def test_usdt_usa_la_mediana_y_no_el_mejor_precio(monkeypatch):
    """El anuncio mas barato suele ser de volumen irrelevante; la mediana no."""
    monkeypatch.setattr(
        binance.requests,
        "post",
        lambda *a, **k: type(
            "R", (), {"raise_for_status": lambda s: None,
                      "json": lambda s: _respuesta(["900", "950", "960", "970", "1200"])}
        )(),
    )
    assert binance.cotizacion_usdt().valor == Decimal("960.0000")


def test_se_descartan_los_anuncios_de_mayoreo(monkeypatch):
    """Un minimo de millones cotiza otro mercado, no el del negocio."""
    cuerpo = _respuesta(["950", "955", "960"])
    cuerpo["data"].append({"adv": {"price": "1500", "minSingleTransAmount": "90000000"}})
    monkeypatch.setattr(
        binance.requests,
        "post",
        lambda *a, **k: type(
            "R", (), {"raise_for_status": lambda s: None, "json": lambda s: cuerpo}
        )(),
    )
    assert binance.cotizacion_usdt().valor == Decimal("955.0000")


def test_con_muy_pocos_anuncios_se_falla_en_vez_de_inventar(monkeypatch):
    monkeypatch.setattr(
        binance.requests,
        "post",
        lambda *a, **k: type(
            "R", (), {"raise_for_status": lambda s: None, "json": lambda s: _respuesta(["950"])}
        )(),
    )
    with pytest.raises(binance.ErrorTasa):
        binance.cotizacion_usdt()


# ------------------------------------------------------------------ persistencia
def test_el_enum_admite_las_series_del_euro(conn):
    """La revision 0011 tiene que haber corrido."""
    valores = conn.execute(
        text("SELECT unnest(enum_range(NULL::tipo_tasa))::text")
    ).scalars().all()
    assert {"bcv", "paralelo", "euro", "euro_paralelo", "usdt_ve"} <= set(valores)
    origenes = conn.execute(
        text("SELECT unnest(enum_range(NULL::origen_tasa))::text")
    ).scalars().all()
    assert "api_binance" in origenes


def test_una_correccion_manual_no_la_pisa_la_api(conn):
    """Si un socio arreglo la tasa a mano, el job de mañana no puede deshacerlo."""
    from app.jobs.operativos import SQL_GUARDAR_TASA

    parametros = {
        "f": date(2026, 3, 10),
        "t": "bcv",
        "v": Decimal("111.11"),
        "o": "manual",
        "c": "alta",
        "p": "{}",
    }
    conn.execute(SQL_GUARDAR_TASA, parametros)
    conn.execute(SQL_GUARDAR_TASA, {**parametros, "v": Decimal("999.99"), "o": "api_dolarapi"})

    valor, origen = conn.execute(
        text("SELECT valor, origen::text FROM tasas_cambio WHERE fecha=:f AND tipo='bcv'"),
        {"f": date(2026, 3, 10)},
    ).one()
    assert valor == Decimal("111.11")
    assert origen == "manual"


def test_la_api_si_actualiza_lo_que_ella_misma_puso(conn):
    from app.jobs.operativos import SQL_GUARDAR_TASA

    parametros = {
        "f": date(2026, 3, 11),
        "t": "bcv",
        "v": Decimal("100"),
        "o": "api_dolarapi",
        "c": "alta",
        "p": "{}",
    }
    conn.execute(SQL_GUARDAR_TASA, parametros)
    conn.execute(SQL_GUARDAR_TASA, {**parametros, "v": Decimal("200")})

    valor = conn.execute(
        text("SELECT valor FROM tasas_cambio WHERE fecha=:f AND tipo='bcv'"),
        {"f": date(2026, 3, 11)},
    ).scalar_one()
    assert valor == Decimal("200")
