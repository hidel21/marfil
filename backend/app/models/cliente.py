"""Clientes. La tabla que no existía y que bloqueaba todo lo demás.

Sin ella `cliente` era texto libre copiado en `ventas` y `pagos`, no había dónde
guardar un teléfono, y por lo tanto la notificación por WhatsApp era imposible.

`clientes_alias` es lo que permite que 'gregor'/'Gregor', 'mirleidy'/'Hade Mirleidy'
y 'Juan herrade'/'Juan Herrade' resuelvan a una sola fila **sin perder** el string
original: el histórico sigue siendo consultable tal como se tecleó.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._comun import MarcasDeTiempo, enum_pg
from app.models.enums import EstadoRegistro, NivelPrecio


class Cliente(Base, MarcasDeTiempo):
    __tablename__ = "clientes"
    __table_args__ = (
        Index(
            "uq_clientes_nombre_normalizado",
            "nombre_normalizado",
            unique=True,
            postgresql_where="estado <> 'fusionado'",
        ),
        Index(
            "ix_clientes_telefono",
            "telefono_e164",
            postgresql_where="telefono_e164 IS NOT NULL",
        ),
        Index("ix_clientes_nombre_trgm", "nombre_normalizado", postgresql_using="gin",
              postgresql_ops={"nombre_normalizado": "gin_trgm_ops"}),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(160), nullable=False)
    #: `clave_nombre()`: minúsculas, sin acentos y **sin espacios**.
    nombre_normalizado: Mapped[str] = mapped_column(String(160), nullable=False)
    telefono_e164: Mapped[str | None] = mapped_column(String(20))
    telefono_verificado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    email: Mapped[str | None] = mapped_column(CITEXT)
    nivel_precio: Mapped[NivelPrecio] = mapped_column(
        enum_pg(NivelPrecio), nullable=False, server_default=NivelPrecio.PUBLICO.value
    )
    #: NULL -> se usa el parámetro global PLAZO_CREDITO_DIAS.
    plazo_credito_dias: Mapped[int | None] = mapped_column(SmallInteger)
    #: Los socios también compran; hay que poder excluir su autoconsumo del ingreso real.
    es_socio: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    estado: Mapped[EstadoRegistro] = mapped_column(
        enum_pg(EstadoRegistro), nullable=False, server_default=EstadoRegistro.ACTIVO.value
    )
    fusionado_en_cliente_id: Mapped[int | None] = mapped_column(
        ForeignKey("clientes.id", name="fk_clientes_fusionado_en_cliente_id_clientes")
    )
    notas: Mapped[str | None] = mapped_column(Text)
    # use_alter: `usuarios` y `clientes` se referencian mutuamente (un afiliado es
    # un cliente con login). La FK se agrega con ALTER despues de crear ambas.
    creado_por_usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "usuarios.id", name="fk_clientes_creado_por_usuario_id_usuarios", use_alter=True
        )
    )

    alias: Mapped[list[ClienteAlias]] = relationship(
        "ClienteAlias", back_populates="cliente", cascade="all, delete-orphan"
    )
    usuario: Mapped[Usuario | None] = relationship(  # noqa: F821
        "Usuario", foreign_keys="Usuario.cliente_id", back_populates="cliente", uselist=False
    )

    @property
    def puede_notificar(self) -> bool:
        return bool(self.telefono_e164)


class ClienteAlias(Base):
    __tablename__ = "clientes_alias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cliente_id: Mapped[int] = mapped_column(
        ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(160), nullable=False)
    alias_normalizado: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    #: excel_ventas | excel_control | db_legacy | manual
    origen: Mapped[str] = mapped_column(String(32), nullable=False)

    cliente: Mapped[Cliente] = relationship("Cliente", back_populates="alias")
