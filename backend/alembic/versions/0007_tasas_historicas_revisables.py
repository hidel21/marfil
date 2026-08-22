"""tasas históricas revisables

Hace visible el origen de las tasas deducidas durante la migración. No modifica pagos
ni saldos: crea un snapshot diario de confianza baja a partir de lo que ya existe,
para que un administrador pueda reemplazarlo por la tasa verificada desde la app.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO tasas_cambio (fecha, tipo, valor, origen, confianza, payload)
        SELECT p.fecha, 'bcv'::tipo_tasa,
               round(avg(p.tasa_aplicada), 8),
               'sintetizada_migracion'::origen_tasa,
               'baja'::confianza_dato,
               jsonb_build_object(
                   'migracion', '0007',
                   'metodo', 'promedio_de_tasas_deducidas_sin_mover_dinero',
                   'pagos', count(*)
               )
          FROM pagos p
         WHERE p.fecha IS NOT NULL
           AND p.tasa_aplicada > 1
           AND p.origen_tasa = 'sintetizada_migracion'
         GROUP BY p.fecha
        ON CONFLICT (fecha, tipo) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM tasas_cambio WHERE payload ->> 'migracion' = '0007'")
