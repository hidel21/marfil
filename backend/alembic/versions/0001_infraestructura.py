"""infraestructura: extensiones, enums, tablas nuevas y auditoria por trigger

Revision aditiva. Streamlit sigue funcionando despues de esta: no se toca ninguna
columna que `database.py` lea, con una sola excepcion documentada abajo.

Que hace, en orden:
 0. Si la base esta vacia, crea la forma legacy (app/db/sql/esquema_legacy.sql).
    Asi la cadena se puede replayar en cualquier entorno y no solo sobre la base
    viva: los dos caminos convergen en el mismo esquema.
 1. Extensiones (citext, unaccent, pg_trgm, btree_gist, pgcrypto).
 2. Los 18 enums nativos. Nativos y no VARCHAR+CHECK para que el vocabulario sea
    descubrible con `enum_range` y no pueda derivar: hoy hay tres vocabularios
    distintos para la misma idea (`ventas.estatus`, `compras.estatus`, `cuotas.estado`).
 3. Suelta `items_venta` y `cuotas` (0 filas verificadas, y Streamlit no las
    consulta) y recrea `cuotas` con su forma nueva. El bloque de oferta
    (proveedores, compras, pagos_compra, gastos) NO se toca: tambien esta vacio,
    pero Streamlit escribe en el, asi que se difiere a 0009.
 4. Renombra importaciones_excel -> importaciones y filas_excel -> filas_importadas,
    y la columna no-ASCII `pestaña` -> `hoja`. Las 322 filas de linaje se conservan.
    **Es el unico punto visible para Streamlit**: `database.py` hay que parchearlo
    en el mismo commit.
 5. Crea las 18 tablas nuevas (DDL congelado en app/db/sql/esquema_0001.sql).
 6. Ajusta `socios` (usuario_id, updated_at, precision del capital).
 7. Instala fn_auditar() + los triggers de saldo, inmutabilidad y stock.
 8. Cuelga la auditoria de las tablas que ya existen en su forma final.

Verificacion despues de aplicar:
    productos 248 | ventas 30 | pagos 31 | socios 3 | filas_importadas 322

Revision ID: 0001
Revises: 0000
Create Date: 2026-08-22

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.db.sql import leer_sql

revision: str = "0001"
down_revision: str | None = "0000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


EXTENSIONES = ("citext", "unaccent", "pg_trgm", "btree_gist", "pgcrypto")

# (nombre del tipo, valores). El orden de los valores importa: agregar uno al final
# despues es un ALTER TYPE barato; insertarlo en el medio, no.
ENUMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("rol_usuario", ("admin", "vendedor", "afiliado")),
    ("estado_producto", ("activo", "borrador_por_revisar", "descatalogado", "fusionado")),
    ("modelo_precio", ("costo", "lista")),
    ("nivel_precio", ("publico", "team", "revendedor")),
    ("moneda", ("USD", "VES", "USDT")),
    (
        "canal_pago",
        (
            "pago_movil",
            "transferencia",
            "efectivo_usd",
            "efectivo_bs",
            "binance",
            "usdt",
            "zelle",
            "otro",
        ),
    ),
    ("estado_cobro", ("pagada", "pendiente_sin_abonos", "pendiente_parcial", "anulada")),
    ("tipo_movimiento_pago", ("abono", "reverso", "ajuste")),
    ("tipo_tasa", ("bcv", "binance", "usdt_ve", "paralelo")),
    (
        "origen_tasa",
        (
            "api_usdtve",
            "api_dolarapi",
            "manual",
            "seed_historico",
            "sintetizada_migracion",
        ),
    ),
    ("confianza_dato", ("alta", "media", "baja")),
    (
        "estado_recordatorio",
        (
            "borrador",
            "listo",
            "enviando",
            "enviado",
            "entregado",
            "leido",
            "fallido",
            "omitido",
        ),
    ),
    ("motivo_omision", ("cooldown", "sin_telefono", "ya_pagado", "limite_mensual", "manual")),
    (
        "tipo_movimiento_stock",
        ("compra", "venta", "ajuste", "devolucion", "muestra", "carga_inicial"),
    ),
    ("accion_auditoria", ("INSERT", "UPDATE", "DELETE")),
    ("actor_auditoria", ("usuario", "sistema", "migracion")),
    ("metodo_enlace", ("exacto", "fuzzy", "manual", "heuristica")),
    ("estado_registro", ("activo", "inactivo", "fusionado")),
)

# Vacias, verificadas en 0 filas y **que Streamlit no consulta**: se sueltan y se
# recrean con su forma nueva.
#
# Deliberadamente NO estan aca `proveedores`, `compras`, `pagos_compra` ni
# `gastos_generales`: tambien tienen 0 filas, pero Streamlit escribe en ellas desde
# las pestanas de compras y finanzas. Ese bloque se difiere a la revision 0009
# (fase 5), cuando el ETL carga los lotes de GASTOS y la API se queda con el tema.
LEGACY_VACIAS = ("items_venta", "cuotas")

# Tablas a las que se les cuelga la auditoria en esta revision.
TABLAS_AUDITADAS = (
    "usuarios",
    "clientes",
    "clientes_alias",
    "productos",
    "productos_alias",
    "ventas",
    "venta_items",
    "cuotas",
    "pagos",
    "socios",
    "parametros_precio",
    "configuracion",
    "plantillas_mensaje",
    "recordatorios",
)


def _verificar_vacias(conexion) -> None:
    """No soltar una tabla sin mirarla: si alguien cargó datos, la migración para."""
    for tabla in LEGACY_VACIAS:
        existe = conexion.execute(
            sa.text("SELECT to_regclass(:t) IS NOT NULL"), {"t": f"public.{tabla}"}
        ).scalar()
        if not existe:
            continue
        filas = conexion.execute(sa.text(f'SELECT count(*) FROM "{tabla}"')).scalar()
        if filas:
            raise RuntimeError(
                f"La tabla '{tabla}' tiene {filas} filas y la revisión 0001 esperaba 0. "
                "Migrá esos datos a mano antes de continuar: 0001 la suelta para "
                "recrearla con otra forma."
            )


def upgrade() -> None:
    conexion = op.get_bind()

    # 0. Sobre una base vacia, crear primero la forma legacy.
    #
    # Las 12 tablas de la app Streamlit nacieron de `create_all()`, nunca de una
    # migracion. Sin este paso la cadena solo se puede aplicar sobre la base viva:
    # en CI, en staging o en la maquina de otro socio, 0001 arrancaria renombrando
    # `filas_excel` y fallaria donde esa tabla nunca existio. Con esto los dos
    # caminos —base viva y base vacia— convergen en el mismo esquema.
    if not conexion.execute(
        sa.text("SELECT to_regclass('public.ventas') IS NOT NULL")
    ).scalar():
        op.execute(leer_sql("esquema_legacy"))

    # 1. Extensiones
    for ext in EXTENSIONES:
        op.execute(f'CREATE EXTENSION IF NOT EXISTS "{ext}"')

    # 2. Enums
    for nombre, valores in ENUMS:
        literales = ", ".join(f"'{v}'" for v in valores)
        op.execute(
            f"DO $$ BEGIN "
            f"IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{nombre}') THEN "
            f"CREATE TYPE {nombre} AS ENUM ({literales}); "
            f"END IF; END $$;"
        )

    # 3. Tablas legacy vacías
    _verificar_vacias(conexion)
    for tabla in LEGACY_VACIAS:
        op.execute(f'DROP TABLE IF EXISTS "{tabla}" CASCADE')

    # 4. Renombres de linaje
    if conexion.execute(
        sa.text("SELECT to_regclass('public.importaciones_excel') IS NOT NULL")
    ).scalar():
        op.rename_table("importaciones_excel", "importaciones")
    if conexion.execute(
        sa.text("SELECT to_regclass('public.filas_excel') IS NOT NULL")
    ).scalar():
        op.rename_table("filas_excel", "filas_importadas")
        op.alter_column("filas_importadas", "pestaña", new_column_name="hoja")

    # `datos` era JSON; JSONB para poder indexarlo con GIN.
    op.execute("ALTER TABLE filas_importadas ALTER COLUMN datos TYPE JSONB USING datos::jsonb")
    op.alter_column("filas_importadas", "hoja", type_=sa.String(64), existing_nullable=False)
    op.add_column(
        "importaciones",
        sa.Column("mapeo_version", sa.String(16), nullable=False, server_default="v1"),
    )
    op.add_column(
        "importaciones",
        sa.Column("estado", sa.String(16), nullable=False, server_default="archivado"),
    )
    op.add_column("importaciones", sa.Column("importado_por_usuario_id", sa.Integer()))
    op.alter_column(
        "importaciones", "archivo_hash", type_=sa.String(64), existing_nullable=False
    )
    op.create_unique_constraint(
        "uq_filas_importadas_ubicacion",
        "filas_importadas",
        ["importacion_id", "hoja", "numero_fila"],
    )
    op.create_index(
        "ix_filas_importadas_datos", "filas_importadas", ["datos"], postgresql_using="gin"
    )

    # 5. Las 23 tablas nuevas, DDL congelado
    op.execute(leer_sql("esquema_0001"))

    # 6. socios: identidad y precisión
    op.add_column("socios", sa.Column("usuario_id", sa.Integer()))
    op.add_column(
        "socios",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.alter_column(
        "socios", "capital_invertido", type_=sa.Numeric(14, 2), existing_nullable=False
    )
    op.create_unique_constraint("uq_socios_usuario_id", "socios", ["usuario_id"])
    op.create_foreign_key(
        "fk_socios_usuario_id_usuarios", "socios", "usuarios", ["usuario_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_importaciones_importado_por_usuario_id_usuarios",
        "importaciones",
        "usuarios",
        ["importado_por_usuario_id"],
        ["id"],
    )

    # 7. Funciones y triggers
    op.execute(leer_sql("fn_auditar"))
    op.execute(leer_sql("triggers_saldo"))

    # Solo se cuelgan los triggers cuyas columnas ya existen.
    #
    # Los que tocan ventas.total_usd / saldo_usd / fecha_vencimiento se cuelgan en
    # 0005 y 0006, cuando esas columnas existen. No es cosmético: entre 0001 y 0006
    # Streamlit sigue registrando abonos, y un trigger AFTER INSERT ON pagos que
    # lea ventas.total_usd le rompería el cobro al negocio en producción.
    #
    # `trg_pagos_inmutable` sí va acá y es seguro: Streamlit inserta pagos pero
    # nunca los edita ni los borra, así que desde hoy el libro es append-only.
    op.execute(
        """
        CREATE TRIGGER trg_pagos_inmutable
        BEFORE UPDATE OR DELETE ON pagos
        FOR EACH ROW EXECUTE FUNCTION fn_pagos_inmutable();

        CREATE TRIGGER trg_movimientos_stock
        AFTER INSERT OR UPDATE OR DELETE ON movimientos_stock
        FOR EACH ROW EXECUTE FUNCTION fn_recalcular_stock();

        """
    )

    # 8. Auditoría
    for tabla in TABLAS_AUDITADAS:
        op.execute(
            f"CREATE TRIGGER trg_auditar_{tabla} "
            f"AFTER INSERT OR UPDATE OR DELETE ON {tabla} "
            f"FOR EACH ROW EXECUTE FUNCTION fn_auditar()"
        )

    # La app no puede reescribir la auditoría: solo insertar y leer.
    op.execute("REVOKE UPDATE, DELETE ON auditoria FROM PUBLIC")


def downgrade() -> None:
    conexion = op.get_bind()

    for tabla in TABLAS_AUDITADAS:
        op.execute(f"DROP TRIGGER IF EXISTS trg_auditar_{tabla} ON {tabla}")

    for trigger, tabla in (
        ("trg_pagos_inmutable", "pagos"),
        ("trg_movimientos_stock", "movimientos_stock"),
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {tabla}")

    for fn in (
        "fn_auditar",
        "fn_pagos_inmutable",
        "fn_recalcular_totales_venta",
        "fn_recalcular_saldo_venta(integer)",
        "fn_pagos_actualizan_saldo",
        "fn_actualizar_vencimiento_venta",
        "fn_recalcular_stock",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {fn} CASCADE")

    op.drop_constraint("fk_socios_usuario_id_usuarios", "socios", type_="foreignkey")
    op.drop_constraint("uq_socios_usuario_id", "socios", type_="unique")
    op.drop_column("socios", "usuario_id")
    op.drop_column("socios", "updated_at")

    op.drop_constraint(
        "fk_importaciones_importado_por_usuario_id_usuarios", "importaciones", type_="foreignkey"
    )

    # Las tablas nuevas, hijas primero.
    for tabla in (
        "enlaces_importacion",
        "recordatorios",
        "plantillas_version",
        "plantillas_mensaje",
        "jobs_ejecuciones",
        "conciliaciones",
        "auditoria",
        "tasas_cambio",
        "configuracion",
        "parametros_precio",
        "cuotas",
        "venta_items",
        "movimientos_stock",
        "productos_alias",
        "clientes_alias",
        "refresh_tokens",
        "usuarios",
        "clientes",
    ):
        op.execute(f'DROP TABLE IF EXISTS "{tabla}" CASCADE')

    op.drop_index("ix_filas_importadas_datos", table_name="filas_importadas")
    op.drop_constraint("uq_filas_importadas_ubicacion", "filas_importadas", type_="unique")
    op.drop_column("importaciones", "importado_por_usuario_id")
    op.drop_column("importaciones", "estado")
    op.drop_column("importaciones", "mapeo_version")
    if conexion.execute(
        sa.text("SELECT to_regclass('public.filas_importadas') IS NOT NULL")
    ).scalar():
        op.alter_column("filas_importadas", "hoja", new_column_name="pestaña")
        op.rename_table("filas_importadas", "filas_excel")
    if conexion.execute(
        sa.text("SELECT to_regclass('public.importaciones') IS NOT NULL")
    ).scalar():
        op.rename_table("importaciones", "importaciones_excel")

    # Recrear las dos legacy que 0001 soltó, con su forma original, para que
    # Streamlit vuelva a arrancar tras un downgrade.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS items_venta (
            id SERIAL PRIMARY KEY, venta_id INTEGER NOT NULL REFERENCES ventas(id),
            producto_id INTEGER NOT NULL REFERENCES productos(id),
            cantidad INTEGER NOT NULL, precio_unitario NUMERIC(10,2) NOT NULL,
            subtotal NUMERIC(10,2) NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cuotas (
            id SERIAL PRIMARY KEY, venta_id INTEGER NOT NULL REFERENCES ventas(id),
            numero INTEGER NOT NULL, fecha_vencimiento DATE NOT NULL,
            monto NUMERIC(10,2) NOT NULL, estado VARCHAR(20) NOT NULL DEFAULT 'pendiente'
        );
        """
    )

    for nombre, _ in reversed(ENUMS):
        op.execute(f"DROP TYPE IF EXISTS {nombre}")
