"""Plantillas de mensaje y log de recordatorios.

Dos cosas que están diseñadas para no tener que migrar después:

1. **`estado` es el ciclo de vida completo** (`BORRADOR..LEIDO`) aunque el proveedor
   manual solo llegue a `ENVIADO`, y `proveedor` / `proveedor_mensaje_id` son
   columnas nulables desde el día uno. Enchufar la WhatsApp Cloud API es un cambio
   de configuración más un webhook, no una migración más una reescritura de la UI.

2. **`cuerpo_renderizado` se congela al generar.** Editar una plantilla después no
   puede dejarte sin poder probar qué se le dijo al cliente: una discusión se
   responde con "este es literalmente el mensaje que enviamos el 14/08".

"Nunca se notifica dos veces" es el índice único `uq_recordatorios_dia`, no lógica
de aplicación: un segundo recordatorio el mismo día para la misma venta es un 23505
en la base, haga lo que haga quien llame. La regla blanda
(`DIAS_ENTRE_RECORDATORIOS`) va en el servicio; el índice es la red.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
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
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._comun import enum_pg
from app.models.enums import EstadoRecordatorio, MotivoOmision

TIPO_POR_VENCER = "recordatorio_por_vencer"
TIPO_VENCIDO = "recordatorio_vencido"
TIPO_MOROSO = "recordatorio_moroso"
TIPO_CONFIRMACION_PAGO = "confirmacion_pago"
TIPO_PLAN_CUOTAS = "plan_de_pago"


class PlantillaMensaje(Base):
    __tablename__ = "plantillas_mensaje"

    clave: Mapped[str] = mapped_column(String(48), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    #: whatsapp | email
    canal: Mapped[str] = mapped_column(String(24), nullable=False, server_default="whatsapp")
    #: Jinja2. Texto plano: WhatsApp no renderiza marcado rico.
    cuerpo: Mapped[str] = mapped_column(Text, nullable=False)
    #: Las variables que esta plantilla declara usar, para validar al guardar.
    variables: Mapped[list | None] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    actualizado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PlantillaVersion(Base):
    """Historial de plantillas: permite ver el diff y restaurar sin miedo."""

    __tablename__ = "plantillas_version"
    __table_args__ = (
        Index("ix_plantillas_version_clave", "plantilla_clave", "version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plantilla_clave: Mapped[str] = mapped_column(
        ForeignKey("plantillas_mensaje.clave", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    cuerpo: Mapped[str] = mapped_column(Text, nullable=False)
    guardado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Recordatorio(Base):
    __tablename__ = "recordatorios"
    __table_args__ = (
        # La red anti-spam, a nivel de base de datos.
        Index(
            "uq_recordatorios_dia",
            "venta_id",
            "canal",
            "dia_generacion",
            unique=True,
            postgresql_where="estado <> 'omitido'",
        ),
        Index("ix_recordatorios_cliente", "cliente_id", "generado_at"),
        Index("ix_recordatorios_estado", "estado"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), nullable=False)
    venta_id: Mapped[int | None] = mapped_column(ForeignKey("ventas.id"))
    cuota_id: Mapped[int | None] = mapped_column(ForeignKey("cuotas.id"))
    #: Cuando el recordatorio agrupa varias ventas del mismo cliente.
    ventas_incluidas: Mapped[list[int] | None] = mapped_column(ARRAY(Integer))

    #: whatsapp_manual | whatsapp_api | email
    canal: Mapped[str] = mapped_column(String(24), nullable=False, server_default="whatsapp_manual")
    plantilla_clave: Mapped[str] = mapped_column(
        ForeignKey("plantillas_mensaje.clave"), nullable=False
    )
    plantilla_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    #: Congelado al generar. Ver el docstring del módulo.
    cuerpo_renderizado: Mapped[str] = mapped_column(Text, nullable=False)
    destino: Mapped[str | None] = mapped_column(String(64))

    #: Los números al momento de generar: un recordatorio viejo no debe recalcularse.
    saldo_usd_al_generar: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tasa_al_generar: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    dias_mora_al_generar: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    estado: Mapped[EstadoRecordatorio] = mapped_column(
        enum_pg(EstadoRecordatorio),
        nullable=False,
        server_default=EstadoRecordatorio.BORRADOR.value,
    )
    motivo_omision: Mapped[MotivoOmision | None] = mapped_column(enum_pg(MotivoOmision))

    generado_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    enviado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    marcado_enviado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))

    proveedor: Mapped[str | None] = mapped_column(String(32))
    proveedor_mensaje_id: Mapped[str | None] = mapped_column(String(128))
    error: Mapped[str | None] = mapped_column(Text)

    #: Columna generada: `generado_at::date`. Es la que entra en el índice único.
    dia_generacion: Mapped[date] = mapped_column(
        Date, Computed("(generado_at AT TIME ZONE 'UTC')::date", persisted=True), nullable=False
    )

    cliente: Mapped[Cliente] = relationship("Cliente")  # noqa: F821
