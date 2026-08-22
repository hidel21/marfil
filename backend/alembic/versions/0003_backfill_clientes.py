"""backfill: la tabla de clientes, desde los nombres sueltos de ventas

`ventas.cliente` y `pagos.cliente` eran texto libre copiado. Sin una tabla de
clientes no hay donde guardar un telefono, y sin telefono la notificacion por
WhatsApp es imposible: esta revision es el requisito previo de esa funcion.

Que hace:
 - Agrupa los nombres distintos de `ventas.cliente` por su clave de unicidad
   (minusculas, sin acentos, sin espacios) y crea un cliente por grupo.
 - Guarda **cada grafia observada** en `clientes_alias`, incluida la canonica. El
   historico sigue siendo consultable tal como se tecleo.
 - Marca `es_socio` en los clientes cuyo nombre coincide con un socio: Gregor y
   Hidelberg compran para si mismos, y su autoconsumo no es ingreso real.
 - Deja una nota de revision donde una clave es prefijo de otra ('Ricardo' vs
   'Ricardo Palacios'): **no fusiona**. Fusionar clientes en silencio es como se
   pierde una cuenta por cobrar; decidirlo es del dueno, y para eso esta la pantalla
   de calidad de datos.
 - `telefono_e164` queda NULL en todos: **ninguna fuente tiene un solo telefono**.
   Ni la base, ni el libro original, ni el v2. Es un bloqueo conocido de la funcion
   de recordatorios y se resuelve cargandolos desde la app.

NO toca `ventas`: la FK `cliente_id` se puebla en 0005. Asi esta revision es solo
inserciones y su downgrade es un DELETE limpio.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-22

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.normalizacion import clave_nombre
from app.etl.canonico import agrupar_por_clave, es_probable_prefijo, mejor_grafia

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conexion = op.get_bind()
    op.execute("SELECT set_config('app.actor_tipo', 'migracion', true)")

    nombres = [
        n
        for (n,) in conexion.execute(
            sa.text(
                "SELECT DISTINCT cliente FROM ventas WHERE cliente IS NOT NULL "
                "AND btrim(cliente) <> '' "
                "UNION "
                "SELECT DISTINCT cliente FROM pagos WHERE cliente IS NOT NULL "
                "AND btrim(cliente) <> ''"
            )
        )
    ]
    if not nombres:
        return

    grupos = agrupar_por_clave(nombres)

    # Los socios que tambien compran.
    claves_socios = {
        clave_nombre(n) for (n,) in conexion.execute(sa.text("SELECT nombre FROM socios"))
    }

    # Prefijos: candidatos a revision manual, nunca a fusion automatica.
    claves = sorted(grupos)
    notas: dict[str, str] = {}
    for corta in claves:
        parecidas = [larga for larga in claves if es_probable_prefijo(corta, larga)]
        if parecidas:
            nombres_parecidos = ", ".join(mejor_grafia(grupos[k]) for k in parecidas)
            notas[corta] = (
                f"Revisar: podria ser el mismo cliente que {nombres_parecidos}. "
                "No se fusiono automaticamente."
            )

    for clave, variantes in grupos.items():
        canonico = mejor_grafia(variantes)
        cliente_id = conexion.execute(
            sa.text(
                "INSERT INTO clientes (nombre, nombre_normalizado, es_socio, notas) "
                "VALUES (:nombre, :clave, :socio, :notas) RETURNING id"
            ),
            {
                "nombre": canonico,
                "clave": clave,
                "socio": clave in claves_socios,
                "notas": notas.get(clave),
            },
        ).scalar_one()

        # Todas las grafias observadas, mas la canonica si difiere de todas.
        alias = list(dict.fromkeys([*variantes, canonico]))
        for grafia in alias:
            conexion.execute(
                sa.text(
                    "INSERT INTO clientes_alias (cliente_id, alias, alias_normalizado, origen) "
                    "VALUES (:c, :alias, :clave, 'db_legacy') "
                    "ON CONFLICT (alias_normalizado) DO NOTHING"
                ),
                {"c": cliente_id, "alias": grafia, "clave": clave},
            )


def downgrade() -> None:
    op.execute("DELETE FROM clientes_alias")
    op.execute("DELETE FROM clientes")
