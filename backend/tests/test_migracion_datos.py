"""Lo que las revisiones 0002, 0003 y 0004 tienen que dejar cierto.

Corren contra la base de test, que se construye desde cero con las migraciones. Como
ahi no hay ventas historicas, lo que se prueba son las **reglas**, no los conteos de
produccion: los conteos van en scripts/verificar_migracion.sql, que se corre contra
la base real.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.normalizacion import clave_nombre

pytestmark = pytest.mark.usefixtures("engine")


# ------------------------------------------------------------------- 0002 semilla
def test_se_siembra_un_solo_usuario_el_superadmin(conn):
    """Los otros dos socios existen para el reparto, pero sin cuenta.

    Sembrar tres cuentas obligaba a inventar dos direcciones de correo y dejaba dos
    perfiles que nadie reclama. Los crea el superadmin, con las direcciones reales.
    """
    filas = conn.execute(
        text(
            "SELECT u.nombre, u.email, s.id IS NOT NULL AS ligado "
            "FROM usuarios u LEFT JOIN socios s ON s.usuario_id = u.id ORDER BY u.nombre"
        )
    ).all()
    assert [f.nombre for f in filas] == ["Hidelberg"]
    assert filas[0].email == "hm@intelli-next.com"
    assert filas[0].ligado, "queda ligado a su fila de reparto de utilidad"


def test_los_socios_sin_cuenta_quedan_listados(conn):
    """Es la lista de trabajo del superadmin: a quién le falta el perfil."""
    pendientes = conn.execute(
        text("SELECT nombre FROM socios WHERE usuario_id IS NULL ORDER BY nombre")
    ).scalars().all()
    assert pendientes == ["Gregor", "Gregory"]


def test_el_superadmin_tampoco_puede_entrar_sin_fijar_su_clave(conn):
    """Sembrar una contraseña conocida sería peor que no sembrar ninguna."""
    bloqueados = conn.execute(
        text("SELECT count(*) FROM usuarios WHERE password_hash = '!bloqueado'")
    ).scalar()
    assert bloqueados == 1


def test_la_politica_de_precios_es_la_del_libro(conn):
    """+70 % divisa y +120 % BCV, medidos sobre el COSTO. Confirmado por el dueño."""
    valores = dict(
        conn.execute(
            text(
                "SELECT clave, valor FROM parametros_precio "
                "WHERE vigencia @> CURRENT_DATE AND clave LIKE 'GANANCIA%' OR "
                "clave LIKE 'DESC%' AND vigencia @> CURRENT_DATE"
            )
        ).all()
    )
    assert valores["GANANCIA_DIVISA"] == Decimal("0.700000")
    assert valores["GANANCIA_BCV"] == Decimal("1.200000")
    assert valores["DESC_TEAM"] == Decimal("0.250000")
    assert valores["DESC_REVENDEDOR"] == Decimal("0.150000")


def test_un_costo_de_12_da_2040_y_2640(conn):
    """El caso real de Cloud. Si esto cambia, cambió la política, no el código."""
    divisa, bcv = conn.execute(
        text(
            "SELECT round(12 * (1 + (SELECT valor FROM parametros_precio "
            "  WHERE clave='GANANCIA_DIVISA' AND vigencia @> CURRENT_DATE)), 2), "
            "       round(12 * (1 + (SELECT valor FROM parametros_precio "
            "  WHERE clave='GANANCIA_BCV' AND vigencia @> CURRENT_DATE)), 2)"
        )
    ).one()
    assert (divisa, bcv) == (Decimal("20.40"), Decimal("26.40"))


def test_los_datos_de_pago_se_siembran_incompletos(conn):
    """A propósito: mientras falten, generar un recordatorio tiene que fallar."""
    datos = conn.execute(
        text("SELECT valor FROM configuracion WHERE clave = 'datos_pago'")
    ).scalar()
    assert set(datos) >= {"banco", "documento", "telefono"}
    assert not any(datos[k] for k in ("banco", "documento", "telefono"))


def test_ninguna_plantilla_lleva_datos_de_pago_escritos(conn):
    """Es el bug que se estaba enviando a clientes reales: 'C.I.: V-XX.XXX.XXX'."""
    con_placeholder = conn.execute(
        text("SELECT count(*) FROM plantillas_mensaje WHERE cuerpo ~ 'X{2,}|04XX|V-XX'")
    ).scalar()
    assert con_placeholder == 0

    usan_variable = conn.execute(
        text("SELECT count(*) FROM plantillas_mensaje WHERE cuerpo LIKE '%datos_pago%'")
    ).scalar()
    assert usan_variable >= 4, "las plantillas de cobranza insertan los datos por variable"


# ------------------------------------------------------------------ 0004 funciones
NOMBRES_REALES = [
    "ACQUA DI GIO",
    "AQUA DI GIO",
    "212 vip",
    "212Vip",
    "Khamrah qahwa",
    "ASAD ZANZÍBAR",
    "Armaf, club de nuit iconic",
    "360.0",
    "9PM REBEL ORIGINAL",
    "Ángel",
    "  espacios   raros  ",
]


@pytest.mark.parametrize("nombre", NOMBRES_REALES)
def test_clave_nombre_da_lo_mismo_en_sql_y_en_python(conn, nombre):
    """Las dos definiciones tienen que coincidir: una la usa el trigger, la otra la app.

    Si divergen, un producto creado por la API y otro por el ETL pueden terminar
    siendo dos filas del mismo perfume.
    """
    en_sql = conn.execute(text("SELECT clave_nombre(:n)"), {"n": nombre}).scalar()
    assert en_sql == clave_nombre(nombre)


def test_el_trigger_llena_la_clave_sin_que_nadie_se_acuerde(conn):
    """Es lo que deja que `create_product` de Streamlit siga andando sin tocarlo."""
    pid = conn.execute(
        text(
            "INSERT INTO productos (nombre, costo, precio_divisa, precio_bcv, stock, "
            "precio_unitario, precio_original, precio_team, precio_revendedor) "
            "VALUES ('Perfume Ñandú Ácido', 0,0,0,0,0,0,0,0) RETURNING id"
        )
    ).scalar_one()
    assert conn.execute(
        text("SELECT nombre_normalizado FROM productos WHERE id = :i"), {"i": pid}
    ).scalar() == "perfumenanduacido"


def test_la_clave_sigue_al_nombre_cuando_se_corrige(conn):
    pid = conn.execute(
        text(
            "INSERT INTO productos (nombre, costo, precio_divisa, precio_bcv, stock, "
            "precio_unitario, precio_original, precio_team, precio_revendedor) "
            "VALUES ('Nombre Viejo', 0,0,0,0,0,0,0,0) RETURNING id"
        )
    ).scalar_one()
    conn.execute(
        text("UPDATE productos SET nombre = 'Nombre Nuevo' WHERE id = :i"), {"i": pid}
    )
    assert conn.execute(
        text("SELECT nombre_normalizado FROM productos WHERE id = :i"), {"i": pid}
    ).scalar() == "nombrenuevo"


# -------------------------------------------------------------------- 0004 reglas
def test_dos_productos_no_pueden_compartir_clave_en_la_misma_lista(conn):
    crear = text(
        "INSERT INTO productos (nombre, es_original, costo, precio_divisa, precio_bcv, "
        "stock, precio_unitario, precio_original, precio_team, precio_revendedor) "
        "VALUES (:n, :o, 0,0,0,0,0,0,0,0)"
    )
    conn.execute(crear, {"n": "Repetido Uno", "o": False})
    with pytest.raises(IntegrityError):
        conn.execute(crear, {"n": "REPETIDO  UNO", "o": False})


def test_el_mismo_nombre_si_puede_estar_en_las_dos_listas(conn):
    """'bharara king' está en Top Quality y en Originales: son SKUs distintos."""
    crear = text(
        "INSERT INTO productos (nombre, es_original, modelo_precio, precio_original_usd, "
        "costo, precio_divisa, precio_bcv, stock, precio_unitario, precio_original, "
        "precio_team, precio_revendedor) "
        "VALUES (:n, :o, :m, :p, 0,0,0,0,0,0,0,0)"
    )
    conn.execute(crear, {"n": "Doble Lista", "o": False, "m": "costo", "p": None})
    conn.execute(crear, {"n": "Doble Lista", "o": True, "m": "lista", "p": 50})


def test_costo_desconocido_es_null_y_no_cero(conn):
    """0-como-desconocido es lo que hacía que la lista mostrara $0,00 como precio."""
    con_cero = conn.execute(
        text("SELECT count(*) FROM productos WHERE costo_usd = 0")
    ).scalar()
    assert con_cero == 0, "ningún producto debería tener costo_usd = 0: o hay costo, o es NULL"


def test_un_producto_de_lista_sin_precio_no_puede_ser_de_lista(conn):
    with pytest.raises(IntegrityError):
        conn.execute(
            text(
                "INSERT INTO productos (nombre, modelo_precio, precio_original_usd, costo, "
                "precio_divisa, precio_bcv, stock, precio_unitario, precio_original, "
                "precio_team, precio_revendedor) "
                "VALUES ('Lista Sin Precio', 'lista', NULL, 0,0,0,0,0,0,0,0)"
            )
        )


def test_un_producto_fusionado_exige_destino(conn):
    pid = conn.execute(
        text(
            "INSERT INTO productos (nombre, costo, precio_divisa, precio_bcv, stock, "
            "precio_unitario, precio_original, precio_team, precio_revendedor) "
            "VALUES ('Para Fusionar', 0,0,0,0,0,0,0,0) RETURNING id"
        )
    ).scalar_one()
    with pytest.raises(IntegrityError):
        conn.execute(
            text("UPDATE productos SET estado = 'fusionado' WHERE id = :i"), {"i": pid}
        )


# ------------------------------------------------------------------ 0003 clientes
def test_el_cliente_recibe_su_alias_propio_solo(conn):
    """Sin el alias propio, un cliente creado hoy no se encuentra por nombre."""
    cid = conn.execute(
        text("INSERT INTO clientes (nombre) VALUES ('  JUAN  Herrade ') RETURNING id")
    ).scalar_one()
    fila = conn.execute(
        text(
            "SELECT c.nombre_normalizado, a.alias, a.alias_normalizado, a.origen "
            "FROM clientes c JOIN clientes_alias a ON a.cliente_id = c.id WHERE c.id = :c"
        ),
        {"c": cid},
    ).one()
    assert fila.nombre_normalizado == "juanherrade"
    assert fila.alias_normalizado == "juanherrade"
    assert fila.origen == "catalogo"


def test_un_alias_extra_tambien_se_normaliza(conn):
    cid = conn.execute(
        text("INSERT INTO clientes (nombre) VALUES ('Cristhian') RETURNING id")
    ).scalar_one()
    conn.execute(
        text(
            "INSERT INTO clientes_alias (cliente_id, alias, origen) "
            "VALUES (:c, '  Cristihan  ', 'test')"
        ),
        {"c": cid},
    )
    assert conn.execute(
        text(
            "SELECT alias_normalizado FROM clientes_alias "
            "WHERE cliente_id = :c AND origen = 'test'"
        ),
        {"c": cid},
    ).scalar() == "cristihan"


def test_un_alias_no_puede_apuntar_a_dos_clientes(conn):
    a = conn.execute(text("INSERT INTO clientes (nombre) VALUES ('Uno') RETURNING id")).scalar_one()
    b = conn.execute(text("INSERT INTO clientes (nombre) VALUES ('Dos') RETURNING id")).scalar_one()
    insertar = text(
        "INSERT INTO clientes_alias (cliente_id, alias, origen) VALUES (:c, 'Ambiguo', 'test')"
    )
    conn.execute(insertar, {"c": a})
    with pytest.raises(IntegrityError):
        conn.execute(insertar, {"c": b})
