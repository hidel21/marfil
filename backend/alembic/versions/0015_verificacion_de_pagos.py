"""verificacion bancaria de los pagos

Un pago registrado no es un pago recibido. El pago movil se carga con la referencia
que manda el cliente, y la plata llega —o no— a la cuenta BNC de Gregor. Hasta ahora
nada distinguia un abono revisado contra el banco de uno anotado de buena fe.

**Por que una tabla aparte y no columnas en `pagos`.** El libro de pagos es
inmutable por trigger: un abono no se edita, se reversa. Una columna `confirmado`
obligaria a abrir una excepcion en esa regla para cada confirmacion, y una excepcion
asi termina siendo el lugar por donde alguien edita un monto. La verificacion es un
hecho distinto, posterior y de otra persona; va en su propia fila.

**Un pago sin fila esta "por confirmar".** No hace falta sembrar nada: todos los
pagos existentes quedan pendientes desde el momento en que esta tabla existe, que es
justamente lo que se pidio ("desconciliar todos para que Gregor los confirme").

**Pendiente no deja de descontar la deuda.** Es una decision de los socios: si el
pago se cargo, el cliente ya no debe eso, y Cobranza no tiene que perseguir a quien
pago solo porque falta revisar el banco. Si Gregor lo rechaza, se reversa y la deuda
vuelve, con el motivo escrito.

Revision ID: 0015
Revises: 0014
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "verificaciones_pago",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "pago_id",
            sa.Integer(),
            sa.ForeignKey("pagos.id", name="fk_verificaciones_pago_pago_id_pagos"),
            nullable=False,
        ),
        sa.Column("estado", sa.String(16), nullable=False),
        sa.Column(
            "usuario_id",
            sa.Integer(),
            sa.ForeignKey("usuarios.id", name="fk_verificaciones_pago_usuario_id_usuarios"),
            nullable=True,
        ),
        sa.Column(
            "verificado_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("nota", sa.Text(), nullable=True),
        # Un pago se verifica una vez. Cambiar de opinion despues de rechazar no tiene
        # sentido (el rechazo ya lo reverso), y despues de confirmar se reversa a mano.
        sa.UniqueConstraint("pago_id", name="uq_verificaciones_pago_pago_id"),
        sa.CheckConstraint(
            "estado IN ('confirmado', 'rechazado')", name="ck_verificaciones_pago_estado"
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_auditar_verificaciones_pago AFTER INSERT OR UPDATE OR DELETE "
        "ON verificaciones_pago FOR EACH ROW EXECUTE FUNCTION fn_auditar()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_auditar_verificaciones_pago ON verificaciones_pago")
    op.drop_table("verificaciones_pago")
