"""Identidad y acceso.

Un solo campo `rol` en vez de una tabla de permisos: el requerimiento son tres
socios administradores y dos tipos de usuario creables (vendedor, afiliado), no
composición arbitraria de permisos. `permisos_extra` absorbe la excepción futura
sin una migración.
"""

from __future__ import annotations

import uuid
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
from sqlalchemy.dialects.postgresql import CITEXT, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._comun import MarcasDeTiempo, enum_pg
from app.models.enums import RolUsuario


class Socio(Base, MarcasDeTiempo):
    """Los tres socios. Es la tabla de reparto de utilidad, no la de identidad."""

    __tablename__ = "socios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    capital_invertido: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default="0"
    )
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", name="fk_socios_usuario_id_usuarios"), unique=True
    )

    usuario: Mapped[Usuario | None] = relationship(
        "Usuario", foreign_keys=[usuario_id], back_populates="socio"
    )


class Usuario(Base, MarcasDeTiempo):
    __tablename__ = "usuarios"
    __table_args__ = (
        CheckConstraint(
            "rol <> 'afiliado' OR cliente_id IS NOT NULL",
            name="afiliado_exige_cliente",
        ),
        Index("ix_usuarios_rol", "rol"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    rol: Mapped[RolUsuario] = mapped_column(enum_pg(RolUsuario), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    telefono_e164: Mapped[str | None] = mapped_column(String(20))
    permisos_extra: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    debe_cambiar_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    ultimo_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    cliente_id: Mapped[int | None] = mapped_column(
        ForeignKey("clientes.id", name="fk_usuarios_cliente_id_clientes")
    )

    socio: Mapped[Socio | None] = relationship(
        "Socio", foreign_keys="Socio.usuario_id", back_populates="usuario", uselist=False
    )
    cliente: Mapped[Cliente | None] = relationship(  # noqa: F821
        "Cliente", foreign_keys=[cliente_id], back_populates="usuario"
    )

    @property
    def es_admin(self) -> bool:
        return self.rol == RolUsuario.ADMIN


class RefreshToken(Base):
    """El token se guarda hasheado; `familia_id` detecta reuso.

    Sin esto la revocación no es real: un JWT sin estado no se puede invalidar, y
    un vendedor que deja el equipo tiene que perder el acceso en el momento.
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_tokens_vigentes", "usuario_id", postgresql_where="revocado_at IS NULL"),
        Index("ix_refresh_tokens_familia_id", "familia_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    familia_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    expira_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revocado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
