"""Programación interna de trabajos; se activa solo por configuración."""

from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import obtener_settings
from app.jobs.operativos import conciliacion, limpiar_sesiones, snapshot_tasa

_scheduler: BackgroundScheduler | None = None


def iniciar() -> BackgroundScheduler | None:
    global _scheduler
    settings = obtener_settings()
    if not settings.jobs_habilitados or _scheduler is not None:
        return _scheduler
    scheduler = BackgroundScheduler(timezone=settings.zona_horaria)
    scheduler.add_job(
        snapshot_tasa,
        "cron",
        hour=9,
        minute=10,
        id="snapshot_tasa",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        conciliacion,
        "cron",
        hour=2,
        minute=15,
        id="conciliacion",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        limpiar_sesiones,
        "cron",
        day_of_week="sun",
        hour=3,
        minute=0,
        id="limpiar_sesiones",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    _scheduler = scheduler
    return scheduler


def detener() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
