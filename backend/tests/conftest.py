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

# Secreto fijo para los tests. En desarrollo el default es aleatorio por proceso —lo
# correcto, para que los tokens no sobrevivan un reinicio—, pero eso hace que limpiar
# la cache de settings rote el secreto y invalide un token ya emitido.
os.environ.setdefault("JWT_SECRET", "secreto-fijo-solo-para-los-tests-de-marfil-1234")

URL_ADMIN = os.getenv(
    "MARFIL_TEST_ADMIN_URL", "postgresql+psycopg://odoo:odoo@localhost:5432/postgres"
)
BASE_TEST = os.getenv("MARFIL_TEST_DB", "marfil_pytest")


def _url_test() -> str:
    base, _, _ = URL_ADMIN.rpartition("/")
    return f"{base}/{BASE_TEST}"


def _construir_base(nombre: str):
    """Crea la base desde cero y le corre todas las migraciones."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import OperationalError

    try:
        admin = create_engine(URL_ADMIN, isolation_level="AUTOCOMMIT")
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{nombre}" WITH (FORCE)'))
            c.execute(text(f'CREATE DATABASE "{nombre}"'))
    except OperationalError as exc:
        pytest.skip(f"sin Postgres disponible: {exc}")

    base, _, _ = URL_ADMIN.rpartition("/")
    url = f"{base}/{nombre}"
    os.environ["DATABASE_URL"] = url

    from app.config import obtener_settings

    obtener_settings.cache_clear()

    from alembic.config import Config

    from alembic import command

    cfg = Config(str(RAIZ_BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ_BACKEND / "alembic"))
    command.stamp(cfg, "0000")
    command.upgrade(cfg, "head")
    return create_engine(url, future=True)


def _tirar_base(nombre: str) -> None:
    from sqlalchemy import create_engine, text

    with create_engine(URL_ADMIN, isolation_level="AUTOCOMMIT").connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{nombre}" WITH (FORCE)'))


@pytest.fixture(scope="session")
def engine():
    """Base para los tests de esquema, que corren en transacciones revertidas."""
    eng = _construir_base(BASE_TEST)
    yield eng
    eng.dispose()
    _tirar_base(BASE_TEST)


@pytest.fixture(scope="session")
def engine_api():
    """Base separada para los tests de la API.

    Van aparte porque escriben **con commit** a traves de HTTP: no hay transaccion que
    revertir. Compartir base con los tests de esquema hacia que estos vieran el estado
    que dejaban aquellos —una contrasena ya fijada, los datos de pago ya completos— y
    fallaran segun el orden en que corrieran. Un test que depende del orden es peor que
    no tenerlo.
    """
    eng = _construir_base(f"{BASE_TEST}_api")
    yield eng
    eng.dispose()
    _tirar_base(f"{BASE_TEST}_api")


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
