"""Linaje de las importaciones.

`filas_importadas` (antes `filas_excel`, con la columna `pestaña` no-ASCII) es el
archivo inmutable de cada fila que entró alguna vez. Las 322 filas que ya están no
se tocan nunca.

`enlaces_importacion` es nueva y hace tres cosas de una:
- responde "qué celda del Excel produjo esta venta";
- hace revisables los cruces dudosos (`metodo='fuzzy'`, `score`, `confianza='baja'`)
  en vez de invisibles, que es el problema del umbral 0,52 de `migrate_excel.py`;
- hace **reversible** la importación: un rollback borra exactamente las filas que
  esta tabla apunta, y nada más.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._comun import enum_pg
from app.models.enums import ConfianzaDato, MetodoEnlace


class Importacion(Base):
    __tablename__ = "importaciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    archivo: Mapped[str] = mapped_column(String(255), nullable=False)
    #: sha256 del contenido: la guardia de idempotencia.
    archivo_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    #: 'v1' (libro original) | 'v2' (libro auditado)
    mapeo_version: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="v1"
    )
    #: archivado | procesado | revertido
    estado: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="archivado"
    )
    importado_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    importado_por_usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id")
    )

    filas: Mapped[list[FilaImportada]] = relationship(
        "FilaImportada", back_populates="importacion", cascade="all, delete-orphan"
    )


class FilaImportada(Base):
    __tablename__ = "filas_importadas"
    __table_args__ = (
        UniqueConstraint(
            "importacion_id",
            "hoja",
            "numero_fila",
            name="uq_filas_importadas_ubicacion",
        ),
        Index("ix_filas_importadas_datos", "datos", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    importacion_id: Mapped[int] = mapped_column(
        ForeignKey("importaciones.id", ondelete="CASCADE"), nullable=False
    )
    #: Antes se llamaba `pestaña`: un identificador no-ASCII en Postgres.
    hoja: Mapped[str] = mapped_column(String(64), nullable=False)
    numero_fila: Mapped[int] = mapped_column(Integer, nullable=False)
    datos: Mapped[dict] = mapped_column(JSONB, nullable=False)

    importacion: Mapped[Importacion] = relationship(
        "Importacion", back_populates="filas"
    )


class EnlaceImportacion(Base):
    __tablename__ = "enlaces_importacion"
    __table_args__ = (
        UniqueConstraint(
            "fila_id",
            "tabla_destino",
            "registro_id",
            name="uq_enlaces_importacion_destino",
        ),
        Index("ix_enlaces_importacion_destino", "tabla_destino", "registro_id"),
        Index(
            "ix_enlaces_importacion_revision",
            "confianza",
            postgresql_where="confianza = 'baja'",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fila_id: Mapped[int] = mapped_column(
        ForeignKey("filas_importadas.id", ondelete="CASCADE"), nullable=False
    )
    tabla_destino: Mapped[str] = mapped_column(String(48), nullable=False)
    registro_id: Mapped[int] = mapped_column(Integer, nullable=False)
    metodo: Mapped[MetodoEnlace] = mapped_column(enum_pg(MetodoEnlace), nullable=False)
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    confianza: Mapped[ConfianzaDato] = mapped_column(
        enum_pg(ConfianzaDato), nullable=False, server_default=ConfianzaDato.ALTA.value
    )
    revisado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revisado_por_usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id")
    )
    notas: Mapped[str | None] = mapped_column(Text)
