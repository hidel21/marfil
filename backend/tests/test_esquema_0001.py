"""Lo que la revisión 0001 tiene que garantizar.

No son tests de "la migración corrió": son tests de las garantías que el negocio
compró con ella. Si alguno se pone rojo, algo que se prometió dejó de ser verdad.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from tests.factories import (
    crear_cliente,
    crear_pago_legacy,
    crear_producto_legacy,
    crear_usuario,
    crear_venta_legacy,
)

pytestmark = pytest.mark.usefixtures("engine")


# --------------------------------------------------------------------- estructura
TABLAS_NUEVAS = (
    "usuarios",
    "refresh_tokens",
    "clientes",
    "clientes_alias",
    "productos_alias",
    "movimientos_stock",
    "venta_items",
    "cuotas",
    "parametros_precio",
    "configuracion",
    "tasas_cambio",
    "auditoria",
    "conciliaciones",
    "jobs_ejecuciones",
    "plantillas_mensaje",
    "plantillas_version",
    "recordatorios",
    "enlaces_importacion",
)


@pytest.mark.parametrize("tabla", TABLAS_NUEVAS)
def test_existen_las_tablas_nuevas(conn, tabla):
    assert conn.execute(
        text("SELECT to_regclass(:t) IS NOT NULL"), {"t": f"public.{tabla}"}
    ).scalar()


@pytest.mark.parametrize("ext", ["citext", "unaccent", "pg_trgm", "btree_gist", "pgcrypto"])
def test_extensiones_instaladas(conn, ext):
    assert (
        conn.execute(
            text("SELECT count(*) FROM pg_extension WHERE extname = :e"), {"e": ext}
        ).scalar()
        == 1
    )


def test_el_tercer_estado_de_cobro_existe():
    """El Excel usaba PENDIENTE (SIN ABONOS) y la app lo había perdido."""
    from app.models.enums import EstadoCobro

    assert EstadoCobro.PENDIENTE_SIN_ABONOS in set(EstadoCobro)


def test_los_enums_son_nativos_de_postgres(conn):
    """Nativos para que el vocabulario no pueda derivar. Antes había tres."""
    creados = set(
        conn.execute(
            text(
                "SELECT typname FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid "
                "GROUP BY typname"
            )
        ).scalars()
    )
    assert {"estado_cobro", "moneda", "rol_usuario", "origen_tasa", "canal_pago"} <= creados


def test_estado_cobro_tiene_los_cuatro_valores(conn):
    valores = (
        conn.execute(text("SELECT unnest(enum_range(NULL::estado_cobro))::text ORDER BY 1"))
        .scalars()
        .all()
    )
    assert sorted(valores) == ["anulada", "pagada", "pendiente_parcial", "pendiente_sin_abonos"]


def test_la_columna_no_ascii_desaparecio(conn):
    columnas = set(
        conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'filas_importadas'"
            )
        ).scalars()
    )
    assert "hoja" in columnas
    assert "pestaña" not in columnas


# ------------------------------------------------------------------- inmutabilidad
def test_no_se_puede_borrar_un_pago(conn):
    u = crear_usuario(conn)
    crear_cliente(conn)
    v = crear_venta_legacy(conn)
    p = crear_pago_legacy(conn, v)
    del u

    with pytest.raises(DBAPIError, match="append-only"):
        conn.execute(text("DELETE FROM pagos WHERE id = :i"), {"i": p})


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("monto_usd", "999"),
        ("monto_bs", "1"),
        ("tasa_bcv", "1"),
        ("fecha", "'2020-01-01'"),
        ("venta_id", "999999"),
    ],
)
def test_los_campos_del_libro_son_inmutables(conn, campo, valor):
    """Corregir un pago es registrar un reverso, no editar la historia."""
    crear_cliente(conn)
    v = crear_venta_legacy(conn)
    p = crear_pago_legacy(conn, v)

    with pytest.raises(DBAPIError, match="inmutable"):
        conn.execute(text(f"UPDATE pagos SET {campo} = {valor} WHERE id = :i"), {"i": p})


def test_la_referencia_si_se_puede_corregir(conn):
    """Un tipeo en la referencia bancaria no es reescribir la historia."""
    crear_cliente(conn)
    v = crear_venta_legacy(conn)
    p = crear_pago_legacy(conn, v)

    conn.execute(text("UPDATE pagos SET referencia = 'CORREGIDA' WHERE id = :i"), {"i": p})
    assert (
        conn.execute(text("SELECT referencia FROM pagos WHERE id = :i"), {"i": p}).scalar()
        == "CORREGIDA"
    )


# ----------------------------------------------------------------------- auditoría
def test_toda_escritura_queda_auditada(conn):
    p = crear_producto_legacy(conn, "Auditado")
    filas = conn.execute(
        text("SELECT accion, tabla FROM auditoria WHERE tabla = 'productos' AND registro_id = :i"),
        {"i": str(p)},
    ).all()
    assert ("INSERT", "productos") in filas


def test_un_update_registra_solo_lo_que_cambio(conn):
    p = crear_producto_legacy(conn, "Cambiante", stock=5)
    conn.execute(text("UPDATE productos SET stock = 9 WHERE id = :i"), {"i": p})

    cambiados = conn.execute(
        text(
            "SELECT campos_cambiados FROM auditoria "
            "WHERE tabla = 'productos' AND accion = 'UPDATE' AND registro_id = :i "
            "ORDER BY id DESC LIMIT 1"
        ),
        {"i": str(p)},
    ).scalar()
    assert cambiados == ["stock"]


def test_un_update_que_no_cambia_nada_no_deja_rastro(conn):
    """Ruido en el log de auditoría es peor que no tenerlo: se deja de leer."""
    p = crear_producto_legacy(conn, "Quieto", stock=5)
    antes = conn.execute(text("SELECT count(*) FROM auditoria")).scalar()

    conn.execute(text("UPDATE productos SET stock = 5 WHERE id = :i"), {"i": p})

    assert conn.execute(text("SELECT count(*) FROM auditoria")).scalar() == antes


def test_el_actor_sale_del_contexto_de_la_sesion(conn):
    u = crear_usuario(conn, "Hidelberg")
    conn.execute(text("SELECT set_config('app.usuario_id', :v, true)"), {"v": str(u)})

    p = crear_producto_legacy(conn, "Con autor")
    fila = conn.execute(
        text(
            "SELECT actor_tipo::text, usuario_id FROM auditoria "
            "WHERE tabla = 'productos' AND registro_id = :i"
        ),
        {"i": str(p)},
    ).one()
    assert fila == ("usuario", u)


def test_sin_contexto_el_actor_es_sistema(conn):
    p = crear_producto_legacy(conn, "Sin autor")
    fila = conn.execute(
        text(
            "SELECT actor_tipo::text, usuario_id FROM auditoria "
            "WHERE tabla = 'productos' AND registro_id = :i"
        ),
        {"i": str(p)},
    ).one()
    assert fila == ("sistema", None)


# ------------------------------------------------------------------- unicidad
def test_un_cliente_no_puede_repetir_nombre_normalizado(conn):
    crear_cliente(conn, "Anderson")
    with pytest.raises(IntegrityError):
        crear_cliente(conn, "  ANDERSON  ")


def test_un_cliente_fusionado_libera_su_nombre(conn):
    """Sin esto no se podría fusionar y volver a usar el nombre canónico."""
    a = crear_cliente(conn, "Ricardo")
    b = crear_cliente(conn, "Ricardo Palacios")
    conn.execute(
        text(
            "UPDATE clientes SET estado = 'fusionado', fusionado_en_cliente_id = :b WHERE id = :a"
        ),
        {"a": a, "b": b},
    )
    crear_cliente(conn, "Ricardo")  # no debe explotar


def test_el_alias_de_producto_distingue_original_de_top_quality(conn):
    """'bharara king' existe en las dos listas: son SKUs distintos."""
    tq = crear_producto_legacy(conn, "Bharara King TQ")
    orig = crear_producto_legacy(conn, "Bharara King Original")
    insertar = text(
        "INSERT INTO productos_alias (producto_id, alias, alias_normalizado, es_original, origen) "
        "VALUES (:p, 'Bharara King', 'bhararaking', :o, 'test')"
    )
    conn.execute(insertar, {"p": tq, "o": False})
    conn.execute(insertar, {"p": orig, "o": True})  # mismo alias, otra lista: permitido

    with pytest.raises(IntegrityError):
        conn.execute(insertar, {"p": tq, "o": False})


# ------------------------------------------------------------------- stock
def test_el_stock_es_la_suma_de_sus_movimientos(conn):
    p = crear_producto_legacy(conn, "Con movimientos", stock=0)
    for tipo, cantidad in (("carga_inicial", 10), ("venta", -3), ("ajuste", -1)):
        conn.execute(
            text(
                "INSERT INTO movimientos_stock (producto_id, tipo, cantidad, saldo_despues) "
                "VALUES (:p, :t, :c, 0)"
            ),
            {"p": p, "t": tipo, "c": cantidad},
        )
    assert conn.execute(text("SELECT stock FROM productos WHERE id = :p"), {"p": p}).scalar() == 6


def test_un_movimiento_de_cero_no_tiene_sentido(conn):
    p = crear_producto_legacy(conn, "Cero")
    with pytest.raises(IntegrityError):
        conn.execute(
            text(
                "INSERT INTO movimientos_stock (producto_id, tipo, cantidad, saldo_despues) "
                "VALUES (:p, 'ajuste', 0, 0)"
            ),
            {"p": p},
        )


# ------------------------------------------------------- parámetros y recordatorios
def test_dos_vigencias_del_mismo_parametro_no_pueden_solaparse(conn):
    # Clave propia del test: las de negocio ya vienen sembradas por 0002.
    insertar = text(
        "INSERT INTO parametros_precio (clave, valor, vigencia) "
        "VALUES ('PARAMETRO_DE_PRUEBA', :v, daterange(:d, NULL))"
    )
    conn.execute(insertar, {"v": "1.2", "d": "2026-06-01"})
    with pytest.raises(IntegrityError):
        conn.execute(insertar, {"v": "1.3", "d": "2026-07-01"})


def test_un_parametro_puede_versionarse_sin_solapar(conn):
    """Cambiar la ganancia deja de ser irreversible: queda el historial."""
    conn.execute(
        text(
            "INSERT INTO parametros_precio (clave, valor, vigencia) "
            "VALUES ('PARAMETRO_DE_PRUEBA', 1.2, daterange('2026-06-01','2026-09-01'))"
        )
    )
    conn.execute(
        text(
            "INSERT INTO parametros_precio (clave, valor, vigencia) "
            "VALUES ('PARAMETRO_DE_PRUEBA', 1.3, daterange('2026-09-01', NULL))"
        )
    )
    vigente = conn.execute(
        text(
            "SELECT valor FROM parametros_precio "
            "WHERE clave = 'PARAMETRO_DE_PRUEBA' AND vigencia @> DATE '2026-07-15'"
        )
    ).scalar()
    assert float(vigente) == 1.2


def test_nadie_recibe_dos_recordatorios_el_mismo_dia(conn):
    """La red anti-spam es un índice único, no lógica de aplicación."""
    c = crear_cliente(conn, "Moroso", telefono="+584121234567")
    v = crear_venta_legacy(conn)
    # La plantilla ya viene sembrada por la revision 0002.
    insertar = text(
        "INSERT INTO recordatorios (cliente_id, venta_id, plantilla_clave, plantilla_version, "
        "cuerpo_renderizado, saldo_usd_al_generar) "
        "VALUES (:c, :v, 'recordatorio_vencido', 1, 'Hola Moroso', 22.00)"
    )
    conn.execute(insertar, {"c": c, "v": v})
    with pytest.raises(IntegrityError):
        conn.execute(insertar, {"c": c, "v": v})
