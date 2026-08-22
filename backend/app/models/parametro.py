"""Parámetros de precio versionados y configuración no numérica.

Los cuatro factores del negocio vivían solo en la hoja `PARÁMETROS` del Excel.
Acá van versionados con `vigencia DATERANGE` y una constraint de exclusión, así que
dos vigencias del mismo parámetro **no pueden** solaparse y el historial de
repreciado siempre se puede reconstruir: cambiar la ganancia deja de ser
irreversible.

`configuracion` es lo que mata el bug de los `V-XX.XXX.XXX`: los datos de pago del
recordatorio son una fila acá, nunca texto en una plantilla.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import DATERANGE, JSONB, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

#: Claves conocidas. La tabla acepta otras; estas son las que el código usa.
CLAVE_GANANCIA_DIVISA = "GANANCIA_DIVISA"
CLAVE_GANANCIA_BCV = "GANANCIA_BCV"
CLAVE_DESC_TEAM = "DESC_TEAM"
CLAVE_DESC_REVENDEDOR = "DESC_REVENDEDOR"
CLAVE_PLAZO_CREDITO_DIAS = "PLAZO_CREDITO_DIAS"
CLAVE_TOLERANCIA_PRECIO_PCT = "TOLERANCIA_PRECIO_PCT"
CLAVE_DIAS_MORA_PARA_MOROSO = "DIAS_MORA_PARA_MOROSO"
CLAVE_DIAS_ENTRE_RECORDATORIOS = "DIAS_ENTRE_RECORDATORIOS"
CLAVE_MAX_RECORDATORIOS_MES = "MAX_RECORDATORIOS_POR_VENTA_MES"
CLAVE_DIAS_POR_VENCER = "DIAS_POR_VENCER"
CLAVE_TASA_COMISION = "TASA_COMISION"

CLAVE_DATOS_PAGO = "datos_pago"
CLAVE_NOMBRE_NEGOCIO = "nombre_negocio"
CLAVE_PROVEEDOR_NOTIFICACIONES = "proveedor_notificaciones"

#: Campos que `{datos_pago}` exige. Si falta alguno, el render falla.
CAMPOS_DATOS_PAGO_REQUERIDOS = ("banco", "documento", "telefono")


class ParametroPrecio(Base):
    """Un parámetro con vigencia.

    La constraint de exclusión GiST es la pieza que hace confiable el historial de
    precios: **dos vigencias del mismo parámetro no pueden solaparse**, así que
    "cuánto era la ganancia BCV el 15 de julio" siempre tiene exactamente una
    respuesta. Sin ella, versionar sería solo acumular filas.
    """

    __tablename__ = "parametros_precio"
    __table_args__ = (
        ExcludeConstraint(
            ("clave", "="),
            ("vigencia", "&&"),
            name="uq_parametros_precio_sin_solape",
            using="gist",
        ),
        CheckConstraint("NOT isempty(vigencia)", name="vigencia_no_vacia"),
        Index("ix_parametros_precio_clave", "clave"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clave: Mapped[str] = mapped_column(String(48), nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    vigencia: Mapped[object] = mapped_column(DATERANGE, nullable=False)
    motivo: Mapped[str | None] = mapped_column(Text)
    creado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Configuracion(Base):
    __tablename__ = "configuracion"

    clave: Mapped[str] = mapped_column(String(64), primary_key=True)
    valor: Mapped[dict] = mapped_column(JSONB, nullable=False)
    es_secreto: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    descripcion: Mapped[str | None] = mapped_column(Text)
    actualizado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
