"""Ventas, líneas y plan de cuotas.

**La decisión central del modelo:** el libro de pagos es la única fuente de verdad
y `ventas.saldo_usd` es un caché mantenido por trigger. No derivado en la app, no
escrito por la app.

Por qué, específicamente en este código: ya hay tres caminos de escritura que
evitan `register_payment` y un migrador de DDL a mano que corre SQL crudo. Una
invariante que vive en Python está a una importación CSV de romperse. Pero un
`SUM()` en cada lectura le cuesta un scan a las dos consultas más calientes
(cobranza y dashboard), y `total − SUM(pagos)` no se puede indexar. Un trigger da
una columna indexable que ningún camino de escritura puede desincronizar, más un
CHECK como piso duro. La vista `v_conciliacion_ventas` prueba cada noche que el
caché coincide con el libro.

`saldo_congelado_migracion` guarda la `deuda` que traía la app vieja. No es
redundante: los montos en USD de la migración salieron de una heurística, así que
esa columna es el testigo de que la migración no movió ninguna cifra. Se borra
cuando un socio firme las cifras reconciliadas.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._comun import MarcasDeTiempo, enum_pg
from app.models.enums import EstadoCobro, Moneda, NivelPrecio


class Venta(Base, MarcasDeTiempo):
    __tablename__ = "ventas"
    __table_args__ = (
        CheckConstraint("saldo_usd >= 0", name="saldo_no_negativo"),
        CheckConstraint("saldo_usd <= total_usd", name="saldo_no_supera_total"),
        CheckConstraint("fecha_vencimiento >= fecha", name="vencimiento_no_anterior_a_venta"),
        CheckConstraint("plazo_dias >= 0", name="plazo_no_negativo"),
        Index("ix_ventas_cliente_fecha", "cliente_id", "fecha"),
        Index("ix_ventas_fecha", "fecha"),
        Index("ix_ventas_vendedor_fecha", "vendedor_usuario_id", "fecha"),
        # El índice de la cobranza: solo lo que tiene saldo, ordenado por vencimiento.
        Index(
            "ix_ventas_por_cobrar",
            "fecha_vencimiento",
            "cliente_id",
            postgresql_where="saldo_usd > 0",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), nullable=False)
    vendedor_usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)

    #: Qué nivel de precio aplica. Reemplaza el `moneda='BCV'` hardcodeado que
    #: nunca se encontraba con el precio sugerido: la fuga de $123.
    moneda_cotizacion: Mapped[Moneda] = mapped_column(enum_pg(Moneda), nullable=False)
    nivel_precio_aplicado: Mapped[NivelPrecio] = mapped_column(
        enum_pg(NivelPrecio), nullable=False, server_default=NivelPrecio.PUBLICO.value
    )

    #: Las tres columnas siguientes las mantiene un trigger. No escribirlas a mano.
    total_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0")
    costo_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0")
    saldo_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0")
    estado_cobro: Mapped[EstadoCobro] = mapped_column(
        enum_pg(EstadoCobro),
        nullable=False,
        server_default=EstadoCobro.PENDIENTE_SIN_ABONOS.value,
    )

    plazo_dias: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    #: `fecha + plazo_dias`, o el vencimiento de la cuota impaga más antigua.
    fecha_vencimiento: Mapped[date] = mapped_column(Date, nullable=False)
    tiene_plan_cuotas: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    notas: Mapped[str | None] = mapped_column(Text)
    anulada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    anulada_por_usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", name="fk_ventas_anulada_por_usuario_id_usuarios")
    )
    motivo_anulacion: Mapped[str | None] = mapped_column(Text)

    #: Testigo de fidelidad de la migración. Ver el docstring del módulo.
    saldo_congelado_migracion: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))

    creado_por_usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", name="fk_ventas_creado_por_usuario_id_usuarios")
    )

    items: Mapped[list[VentaItem]] = relationship(
        "VentaItem",
        back_populates="venta",
        cascade="all, delete-orphan",
        order_by="VentaItem.linea",
    )
    cuotas: Mapped[list[Cuota]] = relationship(
        "Cuota", back_populates="venta", cascade="all, delete-orphan", order_by="Cuota.numero"
    )
    pagos: Mapped[list[Pago]] = relationship(  # noqa: F821
        "Pago", back_populates="venta", order_by="Pago.fecha"
    )
    cliente: Mapped[Cliente] = relationship("Cliente")  # noqa: F821

    @property
    def esta_anulada(self) -> bool:
        return self.anulada_at is not None

    @property
    def abonado_usd(self) -> Decimal:
        return self.total_usd - self.saldo_usd


class VentaItem(Base):
    """Reemplaza la `items_venta` que se diseñó y nunca se conectó (0 filas).

    Las tres columnas que son la pista de auditoría de la fuga de precio:
    `descripcion_libre` (lo que el vendedor tecleó, textual), `precio_lista_usd`
    (el precio de política al momento de la venta) y `desviacion_pct` (generada).
    Con eso se puede responder para siempre "qué líneas se cobraron bajo su nivel
    declarado, por quién, y si alguien lo autorizó".
    """

    __tablename__ = "venta_items"
    __table_args__ = (
        UniqueConstraint("venta_id", "linea", name="uq_venta_items_venta_id_linea"),
        CheckConstraint("cantidad > 0", name="cantidad_positiva"),
        CheckConstraint("precio_unitario_usd >= 0", name="precio_no_negativo"),
        CheckConstraint("costo_unitario_usd >= 0", name="costo_no_negativo"),
        Index("ix_venta_items_producto", "producto_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    venta_id: Mapped[int] = mapped_column(
        ForeignKey("ventas.id", ondelete="CASCADE"), nullable=False
    )
    linea: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), nullable=False)
    #: Exactamente lo que se tecleó. Nunca se sobrescribe, ni al fusionar productos.
    descripcion_libre: Mapped[str | None] = mapped_column(String(200))
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    precio_unitario_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    costo_unitario_usd: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default="0"
    )
    #: Precio de política al momento. NULL cuando el costo era desconocido.
    precio_lista_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))

    #: Columnas generadas por Postgres: no se escriben nunca.
    subtotal_usd: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        Computed("cantidad * precio_unitario_usd", persisted=True),
        nullable=False,
    )
    ganancia_usd: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        Computed("cantidad * (precio_unitario_usd - costo_unitario_usd)", persisted=True),
        nullable=False,
    )
    #: Cuánto se desvió el precio cobrado del precio de política. NULL sin costo.
    desviacion_pct: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 4),
        Computed(
            "CASE WHEN precio_lista_usd IS NULL OR precio_lista_usd = 0 THEN NULL "
            "ELSE (precio_unitario_usd - precio_lista_usd) / precio_lista_usd END",
            persisted=True,
        ),
    )

    motivo_desviacion: Mapped[str | None] = mapped_column(Text)
    aprobado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    #: Venta sobre pedido: se registró con stock insuficiente, a propósito.
    sobreventa: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    venta: Mapped[Venta] = relationship("Venta", back_populates="items")
    producto: Mapped[Producto] = relationship("Producto")  # noqa: F821


class Cuota(Base):
    """Plan de cuotas opcional.

    La tabla ya existía con esta forma exacta y nunca se usó. Ahora **toda** venta
    tiene al menos una cuota —la implícita del plazo por defecto— para que la
    consulta de antigüedad tenga un solo camino de código.
    """

    __tablename__ = "cuotas"
    __table_args__ = (
        UniqueConstraint("venta_id", "numero", name="uq_cuotas_venta_id_numero"),
        CheckConstraint("monto_usd > 0", name="monto_positivo"),
        CheckConstraint("monto_abonado_usd >= 0", name="abonado_no_negativo"),
        CheckConstraint("monto_abonado_usd <= monto_usd", name="abonado_no_supera_monto"),
        Index(
            "ix_cuotas_impagas",
            "fecha_vencimiento",
            postgresql_where="monto_abonado_usd < monto_usd",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    venta_id: Mapped[int] = mapped_column(
        ForeignKey("ventas.id", ondelete="CASCADE"), nullable=False
    )
    numero: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    fecha_vencimiento: Mapped[date] = mapped_column(Date, nullable=False)
    monto_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    #: Mantenido por trigger desde `pagos`.
    monto_abonado_usd: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default="0"
    )
    #: True cuando la generó el plazo por defecto, no un plan explícito.
    implicita: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    venta: Mapped[Venta] = relationship("Venta", back_populates="cuotas")

    @property
    def saldo_usd(self) -> Decimal:
        return self.monto_usd - self.monto_abonado_usd

    @property
    def esta_pagada(self) -> bool:
        return self.monto_abonado_usd >= self.monto_usd
