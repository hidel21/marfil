"""Jobs idempotentes que también pueden dispararse manualmente."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal, InvalidOperation

import requests
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import obtener_settings
from app.db.session import sesion_manual


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
                    "filas_afectadas=:f, detalle=:d WHERE id=:i"
                ),
                {"f": filas, "d": detalle, "i": ejecucion},
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
                    "VALUES (:t, :r, :m, :ok, :d)"
                ),
                {"t": tipo, "r": revisadas, "m": malas, "ok": malas == 0, "d": {"vista": vista}},
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


def snapshot_tasa() -> dict:
    settings = obtener_settings()

    def trabajo(sesion: Session) -> tuple[int, dict]:
        respuesta = requests.get(settings.tasa_api_url, timeout=15)
        respuesta.raise_for_status()
        payload = respuesta.json()
        candidatos = ("promedio", "precio", "valor", "price", "rate")
        bruto = next((payload.get(k) for k in candidatos if payload.get(k) is not None), None)
        try:
            valor = Decimal(str(bruto))
        except (InvalidOperation, TypeError) as exc:
            raise ValueError("La API de tasa no devolvió un valor reconocible.") from exc
        if valor <= 0:
            raise ValueError("La API de tasa devolvió un valor no positivo.")
        filas = sesion.execute(
            text(
                """
                INSERT INTO tasas_cambio (fecha, tipo, valor, origen, confianza, payload)
                VALUES (:f, 'bcv', :v, 'api_dolarapi', 'alta', :p)
                ON CONFLICT (fecha, tipo) DO UPDATE
                   SET valor=EXCLUDED.valor, origen=EXCLUDED.origen,
                       confianza=EXCLUDED.confianza, payload=EXCLUDED.payload,
                       capturado_at=now()
                """
            ),
            {"f": date.today(), "v": valor, "p": payload},
        ).rowcount
        return filas, {
            "fecha": date.today().isoformat(),
            "valor": str(valor),
            "fuente": settings.tasa_api_url,
        }

    return _registrar("snapshot_tasa", trabajo)


JOBS: dict[str, Callable[[], dict]] = {
    "conciliacion": conciliacion,
    "limpiar_sesiones": limpiar_sesiones,
    "snapshot_tasa": snapshot_tasa,
}


def ejecutar(nombre: str) -> dict:
    trabajo = JOBS.get(nombre)
    if trabajo is None:
        raise KeyError(nombre)
    return trabajo()
