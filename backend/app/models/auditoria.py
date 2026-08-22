"""Log de auditoría, conciliaciones y corridas de jobs.

`auditoria` la alimentan **triggers de base de datos**, no la aplicación. La razón
es concreta: el código actual tiene tres caminos de escritura que evitan
`register_payment` y un migrador de DDL que corre SQL crudo. Auditar en Python
audita solo los caminos que uno recordó.

El actor sale de `current_setting('app.usuario_id', true)`, que la sesión pone con
`SET LOCAL` en cada transacción (ver `app/db/session.py`). Un cambio hecho por el
ETL o por un job queda con actor nulo y `actor_tipo` en 'sistema' o 'migracion'.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._comun import enum_pg
from app.models.enums import AccionAuditoria, ActorAuditoria


class EventoAuditoria(Base):
    """Append-only. La app no tiene UPDATE ni DELETE sobre esta tabla."""

    __tablename__ = "auditoria"
    __table_args__ = (
        Index("ix_auditoria_entidad", "tabla", "registro_id", "ocurrido_at"),
        Index("ix_auditoria_usuario", "usuario_id", "ocurrido_at"),
        Index("ix_auditoria_ocurrido_at_brin", "ocurrido_at", postgresql_using="brin"),
        # El filtro de "solo excepciones": todo lo que lleva un motivo.
        Index("ix_auditoria_con_motivo", "ocurrido_at", postgresql_where="motivo IS NOT NULL"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ocurrido_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp()
    )
    actor_tipo: Mapped[ActorAuditoria] = mapped_column(
        enum_pg(ActorAuditoria), nullable=False, server_default=ActorAuditoria.SISTEMA.value
    )
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    accion: Mapped[AccionAuditoria] = mapped_column(enum_pg(AccionAuditoria), nullable=False)
    tabla: Mapped[str] = mapped_column(String(48), nullable=False)
    registro_id: Mapped[str] = mapped_column(Text, nullable=False)
    antes: Mapped[dict | None] = mapped_column(JSONB)
    despues: Mapped[dict | None] = mapped_column(JSONB)
    #: Solo las claves que cambiaron: hace legible una fila de UPDATE de un vistazo.
    campos_cambiados: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    motivo: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)


class Conciliacion(Base):
    """El resultado de cada corrida del job nocturno.

    Existe para que un descuadre sea una bandera roja en el dashboard, no una línea
    de log que nadie lee.
    """

    __tablename__ = "conciliaciones"
    __table_args__ = (Index("ix_conciliaciones_tipo_fecha", "tipo", "ejecutado_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ejecutado_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    #: ventas | pagos_bs | stock | cuotas
    tipo: Mapped[str] = mapped_column(String(32), nullable=False)
    filas_revisadas: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    filas_descuadradas: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    detalle: Mapped[dict | None] = mapped_column(JSONB)


class JobEjecucion(Base):
    """Cada corrida de cada job programado.

    Es lo que hace que `/ajustes/automatizaciones` pueda mostrar última corrida,
    próxima y filas afectadas: una automatización que el usuario no puede ver ni
    disparar es una automatización en la que no va a confiar.
    """

    __tablename__ = "jobs_ejecuciones"
    __table_args__ = (Index("ix_jobs_ejecuciones_nombre_inicio", "nombre", "inicio"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(64), nullable=False)
    inicio: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    fin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: corriendo | ok | error
    estado: Mapped[str] = mapped_column(String(16), nullable=False, server_default="corriendo")
    filas_afectadas: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    detalle: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
