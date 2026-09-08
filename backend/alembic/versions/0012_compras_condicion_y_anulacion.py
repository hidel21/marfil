"""condicion de la compra y su anulacion

Dos huecos que aparecieron al usar el sistema:

**La condicion.** Una compra puede ser de contado, a credito, en consignacion o un
anticipo, y de eso depende si el monto sale del fondo hoy o entra a cuentas por
pagar. Hasta ahora `lotes_compra` guardaba el canal de pago pero no la condicion, asi
que las cuatro se veian iguales.

`condicion` queda **anulable** a proposito. De los lotes ya cargados no sabemos en que
condicion se compraron, y poner `contado` por defecto afirmaria algo que nadie
verifico: pareceria que ya salieron del fondo. Se pide en las compras nuevas y las
viejas quedan en NULL, que se lee como "no consta".

**La anulacion.** `ventas` ya tenia `anulada_at` con autor y motivo; `lotes_compra` no
tenia nada, asi que una compra mal cargada solo se podia borrar. Se replican las tres
columnas para que la correccion deje rastro en vez de borrarlo.

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONDICIONES = ("contado", "credito", "consignacion", "anticipo")


def upgrade() -> None:
    condicion = sa.Enum(*CONDICIONES, name="condicion_compra")
    condicion.create(op.get_bind(), checkfirst=True)

    op.add_column("lotes_compra", sa.Column("condicion", condicion, nullable=True))
    op.add_column(
        "lotes_compra", sa.Column("anulada_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "lotes_compra",
        sa.Column(
            "anulada_por_usuario_id",
            sa.Integer(),
            sa.ForeignKey("usuarios.id", name="fk_lotes_compra_anulada_por_usuario_id_usuarios"),
            nullable=True,
        ),
    )
    op.add_column("lotes_compra", sa.Column("motivo_anulacion", sa.Text(), nullable=True))

    # Las consultas de cuentas por pagar filtran por condicion y por no anuladas.
    op.create_index(
        "ix_lotes_compra_condicion_vigente",
        "lotes_compra",
        ["condicion"],
        postgresql_where=sa.text("anulada_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_lotes_compra_condicion_vigente", table_name="lotes_compra")
    for columna in ("motivo_anulacion", "anulada_por_usuario_id", "anulada_at", "condicion"):
        op.drop_column("lotes_compra", columna)
    sa.Enum(name="condicion_compra").drop(op.get_bind(), checkfirst=True)
