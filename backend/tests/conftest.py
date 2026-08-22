"""Infraestructura de tests.

Los tests de esquema corren contra **Postgres real**, no SQLite: lo que hay que
probar son triggers, enums nativos, columnas generadas e índices únicos parciales,
y ninguna de esas cosas existe en SQLite. Un test que pasa en SQLite y no prueba el
trigger es peor que no tenerlo.

La base de test se crea desde cero con `alembic upgrade head` una vez por sesión, y
cada test corre dentro de una transacción que se revierte. Así los tests no se
contaminan entre sí y no hace falta limpiar.

Se saltan (skip) si no hay Postgres: el resto de la suite —los helpers puros— corre
igual en cualquier parte.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

RAIZ_BACKEND = Path(__file__).resolve().parents[1]
if str(RAIZ_BACKEND) not in sys.path:
    sys.path.insert(0, str(RAIZ_BACKEND))

URL_ADMIN = os.getenv(
    "MARFIL_TEST_ADMIN_URL", "postgresql+psycopg://odoo:odoo@localhost:5432/postgres"
)
BASE_TEST = os.getenv("MARFIL_TEST_DB", "marfil_pytest")


def _url_test() -> str:
    base, _, _ = URL_ADMIN.rpartition("/")
    return f"{base}/{BASE_TEST}"


@pytest.fixture(scope="session")
def engine():
    """Base de test recreada desde las migraciones. Skip si no hay Postgres."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import OperationalError

    try:
        admin = create_engine(URL_ADMIN, isolation_level="AUTOCOMMIT")
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{BASE_TEST}" WITH (FORCE)'))
            c.execute(text(f'CREATE DATABASE "{BASE_TEST}"'))
    except OperationalError as exc:
        pytest.skip(f"sin Postgres disponible para los tests de esquema: {exc}")

    os.environ["DATABASE_URL"] = _url_test()
    from app.config import obtener_settings

    obtener_settings.cache_clear()

    from alembic.config import Config

    from alembic import command

    cfg = Config(str(RAIZ_BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ_BACKEND / "alembic"))
    command.stamp(cfg, "0000")
    command.upgrade(cfg, "head")

    eng = create_engine(_url_test(), future=True)
    yield eng
    eng.dispose()

    with create_engine(URL_ADMIN, isolation_level="AUTOCOMMIT").connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{BASE_TEST}" WITH (FORCE)'))


@pytest.fixture
def conn(engine):
    """Conexión con transacción revertida al final. Cada test parte de lo mismo."""
    conexion = engine.connect()
    tx = conexion.begin()
    try:
        yield conexion
    finally:
        tx.rollback()
        conexion.close()
