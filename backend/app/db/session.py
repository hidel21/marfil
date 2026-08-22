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
    @event.listens_for(factory, "after_begin")
    def _set_local(session: Session, transaction, connection) -> None:  # noqa: ANN001, ARG001
        usuario = usuario_actual_id.get()
        request = request_id_actual.get()
        if usuario is not None:
            connection.execute(
                text("SELECT set_config('app.usuario_id', :v, true)"),
                {"v": str(usuario)},
            )
        if request is not None:
            connection.execute(
                text("SELECT set_config('app.request_id', :v, true)"),
                {"v": request},
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
