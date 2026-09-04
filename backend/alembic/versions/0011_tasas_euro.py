"""tipos de tasa para el euro

`tipo_tasa` nacio con las cuatro series que la operacion usaba: bcv, binance,
usdt_ve y paralelo. Al conectar dolarapi entran dos series mas que la API publica y
que sirven para cotizar a clientes que pagan en euros.

`ALTER TYPE ... ADD VALUE` corre dentro de la transaccion en PostgreSQL 12+, pero el
valor nuevo no se puede USAR hasta que la transaccion cierra. Por eso esta revision
solo declara los valores y no inserta ninguna fila: el primer snapshot que los use ya
corre en otra transaccion.

`downgrade()` no los quita: PostgreSQL no sabe eliminar un valor de un enum sin
recrear el tipo y reescribir cada columna que lo usa, y no vale la pena arriesgar la
tabla de tasas para deshacer dos etiquetas inertes.

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIPOS_NUEVOS = ("euro", "euro_paralelo")
#: `api_usdtve` era otro servicio. El USDT ahora sale del P2P de Binance y merece su
#: propia etiqueta: al auditar una tasa rara, lo primero que se pregunta es de donde
#: salio.
ORIGENES_NUEVOS = ("api_binance",)


def upgrade() -> None:
    for valor in TIPOS_NUEVOS:
        op.execute(f"ALTER TYPE tipo_tasa ADD VALUE IF NOT EXISTS '{valor}'")
    for valor in ORIGENES_NUEVOS:
        op.execute(f"ALTER TYPE origen_tasa ADD VALUE IF NOT EXISTS '{valor}'")


def downgrade() -> None:
    pass
