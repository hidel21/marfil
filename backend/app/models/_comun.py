"""Piezas compartidas por los modelos."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Enum, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import NOMBRES_ENUM


def enum_pg(enum_cls, **kwargs):
    """Enum nativo de Postgres con el nombre canónico del tipo.

    `create_type=False`: los tipos los crea Alembic una sola vez, no el mapper.
    """
    return Enum(
        enum_cls,
        name=NOMBRES_ENUM[enum_cls],
        native_enum=True,
        create_type=False,
        values_callable=lambda e: [m.value for m in e],
        **kwargs,
    )


class MarcasDeTiempo:
    """created_at / updated_at manejados por el servidor, no por Python.

    Por el servidor para que el ETL, los jobs y la API no puedan discrepar.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
