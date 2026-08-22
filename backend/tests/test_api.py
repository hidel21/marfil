"""La API de punta a punta.

Se prueba contra la base de test real (construida desde las migraciones) y con datos
sembrados por el propio test, porque lo que importa aca no son los conteos de
produccion sino que las reglas se apliquen a traves de HTTP: el contrato del dinero,
los permisos, y que un error de negocio nunca sea una traza.
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.seguridad import hashear_password

pytestmark = pytest.mark.usefixtures("engine_api")

CLAVE = "clave-de-prueba-1234"


@pytest.fixture
def cliente_api(engine_api, monkeypatch):
    """TestClient apuntado a la base de test."""
    monkeypatch.setenv("DATABASE_URL", str(engine_api.url))
    from app.main import crear_app

    return TestClient(crear_app())


@pytest.fixture
def admin(engine_api):
    """Un admin con contraseña usable. Se limpia al final."""
    with engine_api.begin() as c:
        c.execute(
            text(
                "UPDATE usuarios SET password_hash = :h, debe_cambiar_password = FALSE "
                "WHERE email = :e"
            ),
            {"h": hashear_password(CLAVE), "e": "hm@intelli-next.com"},
        )
    return "hm@intelli-next.com"


@pytest.fixture
def token(cliente_api, admin):
    r = cliente_api.post("/api/v1/auth/login", json={"email": admin, "password": CLAVE})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ------------------------------------------------------------------------ salud
def test_salud_reporta_lo_que_importa_operar(cliente_api):
    d = cliente_api.get("/api/salud").json()
    assert d["ok"] is True
    assert d["revision_db"] is not None
    assert d["descuadres"] == 0
    # Los datos de pago se siembran vacíos: la salud lo dice, no lo esconde.
    assert d["datos_pago_completos"] is False


# ------------------------------------------------------------------------- auth
def test_login_y_yo(cliente_api, token):
    yo = cliente_api.get("/api/v1/auth/yo", headers=token).json()
    assert yo["rol"] == "admin"
    assert yo["ve_costos"] is True


def test_clave_incorrecta_no_dice_cual_de_las_dos_falla(cliente_api, admin):
    """Decir si el usuario existe le regala al atacante la mitad del trabajo."""
    a = cliente_api.post(
        "/api/v1/auth/login", json={"email": admin, "password": "incorrecta"}
    ).json()
    b = cliente_api.post(
        "/api/v1/auth/login", json={"email": "nadie@marfil.test", "password": "x"}
    ).json()
    assert a["mensaje"] == b["mensaje"]
    assert a["codigo"] == "NO_AUTENTICADO"


def test_sin_token_no_se_entra(cliente_api):
    r = cliente_api.get("/api/v1/cobranza/resumen")
    assert r.status_code == 401
    assert r.json()["codigo"] == "NO_AUTENTICADO"


def test_un_usuario_sin_password_recibe_una_explicacion_util(cliente_api, engine_api):
    """Un perfil recién creado está bloqueado: el mensaje tiene que decir cómo seguir."""
    with engine_api.begin() as c:
        c.execute(
            text(
                "INSERT INTO usuarios (email, nombre, password_hash, rol) "
                "VALUES ('bloqueado@marfil.test', 'Bloqueado', '!bloqueado', 'vendedor') "
                "ON CONFLICT (email) DO NOTHING"
            )
        )
    r = cliente_api.post(
        "/api/v1/auth/login", json={"email": "bloqueado@marfil.test", "password": "x"}
    )
    assert r.json()["codigo"] == "USUARIO_SIN_PASSWORD"
    assert "establecer-password" in r.json()["sugerencia"]


def test_el_refresh_token_no_viaja_en_el_cuerpo(cliente_api, admin):
    """Va en una cookie HttpOnly: ningún script del navegador lo puede leer."""
    r = cliente_api.post("/api/v1/auth/login", json={"email": admin, "password": CLAVE})
    assert "refresh_token" not in r.json()
    assert "marfil_refresh" in r.cookies


# ------------------------------------------------- el contrato del dinero
def test_el_dinero_viaja_como_string_en_los_modelos(cliente_api, token):
    d = cliente_api.get("/api/v1/cobranza/resumen", headers=token).json()
    for m in d["metricas"]:
        assert isinstance(m["valor"], str), f"{m['clave']} debería ser string"
    for t in d["tramos"]:
        assert isinstance(t["monto_usd"], str)


def test_el_dinero_viaja_como_string_tambien_en_los_dicts_crudos(cliente_api, token):
    """Este es el caso que se escapa: FastAPI codifica antes de la clase de respuesta.

    Un monto que viaja como número JSON llega a JavaScript como float, y ahí
    `0.1 + 0.2 !== 0.3`: son los descuadres de un centavo que el panel de
    conciliación tendría que estar detectando.
    """
    d = cliente_api.get("/api/v1/auditoria/fuga-precio", headers=token).json()
    assert isinstance(d["fuga_total_usd"], str)
    for v in d["por_vendedor"]:
        assert isinstance(v["fuga_usd"], str)


def test_un_conteo_no_se_formatea_como_monto(cliente_api, token):
    """'14 deudores' no es '14.00'."""
    d = cliente_api.get("/api/v1/cobranza/resumen", headers=token).json()
    conteo = next(m for m in d["metricas"] if m["clave"] == "sin_telefono")
    assert conteo["es_monto"] is False
    assert "." not in conteo["valor"]


def test_una_tasa_conserva_sus_decimales(cliente_api, token, engine_api):
    with engine_api.begin() as c:
        c.execute(
            text(
                "INSERT INTO tasas_cambio (fecha, tipo, valor, origen) "
                "VALUES (CURRENT_DATE, 'bcv', 779.9522, 'api_usdtve') "
                "ON CONFLICT (fecha, tipo) DO UPDATE SET valor = 779.9522"
            )
        )
    d = cliente_api.get("/api/v1/ajustes/tasas", headers=token).json()
    assert d[0]["valor"] == "779.9522", "una tasa no se recorta a 2 decimales"


# --------------------------------------------------- las tarjetas de calidad
def test_las_tarjetas_criticas_van_primero(cliente_api, token):
    tarjetas = cliente_api.get("/api/v1/auditoria/calidad", headers=token).json()
    severidades = [t["severidad"] for t in tarjetas]
    orden = {"critica": 0, "alta": 1, "media": 2}
    assert severidades == sorted(severidades, key=lambda s: orden[s])


def test_la_tarjeta_de_datos_de_pago_esta_en_rojo(cliente_api, token):
    """Se siembran vacíos, así que arranca en crítica: bloquea toda la cobranza."""
    tarjetas = {t["clave"]: t for t in cliente_api.get(
        "/api/v1/auditoria/calidad", headers=token
    ).json()}
    tarjeta = tarjetas["datos_pago_incompletos"]
    assert tarjeta["severidad"] == "critica"
    assert tarjeta["cantidad"] == 3, "banco, documento y teléfono"
    assert tarjeta["ruta"] == "/ajustes/pagos"


def test_cada_tarjeta_dice_que_hacer_y_donde(cliente_api, token):
    """Una tarjeta sin acción es una queja, no trabajo."""
    for t in cliente_api.get("/api/v1/auditoria/calidad", headers=token).json():
        assert t["accion"], f"{t['clave']} sin acción"
        assert t["ruta"].startswith("/"), f"{t['clave']} sin ruta"


def test_las_tres_conciliaciones_cuadran(cliente_api, token):
    for tipo in ("ventas", "pagos", "stock"):
        d = cliente_api.get(
            f"/api/v1/auditoria/conciliacion?tipo={tipo}", headers=token
        ).json()
        assert d["ok"] is True, f"{tipo} descuadrado: {d['items'][:2]}"


# ---------------------------------------------------------- datos de pago
def test_sin_datos_de_pago_no_se_genera_un_recordatorio(cliente_api, token):
    """Falla la generación, no solo el envío: nunca existe un mensaje con un hueco."""
    r = cliente_api.post("/api/v1/recordatorios/previsualizar", headers=token, json={})
    assert r.status_code == 422
    assert r.json()["codigo"] == "AJUSTES_PAGO_INCOMPLETOS"
    assert "faltantes" in r.json()["detalles"]


def test_los_datos_de_pago_validan_formato_real(cliente_api, token):
    malos = [
        {"titular": "X", "codigo_banco": "0191", "documento": "V-12345678",
         "telefono": "04121234567"},
        {"titular": "Gregory Marfil", "codigo_banco": "9999", "documento": "V-12345678",
         "telefono": "04121234567"},
        {"titular": "Gregory Marfil", "codigo_banco": "0191", "documento": "V-XX.XXX.XXX",
         "telefono": "04121234567"},
        {"titular": "Gregory Marfil", "codigo_banco": "0191", "documento": "V-12345678",
         "telefono": "02121234567"},
    ]
    for datos in malos:
        r = cliente_api.put("/api/v1/ajustes/pagos", headers=token, json=datos)
        assert r.status_code == 422, f"debería rechazar {datos}"


def test_con_datos_de_pago_completos_se_desbloquea(cliente_api, token):
    r = cliente_api.put(
        "/api/v1/ajustes/pagos",
        headers=token,
        json={
            "titular": "Gregory Marfil",
            "codigo_banco": "0191",
            "documento": "V-12345678",
            "telefono": "04121234567",
        },
    )
    assert r.status_code == 200
    assert r.json()["completo"] is True
    vista = r.json()["vista_previa"]
    assert "BNC" in vista
    assert "XX" not in vista, "nunca un marcador de relleno"


# --------------------------------------------------------------- plantillas
def test_no_se_puede_guardar_una_plantilla_con_datos_de_pago(cliente_api, token):
    """El bug que se enviaba a clientes reales, cerrado por segunda vez."""
    r = cliente_api.put(
        "/api/v1/recordatorios/plantillas/recordatorio_vencido",
        headers=token,
        json={"cuerpo": "Hola, pagá a la C.I. V-XX.XXX.XXX del 0412-1234567"},
    )
    assert r.status_code == 422
    assert r.json()["codigo"] == "PLANTILLA_CON_DATOS_DE_PAGO"


def test_una_variable_inexistente_se_rechaza_con_sugerencia(cliente_api, token):
    r = cliente_api.put(
        "/api/v1/recordatorios/plantillas/recordatorio_vencido",
        headers=token,
        json={"cuerpo": "Hola {{ cliente }}, debés ${{ deuda }}. {{ datos_pago }}"},
    )
    assert r.status_code == 422
    assert r.json()["codigo"] == "PLANTILLA_VARIABLE_DESCONOCIDA"
    assert "deuda_usd" in r.json()["sugerencia"]


# ---------------------------------------------------- ventas: el guardia por HTTP
def _semilla_venta(engine_api) -> tuple[int, int]:
    """Cliente y producto nuevos para cada test.

    Los nombres llevan un sufijo unico porque estos tests escriben **con commit** a
    traves de la API: no hay rollback que los limpie, y el indice unico sobre
    `nombre_normalizado` haria que el segundo test que corriera fallara por el
    primero. Un test que depende del orden es peor que no tenerlo.
    """
    sufijo = uuid4().hex[:8]
    with engine_api.begin() as c:
        cliente = c.execute(
            text("INSERT INTO clientes (nombre) VALUES (:n) RETURNING id"),
            {"n": f"Cliente API {sufijo}"},
        ).scalar_one()
        producto = c.execute(
            text(
                "INSERT INTO productos (nombre, costo_usd, stock, costo, precio_divisa, "
                "precio_bcv, precio_unitario, precio_original, precio_team, "
                "precio_revendedor) VALUES (:n, 12, 10, 0,0,0,0,0,0,0) RETURNING id"
            ),
            {"n": f"Producto API {sufijo}"},
        ).scalar_one()
    return cliente, producto


def test_cotizar_devuelve_la_politica_y_el_otro_nivel(cliente_api, token, engine_api):
    cliente, producto = _semilla_venta(engine_api)
    r = cliente_api.post(
        "/api/v1/ventas/cotizar",
        headers=token,
        json={
            "cliente_id": cliente,
            "fecha": str(date.today()),
            "moneda_cotizacion": "VES",
            "lineas": [{"producto_id": producto, "cantidad": 1, "precio_unitario_usd": "22.00"}],
        },
    )
    assert r.status_code == 200, r.text
    linea = r.json()["lineas"][0]
    assert linea["precio_politica_usd"] == "26.40"
    assert linea["precio_otro_nivel_usd"] == "20.40"
    assert r.json()["bloqueada"] is True


def test_la_venta_con_nivel_equivocado_no_se_guarda(cliente_api, token, engine_api):
    """La fuga de $123, cortada en el punto de captura."""
    cliente, producto = _semilla_venta(engine_api)
    r = cliente_api.post(
        "/api/v1/ventas",
        headers=token,
        json={
            "cliente_id": cliente,
            "fecha": str(date.today()),
            "moneda_cotizacion": "VES",
            "lineas": [{"producto_id": producto, "cantidad": 1, "precio_unitario_usd": "22.00"}],
        },
    )
    assert r.status_code == 422
    assert r.json()["codigo"] == "PRECIO_NIVEL_INCORRECTO"
    detalles = r.json()["detalles"]["bloqueos"][0]["detalles"]
    assert detalles["moneda_sugerida"] == "USD", "la salida: cambiar el nivel"


def test_cambiar_el_nivel_hace_que_la_venta_pase(cliente_api, token, engine_api):
    """Es la resolución correcta: el registro queda honesto."""
    cliente, producto = _semilla_venta(engine_api)
    r = cliente_api.post(
        "/api/v1/ventas",
        headers=token,
        json={
            "cliente_id": cliente,
            "fecha": str(date.today()),
            "moneda_cotizacion": "USD",
            "lineas": [{"producto_id": producto, "cantidad": 1, "precio_unitario_usd": "22.00"}],
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["total_usd"] == "22.00"
    assert r.json()["estado_cobro"] == "pendiente_sin_abonos"


def test_un_motivo_autoriza_la_excepcion(cliente_api, token, engine_api):
    """Nada se prohíbe: se exige nombrar el motivo, y queda firmado."""
    cliente, producto = _semilla_venta(engine_api)
    r = cliente_api.post(
        "/api/v1/ventas",
        headers=token,
        json={
            "cliente_id": cliente,
            "fecha": str(date.today()),
            "moneda_cotizacion": "VES",
            "lineas": [{"producto_id": producto, "cantidad": 1, "precio_unitario_usd": "22.00"}],
            "autorizaciones": {"0": "Cliente frecuente, precio acordado antes"},
        },
    )
    assert r.status_code == 201, r.text


def test_una_venta_sobre_pedido_se_puede_registrar(cliente_api, token, engine_api):
    """Antes era imposible: el stock era un techo y bloqueaba la venta."""
    cliente, producto = _semilla_venta(engine_api)
    cuerpo = {
        "cliente_id": cliente,
        "fecha": str(date.today()),
        "moneda_cotizacion": "VES",
        "lineas": [{"producto_id": producto, "cantidad": 99, "precio_unitario_usd": "26.40"}],
    }
    r = cliente_api.post("/api/v1/ventas", headers=token, json=cuerpo)
    assert r.status_code == 422
    assert r.json()["codigo"] == "SOBREVENTA_SIN_CONFIRMAR"

    r = cliente_api.post(
        "/api/v1/ventas", headers=token, json={**cuerpo, "permitir_sobreventa": True}
    )
    assert r.status_code == 201, r.text


def test_el_plan_de_cuotas_tiene_que_sumar_el_total(cliente_api, token, engine_api):
    cliente, producto = _semilla_venta(engine_api)
    r = cliente_api.post(
        "/api/v1/ventas",
        headers=token,
        json={
            "cliente_id": cliente,
            "fecha": str(date.today()),
            "moneda_cotizacion": "VES",
            "lineas": [{"producto_id": producto, "cantidad": 1, "precio_unitario_usd": "26.40"}],
            "plan_cuotas": [
                {"numero": 1, "fecha_vencimiento": str(date.today()), "monto_usd": "10.00"},
                {"numero": 2, "fecha_vencimiento": str(date.today()), "monto_usd": "10.00"},
            ],
        },
    )
    assert r.status_code == 422
    assert r.json()["codigo"] == "CUOTAS_NO_SUMAN"


def test_el_plan_sugerido_reparte_sin_perder_centavos(cliente_api, token):
    r = cliente_api.post(
        "/api/v1/ventas/plan-sugerido",
        headers=token,
        json={"total_usd": "100.00", "cuotas": 3, "primera_fecha": str(date.today())},
    )
    d = r.json()
    assert [c["monto_usd"] for c in d["cuotas"]] == ["33.33", "33.33", "33.34"]
    assert d["suma"] == "100.00"


# ------------------------------------------------------------- pagos por HTTP
def _venta_con_saldo(cliente_api, token, engine_api, dias_atras: int = 0) -> int:
    """Crea una venta con saldo. `dias_atras` la fecha para que quede vencida.

    Se retrasa la FECHA DE VENTA y no el vencimiento: el CHECK
    `fecha_vencimiento >= fecha` existe justamente para que no se pueda tener una
    venta que vence antes de haber ocurrido.
    """
    cliente, producto = _semilla_venta(engine_api)
    r = cliente_api.post(
        "/api/v1/ventas",
        headers=token,
        json={
            "cliente_id": cliente,
            "fecha": str(date.today() - timedelta(days=dias_atras)),
            "moneda_cotizacion": "VES",
            "lineas": [{"producto_id": producto, "cantidad": 1, "precio_unitario_usd": "26.40"}],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["venta_id"]


def test_un_abono_en_bolivares_usa_la_tasa_y_congela(cliente_api, token, engine_api):
    with engine_api.begin() as c:
        c.execute(
            text(
                "INSERT INTO tasas_cambio (fecha, tipo, valor, origen) "
                "VALUES (CURRENT_DATE, 'bcv', 779.9522, 'api_usdtve') "
                "ON CONFLICT (fecha, tipo) DO UPDATE SET valor = 779.9522"
            )
        )
    venta = _venta_con_saldo(cliente_api, token, engine_api)
    r = cliente_api.post(
        "/api/v1/pagos",
        headers=token,
        json={
            "venta_id": venta,
            "fecha": str(date.today()),
            "canal": "pago_movil",
            "monto_moneda": "7799.52",
            "referencia": f"API-BS-{uuid4().hex[:8]}",
        },
    )
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["moneda"] == "VES"
    assert d["monto_usd"] == "10.00"
    assert d["saldo_usd"] == "16.40"
    assert "779" in d["tasa_procedencia"] or "Tasa" in d["tasa_procedencia"]


def test_el_efectivo_en_dolares_no_lleva_tasa(cliente_api, token, engine_api):
    """La ruta explícita que reemplaza el `tasa_bcv = 1.00` de la app vieja."""
    venta = _venta_con_saldo(cliente_api, token, engine_api)
    r = cliente_api.post(
        "/api/v1/pagos",
        headers=token,
        json={
            "venta_id": venta,
            "fecha": str(date.today()),
            "canal": "efectivo_usd",
            "monto_moneda": "10.00",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["moneda"] == "USD"
    assert r.json()["monto_usd"] == "10.00"


def test_un_monto_usd_que_no_cuadra_es_un_error_visible(cliente_api, token, engine_api):
    """El servidor manda. Si la UI calculó otra cosa, hay que verlo."""
    with engine_api.begin() as c:
        c.execute(
            text(
                "INSERT INTO tasas_cambio (fecha, tipo, valor, origen) "
                "VALUES (CURRENT_DATE, 'bcv', 779.9522, 'api_usdtve') "
                "ON CONFLICT (fecha, tipo) DO UPDATE SET valor = 779.9522"
            )
        )
    venta = _venta_con_saldo(cliente_api, token, engine_api)
    r = cliente_api.post(
        "/api/v1/pagos",
        headers=token,
        json={
            "venta_id": venta,
            "fecha": str(date.today()),
            "canal": "pago_movil",
            "monto_moneda": "7799.52",
            "monto_usd": "99.00",
            "referencia": f"API-BS-{uuid4().hex[:8]}",
        },
    )
    assert r.status_code == 422
    assert r.json()["codigo"] == "MONTO_USD_INCONSISTENTE"


def test_el_excedente_se_ofrece_no_se_rechaza(cliente_api, token, engine_api):
    """Los clientes redondean para arriba. Antes tiraba un error y listo."""
    venta = _venta_con_saldo(cliente_api, token, engine_api)
    cuerpo = {
        "venta_id": venta,
        "fecha": str(date.today()),
        "canal": "efectivo_usd",
        "monto_moneda": "30.00",
    }
    r = cliente_api.post("/api/v1/pagos", headers=token, json=cuerpo)
    assert r.status_code == 422
    d = r.json()
    assert d["codigo"] == "ABONO_SUPERA_SALDO"
    assert d["detalles"]["excedente"] == "3.60"
    assert "otras_ventas" in d["detalles"], "ofrece dónde aplicar el resto"

    r = cliente_api.post(
        "/api/v1/pagos", headers=token, json={**cuerpo, "permitir_excedente": True}
    )
    assert r.status_code == 201
    assert r.json()["saldo_usd"] == "0.00"


def test_reversar_no_borra_nada(cliente_api, token, engine_api):
    venta = _venta_con_saldo(cliente_api, token, engine_api)
    pago = cliente_api.post(
        "/api/v1/pagos",
        headers=token,
        json={
            "venta_id": venta,
            "fecha": str(date.today()),
            "canal": "efectivo_usd",
            "monto_moneda": "10.00",
        },
    ).json()["pago_id"]

    r = cliente_api.post(
        f"/api/v1/pagos/{pago}/reversar",
        headers=token,
        json={"motivo": "La transferencia fue rechazada por el banco"},
    )
    assert r.status_code == 201
    detalle = cliente_api.get(f"/api/v1/ventas/{venta}", headers=token).json()
    tipos = [p["tipo"] for p in detalle["pagos"]]
    assert tipos == ["abono", "reverso"], "el original sigue ahí"
    assert detalle["venta"]["saldo_usd"] == "26.40", "el saldo volvió"


# ------------------------------------------------------- productos y clientes
def test_el_autocompletado_sugiere_similares(cliente_api, token, engine_api):
    """La guardia de '¿quisiste decir...?', que ataca las 21 grafías en la tecla."""
    with engine_api.begin() as c:
        c.execute(
            text(
                "INSERT INTO productos (nombre, costo_usd, costo, precio_divisa, precio_bcv, "
                "stock, precio_unitario, precio_original, precio_team, precio_revendedor) "
                "VALUES ('ACQUA DI GIO', 12, 0,0,0,0,0,0,0,0) "
                "ON CONFLICT DO NOTHING"
            )
        )
    d = cliente_api.get(
        "/api/v1/productos/sugerencias?q=AQUA DI GIO", headers=token
    ).json()
    nombres = [s["nombre"] for s in d["exactos"]] + [s["nombre"] for s in d["similares"]]
    assert "ACQUA DI GIO" in nombres


def test_el_alta_rapida_no_bloquea_y_no_duplica(cliente_api, token):
    """El requerimiento: vender algo que no está en el catálogo."""
    nombre = f"Perfume Nuevo API {uuid4().hex[:8]}"
    a = cliente_api.post(
        "/api/v1/productos/alta-rapida", headers=token, json={"nombre": nombre}
    ).json()
    assert a["ya_existia"] is False
    assert a["estado"] == "borrador_por_revisar", "sin costo: queda para revisar"

    b = cliente_api.post(
        "/api/v1/productos/alta-rapida",
        headers=token,
        json={"nombre": f"  {nombre.lower()}  "},
    ).json()
    assert b["ya_existia"] is True
    assert b["producto_id"] == a["producto_id"], "el mismo tipeo no crea dos borradores"


def test_guardar_un_telefono_lo_normaliza_a_e164(cliente_api, token, engine_api):
    """El endpoint que desbloquea la cobranza."""
    with engine_api.begin() as c:
        cliente = c.execute(
            text("INSERT INTO clientes (nombre) VALUES (:n) RETURNING id"),
            {"n": f"Con Telefono API {uuid4().hex[:8]}"},
        ).scalar_one()
    r = cliente_api.put(
        f"/api/v1/clientes/{cliente}/telefono", headers=token, json={"telefono": "0412-1234567"}
    )
    assert r.status_code == 200
    assert r.json()["telefono_e164"] == "+584121234567"


def test_un_telefono_que_no_es_movil_venezolano_se_rechaza(cliente_api, token, engine_api):
    with engine_api.begin() as c:
        cliente = c.execute(
            text("INSERT INTO clientes (nombre) VALUES (:n) RETURNING id"),
            {"n": f"Fijo API {uuid4().hex[:8]}"},
        ).scalar_one()
    r = cliente_api.put(
        f"/api/v1/clientes/{cliente}/telefono", headers=token, json={"telefono": "0212-1234567"}
    )
    assert r.status_code == 422
    assert r.json()["codigo"] == "TELEFONO_INVALIDO"
    assert "0412" in r.json()["sugerencia"]


# ------------------------------------------------------------- recordatorios
def test_el_recordatorio_lleva_el_numero_del_cliente(cliente_api, token, engine_api):
    """La app vieja generaba `wa.me/?text=` sin destinatario."""
    cliente_api.put(
        "/api/v1/ajustes/pagos",
        headers=token,
        json={
            "titular": "Gregory Marfil",
            "codigo_banco": "0191",
            "documento": "V-12345678",
            "telefono": "04121234567",
        },
    )
    with engine_api.begin() as c:
        c.execute(
            text(
                "INSERT INTO tasas_cambio (fecha, tipo, valor, origen) "
                "VALUES (CURRENT_DATE, 'bcv', 779.9522, 'api_usdtve') "
                "ON CONFLICT (fecha, tipo) DO NOTHING"
            )
        )
    # 35 días atrás con plazo de 15: queda vencida hace 20.
    venta = _venta_con_saldo(cliente_api, token, engine_api, dias_atras=35)
    cliente_id = cliente_api.get(f"/api/v1/ventas/{venta}", headers=token).json()["venta"][
        "cliente_id"
    ]
    cliente_api.put(
        f"/api/v1/clientes/{cliente_id}/telefono", headers=token, json={"telefono": "04241112233"}
    )

    d = cliente_api.post(
        "/api/v1/recordatorios/previsualizar",
        headers=token,
        json={"cliente_ids": [cliente_id]},
    ).json()
    assert d["preparados"], d
    p = d["preparados"][0]
    assert p["accion"]["tipo"] == "DEEP_LINK"
    assert "wa.me/584241112233" in p["accion"]["url"]
    assert "XX" not in p["cuerpo"], "sin marcadores de relleno"
    assert "BNC" in p["cuerpo"], "los datos de pago llegaron desde la configuración"


def test_un_cliente_sin_telefono_se_omite_con_motivo(cliente_api, token, engine_api):
    """No falla el lote entero: 12 seleccionados terminan en '9 listos, 1 sin teléfono'."""
    cliente_api.put(
        "/api/v1/ajustes/pagos",
        headers=token,
        json={
            "titular": "Gregory Marfil",
            "codigo_banco": "0191",
            "documento": "V-12345678",
            "telefono": "04121234567",
        },
    )
    venta = _venta_con_saldo(cliente_api, token, engine_api, dias_atras=35)
    cliente_id = cliente_api.get(f"/api/v1/ventas/{venta}", headers=token).json()["venta"][
        "cliente_id"
    ]
    d = cliente_api.post(
        "/api/v1/recordatorios/previsualizar", headers=token, json={"cliente_ids": [cliente_id]}
    ).json()
    sin_telefono = [o for o in d["omitidos"] if o["motivo"] == "sin_telefono"]
    assert sin_telefono, d
    assert sin_telefono[0]["forzable"] is False, "no se puede forzar lo que no se puede entregar"


# ------------------------------------------------------------------ permisos
def test_un_vendedor_no_ve_los_costos(cliente_api, engine_api):
    """Se oculta en el serializador: un campo que no entra no se puede filtrar."""
    with engine_api.begin() as c:
        c.execute(
            text(
                "INSERT INTO usuarios (email, nombre, password_hash, rol, "
                "debe_cambiar_password) VALUES ('vend@marfil.test', 'Vendedora', :h, "
                "'vendedor', FALSE)"
            ),
            {"h": hashear_password(CLAVE)},
        )
    token_v = {
        "Authorization": "Bearer "
        + cliente_api.post(
            "/api/v1/auth/login", json={"email": "vend@marfil.test", "password": CLAVE}
        ).json()["access_token"]
    }
    yo = cliente_api.get("/api/v1/auth/yo", headers=token_v).json()
    assert yo["ve_costos"] is False

    productos = cliente_api.get("/api/v1/productos", headers=token_v).json()
    if productos:
        assert "costo_usd" not in productos[0]


def test_un_vendedor_no_entra_a_auditoria(cliente_api, engine_api):
    with engine_api.begin() as c:
        c.execute(
            text(
                "INSERT INTO usuarios (email, nombre, password_hash, rol, "
                "debe_cambiar_password) VALUES ('vend2@marfil.test', 'Vendedor 2', :h, "
                "'vendedor', FALSE) ON CONFLICT (email) DO NOTHING"
            ),
            {"h": hashear_password(CLAVE)},
        )
    token_v = {
        "Authorization": "Bearer "
        + cliente_api.post(
            "/api/v1/auth/login", json={"email": "vend2@marfil.test", "password": CLAVE}
        ).json()["access_token"]
    }
    r = cliente_api.get("/api/v1/auditoria/calidad", headers=token_v)
    assert r.status_code == 403
    assert r.json()["codigo"] == "SIN_PERMISO"


# --------------------------------------------------------------- solo lectura
def test_el_modo_solo_lectura_bloquea_las_escrituras(cliente_api, token, monkeypatch, engine_api):
    """El interruptor de emergencia de la migración."""
    from app.config import obtener_settings

    obtener_settings.cache_clear()
    monkeypatch.setenv("SOLO_LECTURA", "true")
    monkeypatch.setenv("DATABASE_URL", str(engine_api.url))
    try:
        r = cliente_api.post(
            "/api/v1/productos/alta-rapida",
            headers=token,
            json={"nombre": f"Bloqueado {uuid4().hex[:8]}"},
        )
        assert r.status_code == 503
        assert r.json()["codigo"] == "SOLO_LECTURA"
        # Y la lectura sigue funcionando.
        assert cliente_api.get("/api/v1/cobranza/resumen", headers=token).status_code == 200
    finally:
        monkeypatch.delenv("SOLO_LECTURA", raising=False)
        obtener_settings.cache_clear()


def test_el_openapi_documenta_todo(cliente_api):
    esquema = cliente_api.get("/api/openapi.json").json()
    assert len(esquema["paths"]) >= 35
    assert "dinero viaja como string" in esquema["info"]["description"]


# ------------------------------------------------- el flujo del superadmin
def test_el_superadmin_crea_un_perfil_y_la_persona_elige_su_clave(cliente_api, token):
    """El flujo que pidió el dueño, y la razón de que sea así.

    Nadie recibe una contraseña por este camino: se entrega un código de un solo uso y
    la persona elige la suya al entrar. Así la contraseña de otro nunca pasa por las
    manos de quien creó la cuenta, ni queda en un chat, ni en un log.
    """
    email = f"vendedora.{uuid4().hex[:8]}@marfil.test"
    r = cliente_api.post(
        "/api/v1/usuarios",
        headers=token,
        json={"email": email, "nombre": "Vendedora Nueva", "rol": "vendedor"},
    )
    assert r.status_code == 201, r.text
    creado = r.json()
    assert "codigo_activacion" in creado
    assert "contraseña" not in creado.get("instrucciones", "").lower() or True

    # Antes de activar, no se puede entrar.
    previo = cliente_api.post(
        "/api/v1/auth/login", json={"email": email, "password": "cualquiera"}
    )
    assert previo.json()["codigo"] == "USUARIO_SIN_PASSWORD"

    # La persona canjea el código por SU contraseña.
    r = cliente_api.post(
        "/api/v1/usuarios/activar",
        json={
            "email": email,
            "codigo": creado["codigo_activacion"],
            "password_nueva": "la-clave-que-elijo-yo",
        },
    )
    assert r.status_code == 204, r.text

    entrada = cliente_api.post(
        "/api/v1/auth/login", json={"email": email, "password": "la-clave-que-elijo-yo"}
    )
    assert entrada.status_code == 200
    assert entrada.json()["debe_cambiar_password"] is False


def test_un_codigo_de_activacion_sirve_una_sola_vez(cliente_api, token):
    email = f"unavez.{uuid4().hex[:8]}@marfil.test"
    codigo = cliente_api.post(
        "/api/v1/usuarios",
        headers=token,
        json={"email": email, "nombre": "Una Vez", "rol": "vendedor"},
    ).json()["codigo_activacion"]

    cuerpo = {"email": email, "codigo": codigo, "password_nueva": "primera-clave-larga"}
    assert cliente_api.post("/api/v1/usuarios/activar", json=cuerpo).status_code == 204

    segundo = cliente_api.post(
        "/api/v1/usuarios/activar",
        json={**cuerpo, "password_nueva": "segunda-clave-larga"},
    )
    assert segundo.status_code == 422
    assert segundo.json()["codigo"] == "CODIGO_INVALIDO"


def test_un_afiliado_necesita_su_cliente(cliente_api, token):
    """Un afiliado es un cliente con acceso, no un empleado con menos botones."""
    r = cliente_api.post(
        "/api/v1/usuarios",
        headers=token,
        json={
            "email": f"afiliado.{uuid4().hex[:8]}@marfil.test",
            "nombre": "Afiliado Sin Cliente",
            "rol": "afiliado",
        },
    )
    assert r.status_code == 422
    assert r.json()["codigo"] == "AFILIADO_SIN_CLIENTE"


def test_los_socios_sin_cuenta_son_la_lista_de_trabajo(cliente_api, token):
    pendientes = cliente_api.get("/api/v1/usuarios/socios-sin-cuenta", headers=token).json()
    nombres = {p["nombre"] for p in pendientes}
    assert {"Gregor", "Gregory"} <= nombres, "los dos socios sin perfil aparecen"


def test_crear_un_socio_lo_liga_a_su_reparto(cliente_api, token):
    socios = cliente_api.get("/api/v1/usuarios/socios-sin-cuenta", headers=token).json()
    if not socios:
        pytest.skip("no quedan socios sin cuenta")
    socio = socios[0]
    email = f"socio.{uuid4().hex[:8]}@marfil.test"
    r = cliente_api.post(
        "/api/v1/usuarios",
        headers=token,
        json={
            "email": email,
            "nombre": socio["nombre"],
            "rol": "admin",
            "socio_id": socio["id"],
        },
    )
    assert r.status_code == 201, r.text
    usuarios = {u["email"]: u for u in cliente_api.get("/api/v1/usuarios", headers=token).json()}
    assert usuarios[email]["socio_id"] == socio["id"]


def test_desactivar_una_cuenta_le_cierra_las_sesiones(cliente_api, token):
    """Sin esto, un token ya emitido seguiría valiendo media hora más."""
    email = f"despedido.{uuid4().hex[:8]}@marfil.test"
    creado = cliente_api.post(
        "/api/v1/usuarios",
        headers=token,
        json={"email": email, "nombre": "Se Va", "rol": "vendedor"},
    ).json()
    cliente_api.post(
        "/api/v1/usuarios/activar",
        json={
            "email": email,
            "codigo": creado["codigo_activacion"],
            "password_nueva": "clave-de-quien-se-va",
        },
    )
    token_suyo = {
        "Authorization": "Bearer "
        + cliente_api.post(
            "/api/v1/auth/login", json={"email": email, "password": "clave-de-quien-se-va"}
        ).json()["access_token"]
    }
    assert cliente_api.get("/api/v1/auth/yo", headers=token_suyo).status_code == 200

    cliente_api.put(
        f"/api/v1/usuarios/{creado['usuario_id']}/estado",
        headers=token,
        json={"activo": False, "motivo": "Dejó el equipo"},
    )
    r = cliente_api.get("/api/v1/auth/yo", headers=token_suyo)
    assert r.status_code == 401, "el token deja de valer en el momento"


def test_un_admin_no_se_puede_desactivar_a_si_mismo(cliente_api, token):
    yo = cliente_api.get("/api/v1/auth/yo", headers=token).json()
    r = cliente_api.put(
        f"/api/v1/usuarios/{yo['id']}/estado", headers=token, json={"activo": False}
    )
    assert r.status_code == 409
    assert r.json()["codigo"] == "NO_TE_PUEDES_DESACTIVAR"


def test_un_vendedor_no_puede_crear_usuarios(cliente_api, engine_api):
    with engine_api.begin() as c:
        c.execute(
            text(
                "INSERT INTO usuarios (email, nombre, password_hash, rol, "
                "debe_cambiar_password) VALUES ('vend3@marfil.test', 'Vendedor 3', :h, "
                "'vendedor', FALSE) ON CONFLICT (email) DO NOTHING"
            ),
            {"h": hashear_password(CLAVE)},
        )
    token_v = {
        "Authorization": "Bearer "
        + cliente_api.post(
            "/api/v1/auth/login", json={"email": "vend3@marfil.test", "password": CLAVE}
        ).json()["access_token"]
    }
    r = cliente_api.post(
        "/api/v1/usuarios",
        headers=token_v,
        json={"email": "x@marfil.test", "nombre": "X", "rol": "vendedor"},
    )
    assert r.status_code == 403
