"""Lado de la oferta: proveedores, lotes, compras y gastos.

La hoja `GASTOS Y COMPRAS` era 89 líneas de texto libre en una sola columna
('SCANDAL  9.10$'), con subtotales calculados a mano dentro del texto. La auditoría
ya encontró dos que no cuadran: +$0,50 en el lote del 26/06 y +$1,85 en el pedido de
Caracas.

`lotes_compra.diferencia_usd` es una columna generada justamente para eso: convierte
esos descuadres de una nota en un markdown a un hecho consultable y permanente.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._comun import MarcasDeTiempo, enum_pg
from app.models.enums import CanalPago, EstadoRegistro


class Proveedor(Base, MarcasDeTiempo):
    __tablename__ = "proveedores"
    __table_args__ = (
        Index(
            "uq_proveedores_nombre_normalizado",
            "nombre_normalizado",
            unique=True,
            postgresql_where="estado <> 'fusionado'",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    nombre_normalizado: Mapped[str] = mapped_column(String(200), nullable=False)
    contacto: Mapped[str | None] = mapped_column(String(200))
    telefono_e164: Mapped[str | None] = mapped_column(String(20))
    telefono: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(200))
    estado: Mapped[EstadoRegistro] = mapped_column(
        enum_pg(EstadoRegistro), nullable=False, server_default=EstadoRegistro.ACTIVO.value
    )
    notas: Mapped[str | None] = mapped_column(Text)


class LoteCompra(Base):
    """Un pedido. Los 8 lotes de la hoja GASTOS."""

    __tablename__ = "lotes_compra"
    __table_args__ = (Index("ix_lotes_compra_fecha", "fecha"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    #: 'Lote 19/06/2026', 'PEDIDO CARACAS LUKA STORE'
    codigo: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    #: NULL para el lote de Caracas, que en la hoja no tiene fecha.
    fecha: Mapped[date | None] = mapped_column(Date)
    proveedor_id: Mapped[int | None] = mapped_column(ForeignKey("proveedores.id"))
    canal: Mapped[CanalPago | None] = mapped_column(enum_pg(CanalPago))
    #: Lo que decía la nota escrita a mano: 99, 236, 30, 176, 109, 15, 59.
    subtotal_declarado_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    #: Mantenido por trigger desde `compras`.
    subtotal_calculado_usd: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default="0"
    )
    #: Columna generada: declarado − calculado. Convierte los descuadres de la
    #: hoja GASTOS ($0,50 y $1,85) en un hecho consultable y permanente.
    diferencia_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2),
        Computed(
            "COALESCE(subtotal_declarado_usd, 0) - subtotal_calculado_usd", persisted=True
        ),
    )
    texto_original: Mapped[str | None] = mapped_column(Text)
    notas: Mapped[str | None] = mapped_column(Text)
    importacion_id: Mapped[int | None] = mapped_column(ForeignKey("importaciones.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    compras: Mapped[list[Compra]] = relationship("Compra", back_populates="lote")


class Compra(Base):
    """Una línea `ÍTEM` del lote."""

    __tablename__ = "compras"
    __table_args__ = (
        CheckConstraint("cantidad > 0", name="cantidad_positiva"),
        CheckConstraint("costo_unitario_usd >= 0", name="costo_no_negativo"),
        Index("ix_compras_lote", "lote_id"),
        Index("ix_compras_producto", "producto_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lote_id: Mapped[int] = mapped_column(
        ForeignKey("lotes_compra.id", ondelete="CASCADE"), nullable=False
    )
    #: NULLABLE: no todo ítem de un lote es un SKU del catálogo.
    producto_id: Mapped[int | None] = mapped_column(ForeignKey("productos.id"))
    descripcion_libre: Mapped[str] = mapped_column(String(200), nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    costo_unitario_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    monto_bs: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    tasa_aplicada: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    texto_original: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    lote: Mapped[LoteCompra] = relationship("LoteCompra", back_populates="compras")


class PagoCompra(Base):
    __tablename__ = "pagos_compra"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lote_id: Mapped[int] = mapped_column(ForeignKey("lotes_compra.id"), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    monto_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    monto_bs: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    tasa_aplicada: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    canal: Mapped[CanalPago | None] = mapped_column(enum_pg(CanalPago))
    referencia: Mapped[str | None] = mapped_column(String(64))
    registrado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Gasto(Base):
    """Gasto operativo. Las 3 líneas `GASTO` de la hoja, separadas de la compra de
    producto para que no distorsionen la comparación de subtotales por lote."""

    __tablename__ = "gastos"
    __table_args__ = (Index("ix_gastos_fecha", "fecha"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    lote_id: Mapped[int | None] = mapped_column(ForeignKey("lotes_compra.id"))
    #: envio | muestra | plataforma | otro
    categoria: Mapped[str] = mapped_column(String(64), nullable=False)
    descripcion: Mapped[str] = mapped_column(String(300), nullable=False)
    monto_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    monto_bs: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    tasa_aplicada: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    canal: Mapped[CanalPago | None] = mapped_column(enum_pg(CanalPago))
    texto_original: Mapped[str | None] = mapped_column(Text)
    notas: Mapped[str | None] = mapped_column(Text)
    creado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
