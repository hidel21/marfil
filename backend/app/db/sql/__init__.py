"""SQL crudo que Alembic y los servicios cargan por nombre.

Vive en archivos .sql y no en cadenas dentro de las migraciones porque son
funciones y triggers largos: en un archivo se leen, se diffean y el editor los
resalta.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

DIR_SQL = Path(__file__).resolve().parent


@lru_cache(maxsize=32)
def leer_sql(nombre: str) -> str:
    ruta = DIR_SQL / f"{nombre}.sql"
    if not ruta.is_file():
        raise FileNotFoundError(f"No existe {ruta}")
    return ruta.read_text(encoding="utf-8")
