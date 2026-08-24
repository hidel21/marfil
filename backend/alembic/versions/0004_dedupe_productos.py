"""dedupe de productos, costo NULL y alias de catalogo

La revision delicada. Tres cosas, en este orden:

**1. `costo = 0` pasa a `costo_usd = NULL`** en los 217 productos sin costo. El
cero-como-desconocido es lo que dejaba que la lista de precios mostrara `$0,00`
como si fuera un precio, y con NULL eso es imposible. Un precio en blanco se ve;
un `$0,00` se cobra.

**2. Dedupe por `(nombre_normalizado, es_original)`, nunca por el nombre solo.**
`bharara king` esta en `PRECIOS PERF TOP QUALITY` *y* en `PRECIOS PERF ORIGINALES`
—de ahi las 3 filas—, y un clon Top Quality y un original son SKUs distintos con
costos distintos. Con esa clave, 3 colapsan a 2 y no a 1. Sobrevive la fila que
tiene costo; el perdedor queda `estado='fusionado'` con su nombre convertido en
alias, asi que el historico sigue resolviendo. El indice unico parcial se crea **al
final**: es la prueba de que el dedupe funciono.

**3. Alias declarados a mano** (backend/seeds/alias_productos.yaml), con la
evidencia de cada decision. Nada de umbrales de similitud: sobre estos mismos datos
el trigram propone 'Victorinox swis army' -> 'VICTORIA' y '212 NYC' -> '212 vip',
que son productos distintos. Lo que no tiene evidencia entra como
`borrador_por_revisar` y aparece en la pantalla de calidad de datos.

**Las columnas legacy de precio NO se sueltan.** `precio_divisa`, `precio_bcv`,
`precio_team`, `precio_revendedor`, `precio_unitario`, `costo` y `precio_original`
quedan marcadas como obsoletas con un COMMENT y se sueltan en el cutover. Soltarlas
aca romperia la pestana de productos de Streamlit sin necesidad: la API lee los
precios de la vista `v_precio_vigente`, asi que las columnas viejas solo estorban,
no molestan.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-22

"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
import yaml

from alembic import op
from app.core.normalizacion import clave_nombre
from app.db.sql import leer_sql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DIR_SEEDS = Path(__file__).resolve().parents[2] / "seeds"

COLUMNAS_OBSOLETAS = (
    ("costo", "reemplazada por costo_usd, que usa NULL para 'desconocido'"),
    ("precio_divisa", "derivada: v_precio_vigente la calcula desde costo_usd"),
    ("precio_bcv", "derivada: v_precio_vigente la calcula desde costo_usd"),
    ("precio_team", "derivada: v_precio_vigente la calcula desde precio_original_usd"),
    ("precio_revendedor", "derivada: v_precio_vigente la calcula desde precio_original_usd"),
    ("precio_original", "reemplazada por precio_original_usd"),
    ("precio_unitario", "nunca se escribio ni se leyo"),
)


def upgrade() -> None:
    conexion = op.get_bind()
    op.execute("SELECT set_config('app.actor_tipo', 'migracion', true)")

    # Los pasos de saneamiento (renombres, alias declarados, borradores) reparan el
    # catalogo que trajo la migracion vieja del Excel. En una base virgen no hay nada
    # que reparar, y exigir que 'ACQUA DI GIO' exista ahi seria pedirle a una
    # instalacion nueva que traiga los datos de este negocio. Sobre la base real, en
    # cambio, un destino faltante tiene que fallar ruidoso: dejaria ventas sin resolver.
    catalogo_preexistente = (
        conexion.execute(sa.text("SELECT count(*) FROM productos")).scalar_one() > 0
    )

    # ---------------------------------------------------------------- 1. columnas
    op.add_column("productos", sa.Column("nombre_normalizado", sa.String(200)))
    op.add_column(
        "productos",
        sa.Column("es_original", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "productos",
        sa.Column(
            "modelo_precio",
            sa.Enum(name="modelo_precio", create_type=False),
            nullable=False,
            server_default="costo",
        ),
    )
    op.add_column("productos", sa.Column("linea", sa.String(80)))
    op.add_column("productos", sa.Column("costo_usd", sa.Numeric(14, 2)))
    op.add_column("productos", sa.Column("precio_original_usd", sa.Numeric(14, 2)))
    op.add_column(
        "productos",
        sa.Column("stock_minimo", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "productos",
        sa.Column(
            "estado",
            sa.Enum(name="estado_producto", create_type=False),
            nullable=False,
            server_default="activo",
        ),
    )
    op.add_column("productos", sa.Column("fusionado_en_producto_id", sa.Integer()))
    op.add_column(
        "productos",
        sa.Column("origen_alta", sa.String(24), nullable=False, server_default="catalogo"),
    )
    op.add_column("productos", sa.Column("creado_por_usuario_id", sa.Integer()))
    op.add_column("productos", sa.Column("revisado_at", sa.DateTime(timezone=True)))
    op.add_column("productos", sa.Column("revisado_por_usuario_id", sa.Integer()))
    op.add_column("productos", sa.Column("notas", sa.Text()))
    op.add_column(
        "productos",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.alter_column("productos", "categoria", type_=sa.String(80))
    op.alter_column("productos", "nombre", type_=sa.String(200), existing_nullable=False)

    # ------------------------------------------------------------- 2. renombrados
    # Nombres que son un artefacto de la migracion vieja, no una grafia alternativa.
    semilla = yaml.safe_load((DIR_SEEDS / "alias_productos.yaml").read_text(encoding="utf-8"))
    renombres = (semilla.get("renombrar", []) or []) if catalogo_preexistente else []
    for r in renombres:
        conexion.execute(
            sa.text("UPDATE productos SET nombre = :nuevo WHERE nombre = :viejo"),
            {"nuevo": r["a"], "viejo": r["de"]},
        )
    # El nombre viejo se registra abajo (paso 6 bis) como alias del renombrado. Sin
    # eso las ventas historicas que lo mencionan quedan sin resolver: `ventas.producto`
    # sigue diciendo '360.0' y la clave de '360' es otra.

    # -------------------------------------------------------------- 3. backfill
    # es_original desde la categoria que puso migrate_excel.py.
    conexion.execute(
        sa.text(
            "UPDATE productos SET es_original = (categoria = 'Original'), "
            "modelo_precio = CASE WHEN categoria = 'Original' THEN 'lista'::modelo_precio "
            "ELSE 'costo'::modelo_precio END"
        )
    )
    # El cambio que mas importa: 0 deja de significar 'no se'.
    conexion.execute(
        sa.text(
            "UPDATE productos SET costo_usd = NULLIF(costo, 0), "
            "precio_original_usd = NULLIF(precio_original, 0)"
        )
    )
    # Un producto de lista sin precio no puede quedar como 'lista': violaria el CHECK.
    conexion.execute(
        sa.text(
            "UPDATE productos SET modelo_precio = 'costo' "
            "WHERE modelo_precio = 'lista' AND precio_original_usd IS NULL"
        )
    )
    # Sin costo no hay precio calculable: es trabajo pendiente, no un producto listo.
    conexion.execute(
        sa.text(
            "UPDATE productos SET estado = 'borrador_por_revisar', "
            "notas = coalesce(notas || ' | ', '') || 'Sin costo cargado: el precio no se "
            "puede calcular. Cargalo para que salga de esta lista.' "
            "WHERE costo_usd IS NULL AND precio_original_usd IS NULL"
        )
    )

    # `clave_nombre()` en SQL, gemela de la funcion de Python, mas los triggers que
    # la aplican. Asi la invariante "nombre_normalizado corresponde a nombre" la
    # garantiza la base: Streamlit, la API y el ETL escriben en estas tablas, y
    # pedirle a los tres que se acuerden de llenar la columna es pedir que uno se
    # olvide. Es tambien lo que deja que `create_product` de Streamlit siga andando
    # sin tocarlo.
    op.execute(leer_sql("fn_clave_nombre"))
    op.execute(
        """
        CREATE TRIGGER trg_productos_normalizar
        BEFORE INSERT OR UPDATE OF nombre ON productos
        FOR EACH ROW EXECUTE FUNCTION fn_normalizar_nombre('nombre', 'nombre_normalizado');

        CREATE TRIGGER trg_clientes_normalizar
        BEFORE INSERT OR UPDATE OF nombre ON clientes
        FOR EACH ROW EXECUTE FUNCTION fn_normalizar_nombre('nombre', 'nombre_normalizado');

        CREATE TRIGGER trg_clientes_alias_normalizar
        BEFORE INSERT OR UPDATE OF alias ON clientes_alias
        FOR EACH ROW EXECUTE FUNCTION fn_normalizar_nombre('alias', 'alias_normalizado');

        CREATE TRIGGER trg_productos_alias_normalizar
        BEFORE INSERT OR UPDATE OF alias ON productos_alias
        FOR EACH ROW EXECUTE FUNCTION fn_normalizar_nombre('alias', 'alias_normalizado');

        -- El alias propio, para que un producto o cliente creado despues de esta
        -- revision sea encontrable. Sin esto, la venta que menciona un producto
        -- nuevo no lo resuelve y termina creando un duplicado.
        CREATE TRIGGER trg_productos_self_alias
        AFTER INSERT OR UPDATE OF nombre, estado ON productos
        FOR EACH ROW EXECUTE FUNCTION fn_producto_self_alias();

        CREATE TRIGGER trg_clientes_self_alias
        AFTER INSERT OR UPDATE OF nombre, estado ON clientes
        FOR EACH ROW EXECUTE FUNCTION fn_cliente_self_alias();
        """
    )

    # Backfill con la funcion de la base, no con la de Python: si las dos difieren
    # en algo, conviene que se note aca y no en produccion.
    conexion.execute(sa.text("UPDATE productos SET nombre_normalizado = clave_nombre(nombre)"))
    op.alter_column("productos", "nombre_normalizado", nullable=False)

    # ---------------------------------------------------------------- 4. dedupe
    grupos = conexion.execute(
        sa.text(
            "SELECT nombre_normalizado, es_original, array_agg(id ORDER BY "
            "(costo_usd IS NULL), (precio_original_usd IS NULL), id) AS ids "
            "FROM productos GROUP BY nombre_normalizado, es_original HAVING count(*) > 1"
        )
    ).all()

    fusionados = 0
    for clave, es_original, ids in grupos:
        sobreviviente, perdedores = ids[0], ids[1:]
        for perdedor in perdedores:
            nombre_perdedor = conexion.execute(
                sa.text("SELECT nombre FROM productos WHERE id = :i"), {"i": perdedor}
            ).scalar_one()
            conexion.execute(
                sa.text(
                    "INSERT INTO productos_alias "
                    "(producto_id, alias, alias_normalizado, es_original, origen) "
                    "VALUES (:p, :alias, :clave, :orig, 'dedupe_0004') "
                    "ON CONFLICT (alias_normalizado, es_original) DO NOTHING"
                ),
                {
                    "p": sobreviviente,
                    "alias": nombre_perdedor,
                    "clave": clave,
                    "orig": es_original,
                },
            )
            conexion.execute(
                sa.text(
                    "UPDATE productos SET estado = 'fusionado', "
                    "fusionado_en_producto_id = :s, "
                    "notas = coalesce(notas || ' | ', '') || 'Fusionado en el producto ' "
                    "|| :s || ' por la revision 0004 (nombre duplicado).' "
                    "WHERE id = :p"
                ),
                {"s": sobreviviente, "p": perdedor},
            )
            fusionados += 1

    # ----------------------------------------------------------- 5. self-alias
    # Cada sobreviviente se alias a si mismo, para que la resolucion por alias sea
    # el unico camino de busqueda y no haya que probar dos consultas.
    conexion.execute(
        sa.text(
            "INSERT INTO productos_alias "
            "(producto_id, alias, alias_normalizado, es_original, origen) "
            "SELECT id, nombre, nombre_normalizado, es_original, 'catalogo' "
            "FROM productos WHERE estado <> 'fusionado' "
            "ON CONFLICT (alias_normalizado, es_original) DO NOTHING"
        )
    )

    # ------------------------------------------------- 6. alias declarados a mano
    declarados = (semilla.get("confirmados", []) or []) if catalogo_preexistente else []
    for entrada in declarados:
        destino = conexion.execute(
            sa.text(
                "SELECT id, es_original FROM productos "
                "WHERE nombre = :n AND estado <> 'fusionado' LIMIT 1"
            ),
            {"n": entrada["destino"]},
        ).one_or_none()
        if destino is None:
            raise RuntimeError(
                f"El alias {entrada['alias']!r} apunta a {entrada['destino']!r}, que no "
                "existe en el catalogo. Corregí backend/seeds/alias_productos.yaml: "
                "un alias a un destino inexistente dejaria ventas sin resolver."
            )
        conexion.execute(
            sa.text(
                "INSERT INTO productos_alias "
                "(producto_id, alias, alias_normalizado, es_original, origen) "
                "VALUES (:p, :alias, :clave, :orig, 'declarado') "
                "ON CONFLICT (alias_normalizado, es_original) DO NOTHING"
            ),
            {
                "p": destino.id,
                "alias": entrada["alias"],
                "clave": clave_nombre(entrada["alias"]),
                "orig": destino.es_original,
            },
        )

    # ------------------------------- 6 bis. alias del nombre viejo de cada renombre
    for r in renombres:
        destino = conexion.execute(
            sa.text(
                "SELECT id, es_original FROM productos "
                "WHERE nombre = :n AND estado <> 'fusionado' LIMIT 1"
            ),
            {"n": r["a"]},
        ).one_or_none()
        if destino is None:
            continue
        conexion.execute(
            sa.text(
                "INSERT INTO productos_alias "
                "(producto_id, alias, alias_normalizado, es_original, origen) "
                "VALUES (:p, :alias, :clave, :orig, 'renombrado')"
                " ON CONFLICT (alias_normalizado, es_original) DO NOTHING"
            ),
            {
                "p": destino.id,
                "alias": r["de"],
                "clave": clave_nombre(r["de"]),
                "orig": destino.es_original,
            },
        )

    # -------------------------------- 7. lo que no tiene evidencia, entra a revision
    a_revisar = (semilla.get("a_revisar", []) or []) if catalogo_preexistente else []
    for entrada in a_revisar:
        nuevo = conexion.execute(
            sa.text(
                "INSERT INTO productos (nombre, nombre_normalizado, costo, precio_divisa, "
                "precio_bcv, stock, precio_unitario, precio_original, precio_team, "
                "precio_revendedor, estado, origen_alta, notas) "
                "VALUES (:n, :k, 0, 0, 0, 0, 0, 0, 0, 0, 'borrador_por_revisar', "
                "'import', :notas) "
                "ON CONFLICT DO NOTHING RETURNING id"
            ),
            {
                "n": entrada["nombre"],
                "k": clave_nombre(entrada["nombre"]),
                "notas": "Requiere revision: " + " ".join(entrada["motivo"].split()),
            },
        ).scalar_one_or_none()
        if nuevo is not None:
            conexion.execute(
                sa.text(
                    "INSERT INTO productos_alias "
                    "(producto_id, alias, alias_normalizado, es_original, origen) "
                    "VALUES (:p, :alias, :clave, FALSE, 'a_revisar') "
                    "ON CONFLICT (alias_normalizado, es_original) DO NOTHING"
                ),
                {
                    "p": nuevo,
                    "alias": entrada["nombre"],
                    "clave": clave_nombre(entrada["nombre"]),
                },
            )

    # ------------------------------------------------- 8. constraints e indices
    # El indice unico va al final: es la prueba de que el dedupe funciono.
    op.create_index(
        "uq_productos_nombre_es_original",
        "productos",
        ["nombre_normalizado", "es_original"],
        unique=True,
        postgresql_where=sa.text("estado <> 'fusionado'"),
    )
    op.create_index(
        "ix_productos_por_revisar",
        "productos",
        ["estado"],
        postgresql_where=sa.text("estado = 'borrador_por_revisar'"),
    )
    op.create_index(
        "ix_productos_nombre_trgm",
        "productos",
        ["nombre_normalizado"],
        postgresql_using="gin",
        postgresql_ops={"nombre_normalizado": "gin_trgm_ops"},
    )
    op.create_foreign_key(
        "fk_productos_fusionado_en_producto_id_productos",
        "productos",
        "productos",
        ["fusionado_en_producto_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_productos_creado_por_usuario_id_usuarios",
        "productos",
        "usuarios",
        ["creado_por_usuario_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_productos_revisado_por_usuario_id_usuarios",
        "productos",
        "usuarios",
        ["revisado_por_usuario_id"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_productos_fusionado_exige_destino",
        "productos",
        "estado <> 'fusionado' OR fusionado_en_producto_id IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_productos_modelo_lista_exige_precio",
        "productos",
        "modelo_precio <> 'lista' OR precio_original_usd IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_productos_costo_no_negativo", "productos", "costo_usd IS NULL OR costo_usd >= 0"
    )
    op.create_check_constraint(
        "ck_productos_stock_minimo_no_negativo", "productos", "stock_minimo >= 0"
    )

    def comentar(columna: str, texto: str) -> None:
        # Las comillas simples se duplican: un COMMENT es SQL literal y un apostrofo
        # en el texto rompe la sentencia.
        op.execute(
            f"COMMENT ON COLUMN productos.{columna} IS '{texto.replace(chr(39), chr(39) * 2)}'"
        )

    for columna, motivo in COLUMNAS_OBSOLETAS:
        comentar(
            columna,
            f"OBSOLETA ({motivo}). La lee solo Streamlit durante la convivencia; "
            "se suelta en el cutover.",
        )

    comentar(
        "costo_usd",
        'Costo en dolares. NULL = desconocido. Nunca 0 para decir "no se": eso es lo '
        "que hacia que la lista mostrara $0,00 como si fuera un precio.",
    )
    comentar(
        "nombre_normalizado",
        "clave_nombre(): minusculas, sin acentos y SIN espacios. Sin espacios porque "
        "la auditoria documenta 212 Vip / 212 vip / 212Vip como el mismo producto.",
    )


def downgrade() -> None:
    for nombre in (
        "ck_productos_stock_minimo_no_negativo",
        "ck_productos_costo_no_negativo",
        "ck_productos_modelo_lista_exige_precio",
        "ck_productos_fusionado_exige_destino",
    ):
        op.drop_constraint(nombre, "productos", type_="check")
    for nombre in (
        "fk_productos_revisado_por_usuario_id_usuarios",
        "fk_productos_creado_por_usuario_id_usuarios",
        "fk_productos_fusionado_en_producto_id_productos",
    ):
        op.drop_constraint(nombre, "productos", type_="foreignkey")
    for nombre in (
        "ix_productos_nombre_trgm",
        "ix_productos_por_revisar",
        "uq_productos_nombre_es_original",
    ):
        op.drop_index(nombre, table_name="productos")

    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_clientes_self_alias ON clientes;
        DROP TRIGGER IF EXISTS trg_productos_self_alias ON productos;
        DROP FUNCTION IF EXISTS fn_cliente_self_alias() CASCADE;
        DROP FUNCTION IF EXISTS fn_producto_self_alias() CASCADE;
        DROP TRIGGER IF EXISTS trg_productos_alias_normalizar ON productos_alias;
        DROP TRIGGER IF EXISTS trg_clientes_alias_normalizar ON clientes_alias;
        DROP TRIGGER IF EXISTS trg_clientes_normalizar ON clientes;
        DROP TRIGGER IF EXISTS trg_productos_normalizar ON productos;
        DROP FUNCTION IF EXISTS fn_normalizar_nombre() CASCADE;
        DROP FUNCTION IF EXISTS clave_nombre(text) CASCADE;
        """
    )
    op.execute("DELETE FROM productos_alias")
    op.execute("DELETE FROM productos WHERE origen_alta = 'import'")

    for columna in (
        "updated_at",
        "notas",
        "revisado_por_usuario_id",
        "revisado_at",
        "creado_por_usuario_id",
        "origen_alta",
        "fusionado_en_producto_id",
        "estado",
        "stock_minimo",
        "precio_original_usd",
        "costo_usd",
        "linea",
        "modelo_precio",
        "es_original",
        "nombre_normalizado",
    ):
        op.drop_column("productos", columna)

    op.execute("UPDATE productos SET nombre = '360.0' WHERE nombre = '360'")
