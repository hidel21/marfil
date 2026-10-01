"""Tasas al dia sin depender del cron.

La captura diaria la dispara un workflow de GitHub Actions que necesita secretos
configurados. Si nadie los configura —paso: tres semanas con la tasa del 4 de
septiembre— cada abono en bolivares se convierte con una tasa vieja, y como la tasa se
congela en el pago, el error queda para siempre.

Este modulo hace que la app se ocupe sola: cuando alguien pide la tasa para cargar un
abono, o cuando el servidor arranca, si la ultima BCV no es de hoy se trae lo que
falte. En el plan gratuito eso coincide con el momento justo: el servidor duerme hasta
que alguien lo usa, y quien lo despierta es quien va a necesitar la tasa.

Dos frenos para no castigar a dolarapi ni demorar a nadie:
- a lo sumo un intento por hora por proceso (los fines de semana el BCV no publica, y
  la ultima tasa nunca va a ser "de hoy");
- un solo intento a la vez, aunque lleguen varias pantallas juntas.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.config import obtener_settings
from app.db.session import sesion_manual

log = logging.getLogger(__name__)

INTERVALO_SEGUNDOS = 3600
_cerrojo = threading.Lock()
_ultimo_intento = 0.0


def _hoy(zona: str):
    return datetime.now(ZoneInfo(zona)).date()


def asegurar() -> bool:
    """Trae las tasas que falten. Devuelve True si lo intento. Nunca levanta."""
    global _ultimo_intento
    settings = obtener_settings()
    if not settings.tasas_automaticas:
        return False
    if time.monotonic() - _ultimo_intento < INTERVALO_SEGUNDOS:
        return False
    if not _cerrojo.acquire(blocking=False):
        return False
    try:
        _ultimo_intento = time.monotonic()
        hoy = _hoy(settings.zona_horaria)
        with sesion_manual() as sesion:
            ultima = sesion.execute(
                text("SELECT max(fecha) FROM tasas_cambio WHERE tipo = 'bcv'")
            ).scalar()
        if ultima is not None and ultima >= hoy:
            return False

        # Import tardio: `operativos` importa clientes HTTP que no hacen falta si las
        # tasas ya estan al dia, que es el caso comun.
        from app.jobs.operativos import backfill_tasas, snapshot_tasa

        desde = (ultima or hoy - timedelta(days=30)) - timedelta(days=1)
        backfill_tasas(desde=desde)
        snapshot_tasa()
        log.info("Tasas puestas al día desde %s", desde)
        return True
    except Exception:
        # Sin tasa nueva la app sigue andando: la pantalla avisa que la tasa es vieja.
        log.exception("No se pudieron actualizar las tasas")
        return True
    finally:
        _cerrojo.release()


def asegurar_en_segundo_plano() -> None:
    threading.Thread(target=asegurar, name="tasas-frescas", daemon=True).start()
