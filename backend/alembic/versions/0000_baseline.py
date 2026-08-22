"""baseline: el esquema tal como estaba antes de la migracion

Revisión deliberadamente vacía. Representa las 12 tablas que la app Streamlit creó
con `Base.metadata.create_all()` + `ensure_schema()`, que nunca pasaron por Alembic.
La base viva se marca acá con `alembic stamp 0000` y a partir de este punto todo
cambio de esquema es una revisión.

Estado que representa, verificado el 2026-08-22:
    productos 248 | ventas 30 | pagos 31 | socios 3 | filas_excel 322
    items_venta 0 | cuotas 0 | proveedores 0 | compras 0
    pagos_compra 0 | gastos_generales 0 | importaciones_excel 1

`downgrade()` no borra nada a propósito: bajar de la línea base significaría tirar
la base de producción.

Revision ID: 0000
Revises:
Create Date: 2026-08-22

"""
from __future__ import annotations

from collections.abc import Sequence

revision: str = "0000"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
