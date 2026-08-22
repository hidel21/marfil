"""vistas: la capa de lectura de la API

Reemplazan a las ~30 funciones `load_*_dataframe` de database.py, que existian solo
para alimentar `st.dataframe` y que agrupaban por el TEXTO del nombre del producto
—lo que hacia que dos grafias del mismo perfume fueran dos productos en todos los
reportes—.

Van en SQL y no en Python por dos razones concretas:
 - el drill-down de la pantalla de auditoria necesita abrir cualquier numero agregado
   en las filas que lo produjeron, y con una vista es la misma consulta;
 - `v_calidad_datos` define en un solo lugar que cuenta como problema, asi que el
   numero de la tarjeta y las filas del detalle no pueden discrepar.

Las tres de conciliacion son el pedido de "auditar facilmente" comprimido: muestran
el valor almacenado y el calculado uno al lado del otro, siempre.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-22

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from app.db.sql import leer_sql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VISTAS = (
    "v_calidad_datos",
    "v_demanda_sin_stock",
    "v_stock_bajo",
    "v_rentabilidad_semanal",
    "v_deuda_cliente",
    "v_margen_producto",
    "v_fuga_precio",
    "v_conciliacion_stock",
    "v_conciliacion_pagos",
    "v_conciliacion_ventas",
    "v_cobranza",
    "v_precio_vigente",
)


def upgrade() -> None:
    op.execute(leer_sql("vistas"))


def downgrade() -> None:
    # En orden inverso: v_calidad_datos y v_deuda_cliente dependen de otras.
    for vista in VISTAS:
        op.execute(f"DROP VIEW IF EXISTS {vista} CASCADE")
