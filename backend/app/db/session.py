"""Engine, sesión y el contexto de auditoría por transacción.

El actor de la auditoría viaja a Postgres como `app.usuario_id` / `app.request_id`
vía `SET LOCAL`, porque los triggers de auditoría lo leen con
`current_setting('app.usuario_id', true)`. Se hace en un listener `after_begin`
para que valga en cualquier transacción, no solo en las que pasan por un endpoint.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import obtener_settings

usuario_actual_id: ContextVar[int | None] = ContextVar("usuario_actual_id", default=None)
request_id_actual: ContextVar[str | None] = ContextVar("request_id_actual", default=None)
#: Quien escribe: 'api' hace que la capa de compatibilidad con Streamlit se aparte,
#: porque la API ya escribe el modelo canonico completo.
escritor_actual: ContextVar[str | None] = ContextVar("escritor_actual", default=None)

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def obtener_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = obtener_settings()
        _engine = create_engine(
            settings.exigir_database_url(),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            future=True,
        )
    return _engine


def obtener_sessionmaker() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=obtener_engine(),
            autoflush=False,
            expire_on_commit=False,
            future=True,
        )
        _registrar_contexto_auditoria(_SessionLocal)
    return _SessionLocal


def _registrar_contexto_auditoria(factory: sessionmaker[Session]) -> None:
    """Propaga el contexto a Postgres al empezar cada transaccion.

    Los ContextVar son el mecanismo de respaldo, para el ETL y los jobs, que corren
    en un solo contexto. **En la API no se puede depender de ellos**: FastAPI corre
    las dependencias sincronicas en un threadpool, y la transaccion puede empezar en
    un contexto distinto del que puso el valor. Por eso `app/api/deps.py` llama a
    `fijar_contexto()` de forma explicita sobre la sesion.
    """

    @event.listens_for(factory, "after_begin")
    def _set_local(session: Session, transaction, connection) -> None:  # noqa: ANN001, ARG001
        for clave, valor in (
            ("app.usuario_id", usuario_actual_id.get()),
            ("app.request_id", request_id_actual.get()),
            ("app.escritor", escritor_actual.get()),
        ):
            if valor is not None:
                connection.execute(
                    text("SELECT set_config(:k, :v, true)"),
                    {"k": clave, "v": str(valor)},
                )


def fijar_contexto(
    sesion: Session,
    *,
    usuario_id: int | None = None,
    request_id: str | None = None,
    escritor: str | None = None,
) -> None:
    """Fija el contexto de auditoria en la transaccion actual, sin ContextVars.

    `set_config(..., true)` es equivalente a `SET LOCAL`: vale hasta el fin de la
    transaccion y no se filtra a la siguiente conexion del pool.
    """
    for clave, valor in (
        ("app.usuario_id", usuario_id),
        ("app.request_id", request_id),
        ("app.escritor", escritor),
    ):
        if valor is not None:
            sesion.execute(
                text("SELECT set_config(:k, :v, true)"), {"k": clave, "v": str(valor)}
            )


def get_db() -> Iterator[Session]:
    """Dependencia de FastAPI. Commit explícito en el endpoint; acá solo rollback y cierre."""
    sesion = obtener_sessionmaker()()
    try:
        yield sesion
    except Exception:
        sesion.rollback()
        raise
    finally:
        sesion.close()


@contextmanager
def sesion_manual() -> Iterator[Session]:
    """Para scripts, ETL y jobs, fuera del ciclo de request."""
    sesion = obtener_sessionmaker()()
    try:
        yield sesion
        sesion.commit()
    except Exception:
        sesion.rollback()
        raise
    finally:
        sesion.close()
