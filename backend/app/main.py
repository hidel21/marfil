"""La aplicacion FastAPI.

Sincrona a proposito: endpoints `def` que FastAPI corre en su threadpool, con
SQLAlchemy sincrono. La logica probada del sistema —el `SELECT FOR UPDATE` del abono,
el descuento de stock atomico— es sincrona, tres usuarios concurrentes no necesitan un
event loop, y una reescritura async seria la mayor fuente de bugs nuevos de toda la
migracion.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.errors import registrar_manejadores
from app.api.respuestas import RespuestaMarfil, instalar_codificador_decimal
from app.api.v1 import router as router_v1
from app.config import obtener_settings
from app.db.session import obtener_engine
from app.jobs.scheduler import detener as detener_scheduler
from app.jobs.scheduler import iniciar as iniciar_scheduler

log = logging.getLogger("marfil")

DESCRIPCION = """
API de Sistema Marfil: inventario, ventas, cobranza y recordatorios.

Dos cosas que conviene saber al integrar:

- **El dinero viaja como string** (`"359.67"`), nunca como número JSON. Un float de
  ida y vuelta es como aparecen los descuadres de un centavo, y JavaScript no tiene
  decimales exactos. Parsealo con una librería de decimales.
- **Los errores de negocio son 422 con un código estable**, no trazas. La forma es
  `{codigo, mensaje, campo?, sugerencia?, detalles?}`, y `detalles` trae los números
  para que la interfaz pueda ofrecer la salida en vez de solo decir que no.
"""


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    settings = obtener_settings()
    settings.validar_produccion()

    try:
        with obtener_engine().connect() as conexion:
            revision = conexion.execute(
                text("SELECT version_num FROM alembic_version_marfil")
            ).scalar()
        log.info("Base conectada, revisión %s", revision)
        app.state.revision_db = revision
    except Exception:
        log.exception("No se pudo conectar a la base al arrancar")
        app.state.revision_db = None

    iniciar_scheduler()
    try:
        yield
    finally:
        detener_scheduler()
        obtener_engine().dispose()


def crear_app() -> FastAPI:
    # Antes de construir la app: el codificador de Decimal es global.
    instalar_codificador_decimal()
    settings = obtener_settings()
    app = FastAPI(
        title="Sistema Marfil",
        version="1.0.0",
        description=DESCRIPCION,
        lifespan=ciclo_de_vida,
        # Garantiza el contrato del dinero en TODOS los endpoints, incluidos los que
        # devuelven dicts crudos: un Decimal nunca sale como numero JSON.
        default_response_class=RespuestaMarfil,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.lista_cors,
        allow_credentials=True,  # necesario para la cookie del refresh token
        allow_methods=["*"],
        allow_headers=["*"],
    )

    registrar_manejadores(app)
    app.include_router(router_v1)

    @app.get("/api/salud", tags=["salud"])
    def salud():
        """Chequeo con lo que de verdad importa para operar."""
        estado: dict[str, object] = {
            "ok": True,
            "entorno": settings.entorno,
            "solo_lectura": settings.solo_lectura,
        }
        try:
            with obtener_engine().connect() as c:
                estado["revision_db"] = c.execute(
                    text("SELECT version_num FROM alembic_version_marfil")
                ).scalar()
                estado["descuadres"] = c.execute(
                    text("SELECT count(*) FROM v_conciliacion_ventas WHERE NOT ok")
                ).scalar()
                estado["datos_pago_completos"] = c.execute(
                    text(
                        "SELECT count(*) = 0 FROM ("
                        "  SELECT jsonb_each_text(valor) AS campo FROM configuracion "
                        "  WHERE clave = 'datos_pago') x "
                        "WHERE (x.campo).key IN ('banco','documento','telefono') "
                        "  AND COALESCE(btrim((x.campo).value), '') = ''"
                    )
                ).scalar()
        except Exception as exc:
            estado["ok"] = False
            estado["error"] = type(exc).__name__
        return estado

    # En el despliegue gratuito se sirve la exportación estática de Next desde el
    # mismo origen. Así la cookie HttpOnly conserva SameSite=Lax y no se convierte
    # en una cookie de terceros. API y salud se registran antes que este montaje.
    if settings.frontend_dir and Path(settings.frontend_dir).is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")

    return app


app = crear_app()
