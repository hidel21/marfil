"""normalizar ventas y pagos: el modelo canonico y el libro

Ventas y pagos van en **una sola revision** a proposito. El saldo se calcula desde
el libro, asi que con la mitad del cambio aplicada no puede estar bien: separarlas
daria un estado intermedio inconsistente y un rollback de la mitad tampoco dejaria
nada usable.

Que hace:

 1. Columnas nuevas en `ventas` y `pagos` (todas nulables primero).
 2. **Corrige las 8 fechas mal tecleadas** (`2026-02-08` -> `2026-08-02`, ids 23-30),
    cada una con su evento de auditoria y actor 'migracion'. Es un cambio de dato, y
    queda firmado.
 3. Resuelve `cliente_id` por alias y `vendedor_usuario_id` por nombre; asigna
    `codigo` legible.
 4. Crea una `venta_items` por venta desde las columnas planas, con
    `descripcion_libre` textual (`ASAD BORBOM`, `Victorinox swis army` se conservan
    tal como se tecleo).
 5. Traduce `pagos` a la forma del libro. **Los 2 pagos con tasa_bcv = 1.00 pasan a
    moneda USD**, tasa 1 y canal efectivo_usd: dejan de contaminar el total en
    bolivares con 28 Bs que nunca fueron bolivares.
 6. **Marca las 29 tasas restantes como `sintetizada_migracion` con confianza baja.**
    `migrate_excel.py` las despejaba de una heuristica de tercios
    (`tasa = monto_bs / monto_usd`, con `monto_usd` derivado de la deuda), no de una
    tasa registrada. Se prueba solo con los datos: la venta 9 tiene 1.088,44 el
    11/07 y el 02/08 —la misma tasa a tres semanas de distancia— mientras otros
    pagos de esos dias rondan 690. No se corrigen aca: eso es la revision 0007,
    aparte y reversible, porque mueve dinero.
 7. Crea una cuota implicita por venta, para que la consulta de antiguedad tenga un
    solo camino de codigo con plan y sin plan.
 8. Congela `saldo_congelado_migracion = deuda` **antes** de que los triggers
    recalculen, y despues verifica que el saldo calculado coincida. Es la prueba de
    que la migracion no movio ninguna cifra.
 9. Cuelga los triggers canonicos y la capa de compatibilidad con Streamlit.

**Las columnas legacy no se sueltan.** `cliente`, `producto`, `deuda`, `estatus`,
`precio_venta`, `costo`, `ganancia`, `total`, `monto_bs`, `tasa_bcv`, `nro_cuota`
quedan como espejo de solo lectura que mantienen los triggers, y Streamlit las sigue
leyendo. Se sueltan en el cutover.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-22

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.db.sql import leer_sql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Las 8 filas que la auditoria (§5.1) marco como dd/mm invertido: estan encajonadas
#: entre el 30/07 y el 02/08 y son el bloque mas reciente del libro.
FECHA_ERRONEA = "2026-02-08"
FECHA_CORREGIDA = "2026-08-02"

COLUMNAS_LEGACY_VENTAS = (
    "cliente", "vendedor", "producto", "cantidad", "precio_venta", "costo",
    "ganancia", "moneda", "deuda", "estatus", "total",
)
COLUMNAS_LEGACY_PAGOS = ("cliente", "producto", "monto_bs", "tasa_bcv", "nro_cuota")


def upgrade() -> None:
    conexion = op.get_bind()
    op.execute("SELECT set_config('app.actor_tipo', 'migracion', true)")

    op.execute("CREATE SEQUENCE IF NOT EXISTS ventas_codigo_seq")

    # ------------------------------------------------------- 1. columnas en ventas
    for columna in (
        sa.Column("codigo", sa.String(20)),
        sa.Column("cliente_id", sa.Integer()),
        sa.Column("vendedor_usuario_id", sa.Integer()),
        sa.Column("moneda_cotizacion", sa.Enum(name="moneda", create_type=False)),
        sa.Column(
            "nivel_precio_aplicado",
            sa.Enum(name="nivel_precio", create_type=False),
            nullable=False,
            server_default="publico",
        ),
        sa.Column("total_usd", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("costo_usd", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("saldo_usd", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column(
            "estado_cobro",
            sa.Enum(name="estado_cobro", create_type=False),
            nullable=False,
            server_default="pendiente_sin_abonos",
        ),
        sa.Column("plazo_dias", sa.SmallInteger()),
        sa.Column("fecha_vencimiento", sa.Date()),
        sa.Column("tiene_plan_cuotas", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("notas", sa.Text()),
        sa.Column("anulada_at", sa.DateTime(timezone=True)),
        sa.Column("anulada_por_usuario_id", sa.Integer()),
        sa.Column("motivo_anulacion", sa.Text()),
        sa.Column("saldo_congelado_migracion", sa.Numeric(14, 2)),
        sa.Column("creado_por_usuario_id", sa.Integer()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    ):
        op.add_column("ventas", columna)

    # -------------------------------------------------------- 2. columnas en pagos
    for columna in (
        sa.Column("cuota_id", sa.Integer()),
        sa.Column("tipo", sa.Enum(name="tipo_movimiento_pago", create_type=False)),
        sa.Column("moneda", sa.Enum(name="moneda", create_type=False)),
        sa.Column("monto_moneda", sa.Numeric(18, 2)),
        sa.Column("tasa_aplicada", sa.Numeric(18, 8)),
        sa.Column("tasa_id", sa.Integer()),
        sa.Column("origen_tasa", sa.Enum(name="origen_tasa", create_type=False)),
        sa.Column(
            "confianza_tasa",
            sa.Enum(name="confianza_dato", create_type=False),
            nullable=False,
            server_default="alta",
        ),
        sa.Column("canal", sa.Enum(name="canal_pago", create_type=False)),
        sa.Column("nro_bloque", sa.SmallInteger()),
        sa.Column("anula_pago_id", sa.Integer()),
        sa.Column("motivo", sa.Text()),
        sa.Column("registrado_por_usuario_id", sa.Integer()),
        sa.Column("comprobante_url", sa.Text()),
        sa.Column("notas", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    ):
        op.add_column("pagos", columna)

    op.alter_column("pagos", "referencia", type_=sa.String(64), nullable=True)
    op.alter_column("ventas", "fecha", nullable=False)
    # `tasa_bcv` era NUMERIC(10,2) y truncaba la tasa a dos decimales: 779,9522 se
    # guardaba como 779,95. El BCV publica 4+ decimales, y esta es la columna en la
    # que Streamlit sigue escribiendo, asi que se ensancha para que la traduccion al
    # libro no herede la perdida.
    op.alter_column("pagos", "tasa_bcv", type_=sa.Numeric(18, 8), existing_nullable=False)
    # Las columnas legacy de `pagos` pasan a nulables: son un espejo que llena un
    # trigger, no un dato que el escritor tenga que traer. `cliente` era NOT NULL y
    # hacia fallar cualquier pago que no viniera de Streamlit.
    op.alter_column("pagos", "cliente", existing_type=sa.String(200), nullable=True)
    op.alter_column("pagos", "tasa_bcv", existing_type=sa.Numeric(18, 8), nullable=True)
    op.alter_column("pagos", "monto_bs", existing_type=sa.Numeric(10, 2), nullable=True)
    op.alter_column("pagos", "nro_cuota", existing_type=sa.Integer(), nullable=True)

    hay_datos = conexion.execute(sa.text("SELECT count(*) FROM ventas")).scalar_one() > 0

    # ---------------------------------------------- 3. las 8 fechas mal tecleadas
    if hay_datos:
        afectadas = conexion.execute(
            sa.text("SELECT id FROM ventas WHERE fecha = :mala"), {"mala": FECHA_ERRONEA}
        ).scalars().all()
        if afectadas:
            conexion.execute(
                sa.text("UPDATE ventas SET fecha = :buena WHERE fecha = :mala"),
                {"buena": FECHA_CORREGIDA, "mala": FECHA_ERRONEA},
            )
            # El trigger de auditoria ya registro el UPDATE; esto le agrega el motivo,
            # que es lo que alimenta el filtro "solo excepciones".
            conexion.execute(
                sa.text(
                    "UPDATE auditoria SET motivo = :motivo "
                    "WHERE tabla = 'ventas' AND accion = 'UPDATE' "
                    "AND registro_id = ANY(:ids) AND campos_cambiados = ARRAY['fecha'] "
                    "AND motivo IS NULL"
                ),
                {
                    "motivo": (
                        f"Correccion de fecha {FECHA_ERRONEA} -> {FECHA_CORREGIDA}: "
                        "dd/mm teclado como mm/dd (auditoria.md §5.1). Autorizado por "
                        "el dueno."
                    ),
                    "ids": [str(i) for i in afectadas],
                },
            )

    # ------------------------------------------------- 4. cliente, vendedor, codigo
    if hay_datos:
        conexion.execute(
            sa.text(
                "UPDATE ventas v SET cliente_id = a.cliente_id "
                "FROM clientes_alias a "
                "WHERE a.alias_normalizado = clave_nombre(v.cliente) "
                "AND v.cliente_id IS NULL"
            )
        )
        conexion.execute(
            sa.text(
                "UPDATE ventas v SET vendedor_usuario_id = u.id FROM usuarios u "
                "WHERE clave_nombre(u.nombre) = clave_nombre(COALESCE(v.vendedor, '')) "
                "AND v.vendedor_usuario_id IS NULL"
            )
        )
        # Un vendedor que no coincide no puede dejar la venta sin registrar.
        conexion.execute(
            sa.text(
                "UPDATE ventas SET vendedor_usuario_id = "
                "(SELECT id FROM usuarios WHERE rol = 'admin' ORDER BY id LIMIT 1), "
                "notas = coalesce(notas || ' | ', '') || 'Vendedor sin usuario: ' "
                "|| coalesce(vendedor, '(vacio)') || '. Revisar la atribucion.' "
                "WHERE vendedor_usuario_id IS NULL"
            )
        )
        conexion.execute(
            sa.text(
                "UPDATE ventas SET "
                "codigo = 'V-' || to_char(fecha, 'YYYY') || '-' || lpad(id::text, 4, '0'), "
                "moneda_cotizacion = CASE "
                "  WHEN upper(COALESCE(moneda, 'BCV')) IN ('USD','DIVISA') THEN 'USD'::moneda "
                "  WHEN upper(COALESCE(moneda, 'BCV')) = 'USDT' THEN 'USDT'::moneda "
                "  ELSE 'VES'::moneda END, "
                "plazo_dias = COALESCE((SELECT valor::integer FROM parametros_precio "
                "  WHERE clave = 'PLAZO_CREDITO_DIAS' AND vigencia @> ventas.fecha LIMIT 1), 15) "
                "WHERE codigo IS NULL"
            )
        )
        conexion.execute(
            sa.text(
                "UPDATE ventas SET fecha_vencimiento = fecha + plazo_dias "
                "WHERE fecha_vencimiento IS NULL"
            )
        )
        # El testigo de fidelidad, antes de que ningun trigger toque nada.
        conexion.execute(
            sa.text("UPDATE ventas SET saldo_congelado_migracion = deuda")
        )

    # ------------------------------------------------------ 5. constraints en ventas
    op.alter_column("ventas", "codigo", nullable=False)
    op.alter_column("ventas", "cliente_id", nullable=False)
    op.alter_column("ventas", "vendedor_usuario_id", nullable=False)
    op.alter_column("ventas", "moneda_cotizacion", nullable=False)
    op.alter_column("ventas", "plazo_dias", nullable=False)
    op.alter_column("ventas", "fecha_vencimiento", nullable=False)
    op.create_unique_constraint("uq_ventas_codigo", "ventas", ["codigo"])
    op.create_foreign_key(
        "fk_ventas_cliente_id_clientes", "ventas", "clientes", ["cliente_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_ventas_vendedor_usuario_id_usuarios",
        "ventas",
        "usuarios",
        ["vendedor_usuario_id"],
        ["id"],
    )
    for nombre, columna in (
        ("fk_ventas_anulada_por_usuario_id_usuarios", "anulada_por_usuario_id"),
        ("fk_ventas_creado_por_usuario_id_usuarios", "creado_por_usuario_id"),
    ):
        op.create_foreign_key(nombre, "ventas", "usuarios", [columna], ["id"])
    op.create_index("ix_ventas_cliente_fecha", "ventas", ["cliente_id", "fecha"])
    op.create_index("ix_ventas_fecha", "ventas", ["fecha"])
    op.create_index("ix_ventas_vendedor_fecha", "ventas", ["vendedor_usuario_id", "fecha"])
    op.create_index(
        "ix_ventas_por_cobrar",
        "ventas",
        ["fecha_vencimiento", "cliente_id"],
        postgresql_where=sa.text("saldo_usd > 0"),
    )

    # ------------------------------------------- 6. las lineas, desde lo que hay
    # `resolver_producto()` centraliza el desempate: un mismo nombre puede tener dos
    # alias (Top Quality y Original) y una venta historica no dice de cual salio.
    op.execute(leer_sql("fn_resolver_producto"))

    if hay_datos:
        conexion.execute(
            sa.text(
                "INSERT INTO venta_items (venta_id, linea, producto_id, descripcion_libre, "
                "cantidad, precio_unitario_usd, costo_unitario_usd) "
                "SELECT v.id, 1, resolver_producto(v.producto), v.producto, "
                "  GREATEST(1, COALESCE(v.cantidad, 1)), "
                "  round(COALESCE(v.precio_venta, 0) / GREATEST(1, COALESCE(v.cantidad, 1)), 2), "
                "  round(COALESCE(v.costo, 0) / GREATEST(1, COALESCE(v.cantidad, 1)), 2) "
                "FROM ventas v "
                "WHERE v.producto IS NOT NULL "
                "AND resolver_producto(v.producto) IS NOT NULL "
                "AND NOT EXISTS (SELECT 1 FROM venta_items i WHERE i.venta_id = v.id)"
            )
        )
        # Si algo no resuelve, la migracion para: una venta sin linea tendria total 0
        # y el saldo quedaria mal. Es mejor fallar aca que dejar cifras rotas.
        sin_linea = conexion.execute(
            sa.text(
                "SELECT count(*) FROM ventas v WHERE v.producto IS NOT NULL "
                "AND NOT EXISTS (SELECT 1 FROM venta_items i WHERE i.venta_id = v.id)"
            )
        ).scalar_one()
        if sin_linea:
            faltantes = conexion.execute(
                sa.text(
                    "SELECT DISTINCT v.producto FROM ventas v WHERE v.producto IS NOT NULL "
                    "AND NOT EXISTS (SELECT 1 FROM venta_items i WHERE i.venta_id = v.id)"
                )
            ).scalars().all()
            raise RuntimeError(
                f"{sin_linea} venta(s) sin linea porque su producto no resuelve: "
                f"{faltantes}. Agregá el alias en backend/seeds/alias_productos.yaml."
            )
        # El precio de politica al momento, para que la desviacion sea calculable.
        # NULL donde el costo era desconocido: sin costo no hay politica que comparar.
        conexion.execute(
            sa.text(
                "UPDATE venta_items i SET precio_lista_usd = round("
                "  p.costo_usd * (1 + (SELECT valor FROM parametros_precio "
                "    WHERE clave = CASE WHEN v.moneda_cotizacion = 'VES' "
                "      THEN 'GANANCIA_BCV' ELSE 'GANANCIA_DIVISA' END "
                "    AND vigencia @> v.fecha LIMIT 1)), 2) "
                "FROM ventas v, productos p "
                "WHERE i.venta_id = v.id AND i.producto_id = p.id "
                "AND p.costo_usd IS NOT NULL"
            )
        )
        # Las 2 ventas por debajo del costo quedan como estan, por decision del dueno,
        # pero con motivo escrito para que el guardia de precio no las marque para
        # siempre como una excepcion sin explicar.
        conexion.execute(
            sa.text(
                "UPDATE venta_items SET motivo_desviacion = "
                "'Dato historico anterior al sistema (auditoria.md §5.2). El dueno "
                "decidio conservarlo tal cual.' "
                "WHERE precio_unitario_usd < costo_unitario_usd"
            )
        )

    # ------------------------------------------------ 7. el libro, desde monto_bs
    #
    # `trg_pagos_inmutable` se desactiva para esta traduccion y se vuelve a activar
    # enseguida. No es una excepcion comoda: el trigger esta haciendo exactamente su
    # trabajo al bloquear un UPDATE sobre monto y tasa, y esta es la unica escritura
    # legitima de ese tipo en la vida de la tabla —traducir la forma vieja a la del
    # libro—. `monto_usd`, que es la cifra de dinero, NO se toca: solo se completa la
    # forma (monto_bs -> monto_moneda, tasa_bcv -> tasa_aplicada).
    if hay_datos:
        op.execute("ALTER TABLE pagos DISABLE TRIGGER trg_pagos_inmutable")
        conexion.execute(
            sa.text(
                "UPDATE pagos SET tipo = 'abono', nro_bloque = nro_cuota, "
                # tasa <= 1 no es una tasa: es un pago en dolares metido a la fuerza.
                "moneda = CASE WHEN COALESCE(tasa_bcv, 0) <= 1 THEN 'USD'::moneda "
                "              ELSE 'VES'::moneda END, "
                "monto_moneda = CASE WHEN COALESCE(tasa_bcv, 0) <= 1 THEN monto_usd "
                "                    ELSE monto_bs END, "
                "tasa_aplicada = CASE WHEN COALESCE(tasa_bcv, 0) <= 1 THEN 1 "
                "                     ELSE tasa_bcv END, "
                "canal = CASE WHEN COALESCE(tasa_bcv, 0) <= 1 THEN 'efectivo_usd'::canal_pago "
                "             ELSE 'pago_movil'::canal_pago END, "
                # La codificacion honesta del hallazgo: estas tasas se despejaron de
                # una heuristica, no se registraron.
                "origen_tasa = CASE WHEN COALESCE(tasa_bcv, 0) <= 1 THEN 'manual'::origen_tasa "
                "                   ELSE 'sintetizada_migracion'::origen_tasa END, "
                "confianza_tasa = CASE WHEN COALESCE(tasa_bcv, 0) <= 1 "
                "  THEN 'media'::confianza_dato ELSE 'baja'::confianza_dato END, "
                "notas = CASE WHEN COALESCE(tasa_bcv, 0) <= 1 "
                "  THEN 'Efectivo en dolares. En el libro estaba como monto en Bs con "
                "tasa 1,00 (auditoria.md §5.6).' "
                "  ELSE 'Tasa deducida por migrate_excel.py como monto_bs/monto_usd, con "
                "monto_usd derivado de la deuda. No es una tasa registrada.' END, "
                "referencia = NULLIF(NULLIF(btrim(referencia), ''), 'SIN REFERENCIA') "
                "WHERE moneda IS NULL"
            )
        )
        op.execute("ALTER TABLE pagos ENABLE TRIGGER trg_pagos_inmutable")

        # Y se comprueba que la traduccion no movio dinero.
        movidos = conexion.execute(
            sa.text(
                "SELECT count(*) FROM pagos WHERE abs("
                "  CASE WHEN moneda = 'USD' THEN monto_moneda "
                "       ELSE round(monto_moneda / NULLIF(tasa_aplicada, 0), 2) END "
                "  - monto_usd) > 0.01"
            )
        ).scalar_one()
        if movidos:
            raise RuntimeError(
                f"{movidos} pago(s) donde monto_moneda/tasa no reproduce monto_usd. "
                "La traduccion de la forma no debe cambiar ninguna cifra."
            )

    op.alter_column("pagos", "tipo", nullable=False, server_default="abono")
    op.alter_column("pagos", "moneda", nullable=False)
    op.alter_column("pagos", "monto_moneda", nullable=False)
    op.alter_column("pagos", "tasa_aplicada", nullable=False)
    op.alter_column("pagos", "origen_tasa", nullable=False)
    op.alter_column("pagos", "canal", nullable=False)

    op.create_check_constraint(
        "ck_pagos_signo_segun_tipo",
        "pagos",
        "(tipo = 'reverso' AND monto_usd < 0) OR (tipo <> 'reverso' AND monto_usd > 0)",
    )
    op.create_check_constraint(
        "ck_pagos_tasa_coherente_con_moneda",
        "pagos",
        "(moneda = 'USD' AND tasa_aplicada = 1) OR (moneda <> 'USD' AND tasa_aplicada > 1)",
    )
    op.create_check_constraint(
        "ck_pagos_reverso_apunta_a_pago",
        "pagos",
        "tipo <> 'reverso' OR anula_pago_id IS NOT NULL",
    )
    op.create_foreign_key("fk_pagos_cuota_id_cuotas", "pagos", "cuotas", ["cuota_id"], ["id"])
    op.create_foreign_key(
        "fk_pagos_tasa_id_tasas_cambio", "pagos", "tasas_cambio", ["tasa_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_pagos_anula_pago_id_pagos", "pagos", "pagos", ["anula_pago_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_pagos_registrado_por_usuario_id_usuarios",
        "pagos",
        "usuarios",
        ["registrado_por_usuario_id"],
        ["id"],
    )
    op.create_index(
        "uq_pagos_referencia",
        "pagos",
        ["referencia", "monto_moneda", "fecha"],
        unique=True,
        postgresql_where=sa.text("referencia IS NOT NULL AND tipo = 'abono'"),
    )
    op.create_index("ix_pagos_venta_fecha", "pagos", ["venta_id", "fecha"])
    op.create_index("ix_pagos_fecha", "pagos", ["fecha"])
    op.create_index("ix_pagos_cuota", "pagos", ["cuota_id"])

    # ---------------------------------------------------- 8. triggers canonicos
    op.execute(
        """
        CREATE TRIGGER trg_venta_items_totales
        AFTER INSERT OR UPDATE OR DELETE ON venta_items
        FOR EACH ROW EXECUTE FUNCTION fn_recalcular_totales_venta();

        CREATE TRIGGER trg_pagos_saldo
        AFTER INSERT OR UPDATE ON pagos
        FOR EACH ROW EXECUTE FUNCTION fn_pagos_actualizan_saldo();

        CREATE TRIGGER trg_cuotas_vencimiento
        AFTER INSERT OR UPDATE OR DELETE ON cuotas
        FOR EACH ROW EXECUTE FUNCTION fn_actualizar_vencimiento_venta();
        """
    )

    # -------------------------------------- 9. recalcular todo con los triggers puestos
    if hay_datos:
        conexion.execute(
            sa.text(
                "UPDATE ventas v SET total_usd = COALESCE(i.total, 0), "
                "costo_usd = COALESCE(i.costo, 0) FROM ("
                "  SELECT venta_id, SUM(subtotal_usd) total, "
                "         SUM(cantidad * costo_unitario_usd) costo "
                "  FROM venta_items GROUP BY venta_id) i "
                "WHERE i.venta_id = v.id"
            )
        )
        conexion.execute(
            sa.text("SELECT fn_recalcular_saldo_venta(id) FROM ventas")
        )

        # La cuota implicita del plazo por defecto: un solo camino de codigo para la
        # antiguedad, con plan y sin plan.
        conexion.execute(
            sa.text(
                "INSERT INTO cuotas (venta_id, numero, fecha_vencimiento, monto_usd, implicita) "
                "SELECT id, 1, fecha_vencimiento, total_usd, TRUE FROM ventas "
                "WHERE total_usd > 0 "
                "AND NOT EXISTS (SELECT 1 FROM cuotas c WHERE c.venta_id = ventas.id)"
            )
        )
        conexion.execute(
            sa.text(
                "UPDATE cuotas c SET monto_abonado_usd = LEAST(c.monto_usd, GREATEST(0, "
                "  COALESCE((SELECT SUM(monto_usd) FROM pagos WHERE venta_id = c.venta_id), 0)))"
            )
        )
        conexion.execute(
            sa.text(
                "UPDATE pagos p SET cuota_id = c.id FROM cuotas c "
                "WHERE c.venta_id = p.venta_id AND p.cuota_id IS NULL"
            )
        )

        # ------------------------------------- La prueba: el saldo no se movio.
        descuadres = conexion.execute(
            sa.text(
                "SELECT count(*) FROM ventas "
                "WHERE abs(COALESCE(saldo_usd, 0) - COALESCE(saldo_congelado_migracion, 0)) > 0.005"
            )
        ).scalar_one()
        if descuadres:
            detalle = conexion.execute(
                sa.text(
                    "SELECT id, codigo, saldo_congelado_migracion, saldo_usd FROM ventas "
                    "WHERE abs(COALESCE(saldo_usd,0) - COALESCE(saldo_congelado_migracion,0)) "
                    "> 0.005 ORDER BY id LIMIT 10"
                )
            ).all()
            raise RuntimeError(
                f"El saldo calculado no coincide con el de la app vieja en {descuadres} "
                f"venta(s). La migracion no debe mover dinero. Primeras: {detalle}"
            )

    # ------------------------------------------ 10. constraints de saldo y cuotas
    op.create_check_constraint("ck_ventas_saldo_no_negativo", "ventas", "saldo_usd >= 0")
    op.create_check_constraint(
        "ck_ventas_saldo_no_supera_total", "ventas", "saldo_usd <= total_usd"
    )
    op.create_check_constraint(
        "ck_ventas_vencimiento_no_anterior_a_venta", "ventas", "fecha_vencimiento >= fecha"
    )
    op.create_check_constraint("ck_ventas_plazo_no_negativo", "ventas", "plazo_dias >= 0")

    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_cuotas_suman_total() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            v_venta_id integer := COALESCE(NEW.venta_id, OLD.venta_id);
            v_total    numeric(14,2);
            v_cuotas   numeric(14,2);
        BEGIN
            SELECT total_usd INTO v_total FROM ventas WHERE id = v_venta_id;
            IF NOT FOUND THEN RETURN NULL; END IF;

            SELECT COALESCE(SUM(monto_usd), 0) INTO v_cuotas
              FROM cuotas WHERE venta_id = v_venta_id;

            IF v_cuotas > 0 AND abs(v_cuotas - v_total) > 0.005 THEN
                RAISE EXCEPTION
                    'Las cuotas de la venta % suman % y la venta es de %. Corregí el plan.',
                    v_venta_id, v_cuotas, v_total
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NULL;
        END;
        $$;

        CREATE CONSTRAINT TRIGGER trg_cuotas_suman_total
        AFTER INSERT OR UPDATE OR DELETE ON cuotas
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION fn_cuotas_suman_total();
        """
    )

    # --------------------------------- 11. capa de compatibilidad con Streamlit
    op.execute(leer_sql("compat_streamlit"))
    op.execute(
        """
        CREATE TRIGGER trg_compat_ventas_completar
        BEFORE INSERT ON ventas
        FOR EACH ROW EXECUTE FUNCTION fn_compat_ventas_completar();

        CREATE TRIGGER trg_compat_ventas_linea
        AFTER INSERT ON ventas
        FOR EACH ROW EXECUTE FUNCTION fn_compat_ventas_linea();

        CREATE TRIGGER trg_compat_espejo_saldo
        AFTER UPDATE OF saldo_usd, total_usd, estado_cobro ON ventas
        FOR EACH ROW EXECUTE FUNCTION fn_compat_espejo_saldo();

        CREATE TRIGGER trg_compat_pagos_completar
        BEFORE INSERT ON pagos
        FOR EACH ROW EXECUTE FUNCTION fn_compat_pagos_completar();
        """
    )

    for columna in COLUMNAS_LEGACY_VENTAS:
        op.execute(
            f"COMMENT ON COLUMN ventas.{columna} IS "
            "'OBSOLETA. Espejo de solo lectura que mantienen los triggers de "
            "compatibilidad para que Streamlit siga leyendo durante la convivencia. "
            "Se suelta en el cutover.'"
        )
    for columna in COLUMNAS_LEGACY_PAGOS:
        op.execute(
            f"COMMENT ON COLUMN pagos.{columna} IS "
            "'OBSOLETA. La escribe Streamlit; los triggers la traducen a la forma del "
            "libro. Se suelta en el cutover.'"
        )
    op.execute(
        "COMMENT ON COLUMN ventas.saldo_congelado_migracion IS "
        "'La deuda que traia la app vieja, congelada antes de que los triggers "
        "recalcularan. Es el testigo de que la migracion no movio ninguna cifra. Se "
        "suelta cuando un socio firme las cifras reconciliadas.'"
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_pagos_espejo_legacy ON pagos;
        DROP FUNCTION IF EXISTS fn_pagos_espejo_legacy() CASCADE;
        DROP FUNCTION IF EXISTS fn_escribe_la_api() CASCADE;
        DROP TRIGGER IF EXISTS trg_compat_pagos_completar ON pagos;
        DROP TRIGGER IF EXISTS trg_compat_espejo_saldo ON ventas;
        DROP TRIGGER IF EXISTS trg_compat_ventas_linea ON ventas;
        DROP TRIGGER IF EXISTS trg_compat_ventas_completar ON ventas;
        DROP FUNCTION IF EXISTS fn_compat_pagos_completar() CASCADE;
        DROP FUNCTION IF EXISTS fn_compat_espejo_saldo() CASCADE;
        DROP FUNCTION IF EXISTS fn_compat_ventas_linea() CASCADE;
        DROP FUNCTION IF EXISTS fn_compat_ventas_completar() CASCADE;
        DROP TRIGGER IF EXISTS trg_cuotas_suman_total ON cuotas;
        DROP FUNCTION IF EXISTS fn_cuotas_suman_total() CASCADE;
        DROP TRIGGER IF EXISTS trg_cuotas_vencimiento ON cuotas;
        DROP TRIGGER IF EXISTS trg_pagos_saldo ON pagos;
        DROP TRIGGER IF EXISTS trg_venta_items_totales ON venta_items;
        """
    )
    # Las columnas de `pagos` se sueltan ANTES de borrar las cuotas: `pagos.cuota_id`
    # las referencia, y un DELETE con la FK puesta falla.
    for nombre in (
        "ck_pagos_reverso_apunta_a_pago",
        "ck_pagos_tasa_coherente_con_moneda",
        "ck_pagos_signo_segun_tipo",
    ):
        op.drop_constraint(nombre, "pagos", type_="check")
    for indice in (
        "ix_pagos_cuota", "ix_pagos_fecha", "ix_pagos_venta_fecha", "uq_pagos_referencia",
    ):
        op.drop_index(indice, table_name="pagos")
    for columna in (
        "created_at", "notas", "comprobante_url", "registrado_por_usuario_id", "motivo",
        "anula_pago_id", "nro_bloque", "canal", "confianza_tasa", "origen_tasa",
        "tasa_id", "tasa_aplicada", "monto_moneda", "moneda", "tipo", "cuota_id",
    ):
        op.drop_column("pagos", columna)
    op.alter_column("pagos", "tasa_bcv", type_=sa.Numeric(10, 2), existing_nullable=False)

    op.execute("DELETE FROM cuotas")
    op.execute("DELETE FROM venta_items")

    for nombre in (
        "ck_ventas_plazo_no_negativo",
        "ck_ventas_vencimiento_no_anterior_a_venta",
        "ck_ventas_saldo_no_supera_total",
        "ck_ventas_saldo_no_negativo",
    ):
        op.drop_constraint(nombre, "ventas", type_="check")
    for indice in (
        "ix_ventas_por_cobrar",
        "ix_ventas_vendedor_fecha",
        "ix_ventas_fecha",
        "ix_ventas_cliente_fecha",
    ):
        op.drop_index(indice, table_name="ventas")

    for columna in (
        "updated_at", "created_at", "creado_por_usuario_id", "saldo_congelado_migracion",
        "motivo_anulacion", "anulada_por_usuario_id", "anulada_at", "notas",
        "tiene_plan_cuotas", "fecha_vencimiento", "plazo_dias", "estado_cobro",
        "saldo_usd", "costo_usd", "total_usd", "nivel_precio_aplicado",
        "moneda_cotizacion", "vendedor_usuario_id", "cliente_id", "codigo",
    ):
        op.drop_column("ventas", columna)

    op.execute("DROP SEQUENCE IF EXISTS ventas_codigo_seq")

    # Las 8 fechas corregidas NO se revierten. Dos razones:
    # - es una correccion de dato autorizada por el dueno, no un cambio de esquema;
    # - revertirla por fecha alcanzaria tambien a las 2 ventas que si son del
    #   02/08/2026, y un downgrade que corrompe datos es peor que no tener downgrade.
    # Queda registrada en `auditoria` con su motivo, que es donde corresponde.
