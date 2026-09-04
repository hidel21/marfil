"""Jobs idempotentes que también pueden dispararse manualmente."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date

import requests
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import sesion_manual
from app.integrations.tasas import binance, dolarapi


def _registrar(nombre: str, trabajo: Callable[[Session], tuple[int, dict]]) -> dict:
    """Registra inicio/fin/error sin ocultar la excepción al scheduler."""
    with sesion_manual() as sesion:
        ejecucion = sesion.execute(
            text("INSERT INTO jobs_ejecuciones (nombre) VALUES (:n) RETURNING id"),
            {"n": nombre},
        ).scalar_one()
    try:
        with sesion_manual() as sesion:
            filas, detalle = trabajo(sesion)
            sesion.execute(
                text(
                    "UPDATE jobs_ejecuciones SET fin=now(), estado='ok', "
                    "filas_afectadas=:f, detalle=CAST(:d AS jsonb) WHERE id=:i"
                ),
                {"f": filas, "d": json.dumps(detalle, ensure_ascii=False), "i": ejecucion},
            )
        return {
            "ejecucion_id": ejecucion,
            "estado": "ok",
            "filas_afectadas": filas,
            "detalle": detalle,
        }
    except Exception as exc:
        with sesion_manual() as sesion:
            sesion.execute(
                text("UPDATE jobs_ejecuciones SET fin=now(), estado='error', error=:e WHERE id=:i"),
                {"e": f"{type(exc).__name__}: {exc}"[:2000], "i": ejecucion},
            )
        raise


def conciliacion() -> dict:
    def trabajo(sesion: Session) -> tuple[int, dict]:
        detalle, afectadas = {}, 0
        for tipo, vista in {
            "ventas": "v_conciliacion_ventas",
            "pagos": "v_conciliacion_pagos",
            "stock": "v_conciliacion_stock",
        }.items():
            revisadas, malas = sesion.execute(
                text(f"SELECT count(*), count(*) FILTER (WHERE NOT ok) FROM {vista}")
            ).one()
            sesion.execute(
                text(
                    "INSERT INTO conciliaciones "
                    "(tipo, filas_revisadas, filas_descuadradas, ok, detalle) "
                    "VALUES (:t, :r, :m, :ok, CAST(:d AS jsonb))"
                ),
                {
                    "t": tipo,
                    "r": revisadas,
                    "m": malas,
                    "ok": malas == 0,
                    "d": json.dumps({"vista": vista}),
                },
            )
            detalle[tipo] = {"revisadas": revisadas, "descuadradas": malas}
            afectadas += 1
        return afectadas, detalle

    return _registrar("conciliacion", trabajo)


def limpiar_sesiones() -> dict:
    def trabajo(sesion: Session) -> tuple[int, dict]:
        filas = sesion.execute(
            text("DELETE FROM refresh_tokens WHERE expira_at < now() - interval '7 days'")
        ).rowcount
        return filas, {"tokens_expirados_eliminados": filas}

    return _registrar("limpiar_sesiones", trabajo)


SQL_GUARDAR_TASA = text(
    """
    INSERT INTO tasas_cambio (fecha, tipo, valor, origen, confianza, payload)
    VALUES (:f, CAST(:t AS tipo_tasa), :v, CAST(:o AS origen_tasa),
            CAST(:c AS confianza_dato), CAST(:p AS jsonb))
    ON CONFLICT (fecha, tipo) DO UPDATE
       SET valor=EXCLUDED.valor, origen=EXCLUDED.origen,
           confianza=EXCLUDED.confianza, payload=EXCLUDED.payload,
           capturado_at=now()
     -- Una correccion manual gana sobre lo que diga la API: si un socio arreglo la
     -- tasa de un dia a mano, el job de mañana no debe pisarla.
     WHERE tasas_cambio.origen <> 'manual'
    """
)


def snapshot_tasa() -> dict:
    """Captura del dia: las cuatro series de dolarapi mas el USDT de Binance.

    Ninguna fuente puede tumbar a las otras. Que Binance cambie su endpoint no puede
    dejar al negocio sin la tasa BCV, que es la que bloquea cobrar.
    """

    def trabajo(sesion: Session) -> tuple[int, dict]:
        capturadas, fallos = dolarapi.todas_las_actuales()
        guardadas: dict[str, str] = {}
        filas = 0

        for cotizacion in capturadas:
            filas += sesion.execute(
                SQL_GUARDAR_TASA,
                {
                    "f": cotizacion.fecha,
                    "t": cotizacion.tipo,
                    "v": cotizacion.valor,
                    "o": "api_dolarapi",
                    "c": "alta",
                    "p": json.dumps(cotizacion.payload, ensure_ascii=False),
                },
            ).rowcount
            guardadas[cotizacion.tipo] = str(cotizacion.valor)

        try:
            usdt = binance.cotizacion_usdt()
        except (requests.RequestException, binance.ErrorTasa) as exc:
            fallos.append(f"usdt_ve: {exc}")
        else:
            filas += sesion.execute(
                SQL_GUARDAR_TASA,
                {
                    "f": usdt.fecha,
                    "t": usdt.tipo,
                    "v": usdt.valor,
                    "o": "api_binance",
                    # Media y no alta: es una mediana de anuncios de un endpoint sin
                    # contrato publicado, no el valor de un banco central.
                    "c": "media",
                    "p": json.dumps(usdt.payload, ensure_ascii=False),
                },
            ).rowcount
            guardadas[usdt.tipo] = str(usdt.valor)

        if not guardadas:
            raise ValueError(f"Ninguna fuente de tasa respondio. Fallos: {'; '.join(fallos)}")

        return filas, {
            "fecha": date.today().isoformat(),
            "tasas": guardadas,
            "fallos": fallos,
        }

    return _registrar("snapshot_tasa", trabajo)


def backfill_tasas(desde: date | None = None) -> dict:
    """Carga el historico de dolarapi hacia atras. Idempotente: se puede repetir.

    Binance queda fuera a proposito: su P2P solo expone el libro de ahora, no tiene
    historico que rellenar.
    """
    inicio = desde or date(date.today().year, 1, 1)

    def trabajo(sesion: Session) -> tuple[int, dict]:
        detalle: dict[str, object] = {"desde": inicio.isoformat()}
        filas = 0
        for tipo in dolarapi.SERIES:
            try:
                serie = dolarapi.historico(tipo, desde=inicio)
            except (requests.RequestException, dolarapi.ErrorTasa) as exc:
                detalle[tipo] = f"fallo: {exc}"
                continue
            for cotizacion in serie:
                filas += sesion.execute(
                    SQL_GUARDAR_TASA,
                    {
                        "f": cotizacion.fecha,
                        "t": cotizacion.tipo,
                        "v": cotizacion.valor,
                        "o": "api_dolarapi",
                        "c": "alta",
                        "p": json.dumps(cotizacion.payload, ensure_ascii=False),
                    },
                ).rowcount
            detalle[tipo] = len(serie)
        return filas, detalle

    return _registrar("backfill_tasas", trabajo)


JOBS: dict[str, Callable[[], dict]] = {
    "conciliacion": conciliacion,
    "limpiar_sesiones": limpiar_sesiones,
    "snapshot_tasa": snapshot_tasa,
    "backfill_tasas": backfill_tasas,
}


def ejecutar(nombre: str) -> dict:
    trabajo = JOBS.get(nombre)
    if trabajo is None:
        raise KeyError(nombre)
    return trabajo()
