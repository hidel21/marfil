"""Historial de tasas de cambio.

Existe porque el Excel nunca guardó la tasa y la app solo tenía el snapshot por
pago. Sin esta tabla no hay forma de que dos pagos del mismo día compartan la tasa
"oficial" del día, ni de reconstruir por qué un cobro en USD dio lo que dio.

`payload` guarda la respuesta cruda de la API: cuando alguien discuta una tasa, la
respuesta es el JSON que se recibió, no la memoria de nadie.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._comun import enum_pg
from app.models.enums import ConfianzaDato, OrigenTasa, TipoTasa


class TasaCambio(Base):
    __tablename__ = "tasas_cambio"
    __table_args__ = (
        UniqueConstraint("fecha", "tipo", name="uq_tasas_cambio_fecha_tipo"),
        CheckConstraint("valor > 0", name="valor_positivo"),
        Index("ix_tasas_cambio_tipo_fecha", "tipo", "fecha"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    tipo: Mapped[TipoTasa] = mapped_column(enum_pg(TipoTasa), nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    origen: Mapped[OrigenTasa] = mapped_column(enum_pg(OrigenTasa), nullable=False)
    confianza: Mapped[ConfianzaDato] = mapped_column(
        enum_pg(ConfianzaDato), nullable=False, server_default=ConfianzaDato.ALTA.value
    )
    capturado_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    payload: Mapped[dict | None] = mapped_column(JSONB)
