"""Estado y disparo controlado de automatizaciones."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Header
from sqlalchemy import text

from app.api.deps import PuedeEscribir, SesionDb, SoloAdmin
from app.api.errors import ErrorNegocio
from app.config import obtener_settings
from app.jobs.operativos import JOBS, ejecutar

router = APIRouter(prefix="/automatizaciones", tags=["automatizaciones"])


@router.get("")
def listar(db: SesionDb, actual: SoloAdmin):
    del actual
    ultimas = (
        db.execute(
            text(
                """
            SELECT DISTINCT ON (nombre) id, nombre, inicio, fin, estado,
                   filas_afectadas, detalle, error
              FROM jobs_ejecuciones ORDER BY nombre, inicio DESC
            """
            )
        )
        .mappings()
        .all()
    )
    por_nombre = {f.nombre: dict(f) for f in ultimas}
    return [{"nombre": nombre, "ultima": por_nombre.get(nombre)} for nombre in JOBS]


@router.post("/{nombre}/ejecutar")
def ejecutar_manual(
    nombre: str, actual: SoloAdmin, _: PuedeEscribir, x_job_secret: str | None = Header(None)
):
    del actual
    if nombre not in JOBS:
        raise ErrorNegocio("JOB_DESCONOCIDO", "Esa automatización no existe.")
    settings = obtener_settings()
    if (
        x_job_secret is not None
        and settings.job_secret
        and not secrets.compare_digest(x_job_secret, settings.job_secret)
    ):
        raise ErrorNegocio("JOB_SECRET_INVALIDO", "La clave de automatización no es válida.")
    return ejecutar(nombre)


@router.post("/cron/{nombre}")
def ejecutar_desde_cron(nombre: str, x_job_secret: str = Header(...)):
    """Entrada sin sesión para cron externo; la protege un secreto independiente."""
    settings = obtener_settings()
    if not settings.job_secret or not secrets.compare_digest(x_job_secret, settings.job_secret):
        raise ErrorNegocio("JOB_SECRET_INVALIDO", "La clave de automatización no es válida.")
    if nombre not in JOBS:
        raise ErrorNegocio("JOB_DESCONOCIDO", "Esa automatización no existe.")
    return ejecutar(nombre)
