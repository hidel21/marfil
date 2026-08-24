"""El libro de pagos: append-only, impuesto en la base de datos.

Un trigger levanta excepción ante `DELETE` y ante cualquier `UPDATE` que toque
`monto_usd`, `monto_moneda`, `tasa_aplicada`, `venta_id` o `fecha`. Las correcciones
son filas `tipo='reverso'` con monto negativo apuntando a `anula_pago_id`.

Eso hace dos cosas de una: la historia no se puede reescribir (solo extender), y la
auditoría sale gratis. También es lo que permite que el rollback de la fase 4 no
necesite un restore: lo que la API escribió mal es visible y reversible.

El campo `moneda` con `EFECTIVO_USD` es la ruta explícita que reemplaza el hack de
guardar `tasa_bcv = 1.00` para un pago en dólares. Esos dos registros existen en la
base y contaminaban el total en bolívares con 28 Bs que nunca fueron bolívares.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._comun import enum_pg
from app.models.enums import (
    CanalPago,
    ConfianzaDato,
    Moneda,
    OrigenTasa,
    TipoMovimientoPago,
)


class Pago(Base):
    __tablename__ = "pagos"
    __table_args__ = (
        # El signo distingue abono de reverso. Sin esto un reverso positivo
        # aumentaría el cobrado en vez de corregirlo.
        CheckConstraint(
            "(tipo = 'reverso' AND monto_usd < 0) OR (tipo <> 'reverso' AND monto_usd > 0)",
            name="signo_segun_tipo",
        ),
        CheckConstraint(
            "(moneda = 'USD' AND tasa_aplicada = 1) OR (moneda <> 'USD' AND tasa_aplicada > 1)",
            name="tasa_coherente_con_moneda",
        ),
        CheckConstraint(
            "tipo <> 'reverso' OR anula_pago_id IS NOT NULL",
            name="reverso_apunta_a_pago",
        ),
        # Guardia de doble contabilización. Compuesto y no solo por referencia
        # porque las referencias reales son de 3-4 dígitos ('172', '542', '666')
        # y colisionan entre meses.
        Index(
            "uq_pagos_referencia",
            "referencia",
            "monto_moneda",
            "fecha",
            unique=True,
            postgresql_where="referencia IS NOT NULL AND tipo = 'abono'",
        ),
        Index("ix_pagos_venta_fecha", "venta_id", "fecha"),
        Index("ix_pagos_fecha", "fecha"),
        Index("ix_pagos_cuota", "cuota_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    venta_id: Mapped[int] = mapped_column(ForeignKey("ventas.id"), nullable=False)
    #: NULL cuando la venta no tiene plan de cuotas.
    cuota_id: Mapped[int | None] = mapped_column(ForeignKey("cuotas.id"))
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    tipo: Mapped[TipoMovimientoPago] = mapped_column(
        enum_pg(TipoMovimientoPago),
        nullable=False,
        server_default=TipoMovimientoPago.ABONO.value,
    )

    moneda: Mapped[Moneda] = mapped_column(enum_pg(Moneda), nullable=False)
    #: Tal como se recibió: bolívares, dólares en efectivo, USDT.
    monto_moneda: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    tasa_aplicada: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    tasa_id: Mapped[int | None] = mapped_column(ForeignKey("tasas_cambio.id"))
    origen_tasa: Mapped[OrigenTasa] = mapped_column(enum_pg(OrigenTasa), nullable=False)
    confianza_tasa: Mapped[ConfianzaDato] = mapped_column(
        enum_pg(ConfianzaDato), nullable=False, server_default=ConfianzaDato.ALTA.value
    )

    #: El monto del libro, con signo. Lo calcula el servidor, nunca el cliente.
    monto_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    canal: Mapped[CanalPago] = mapped_column(enum_pg(CanalPago), nullable=False)
    #: NULLABLE: el efectivo no tiene referencia bancaria.
    referencia: Mapped[str | None] = mapped_column(String(64))
    comprobante_url: Mapped[str | None] = mapped_column(Text)

    #: Solo linaje: el viejo "Bloque de Pago" 1/2/3, que imitaba las tres columnas
    #: fijas del Excel y nunca fue un plan de cuotas real.
    nro_bloque: Mapped[int | None] = mapped_column(SmallInteger)

    anula_pago_id: Mapped[int | None] = mapped_column(
        ForeignKey("pagos.id", name="fk_pagos_anula_pago_id_pagos")
    )
    motivo: Mapped[str | None] = mapped_column(Text)
    registrado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    notas: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    venta: Mapped[Venta] = relationship("Venta", back_populates="pagos")  # noqa: F821
    cuota: Mapped[Cuota | None] = relationship("Cuota")  # noqa: F821

    @property
    def es_reverso(self) -> bool:
        return self.tipo == TipoMovimientoPago.REVERSO

    @property
    def tasa_es_confiable(self) -> bool:
        return self.origen_tasa != OrigenTasa.SINTETIZADA_MIGRACION
