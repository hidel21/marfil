"""Configuración del backend.

`DATABASE_URL` sale, en orden: variable de entorno, `.env`, o
`.streamlit/secrets.toml` (comodidad para desarrollo local mientras Streamlit
sigue vivo). El esquema `postgresql+psycopg2://` se normaliza a `+psycopg`
porque el backend usa psycopg 3.
"""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ_PROYECTO = Path(__file__).resolve().parents[2]
SECRETS_STREAMLIT = RAIZ_PROYECTO / ".streamlit" / "secrets.toml"


def _url_desde_secrets_streamlit() -> str:
    if not SECRETS_STREAMLIT.is_file():
        return ""
    try:
        datos = tomllib.loads(SECRETS_STREAMLIT.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return ""
    return str(datos.get("DATABASE_URL") or "")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(RAIZ_PROYECTO / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    entorno: str = Field(default="desarrollo")
    database_url: str = Field(default="")

    jwt_secret: str = Field(default="cambiar-en-produccion")
    jwt_algoritmo: str = Field(default="HS256")
    access_token_minutos: int = Field(default=30)
    refresh_token_dias: int = Field(default=30)

    cors_origenes: str = Field(default="http://localhost:3000")
    zona_horaria: str = Field(default="America/Caracas")

    # Interruptor de emergencia del plan (fase 4): deja la API sin escrituras.
    solo_lectura: bool = Field(default=False)

    @field_validator("database_url", mode="after")
    @classmethod
    def _resolver_url(cls, valor: str) -> str:
        url = valor or _url_desde_secrets_streamlit()
        if url.startswith("postgresql+psycopg2://"):
            url = url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url

    @property
    def lista_cors(self) -> list[str]:
        return [o.strip() for o in self.cors_origenes.split(",") if o.strip()]

    def exigir_database_url(self) -> str:
        if not self.database_url:
            raise RuntimeError(
                "Falta DATABASE_URL. Definila como variable de entorno, en backend/.env "
                "o en .streamlit/secrets.toml."
            )
        return self.database_url


@lru_cache(maxsize=1)
def obtener_settings() -> Settings:
    return Settings()
