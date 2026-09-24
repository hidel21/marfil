"""ETL del Excel V2: lo que tiene que valer para poder cargar un libro sin duplicar.

Cada test arma su propio libro con openpyxl y lo corre contra la base de test dentro
de una transaccion revertida. Los casos no son hipoteticos: cada uno es algo que casi
sale mal al cruzar el libro real contra una copia de produccion.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.etl import carga, cruce, libro
from app.jobs.operativos import SQL_GUARDAR_TASA
from tests.factories import crear_cliente

pytestmark = pytest.mark.usefixtures("engine")

CAB_VENTAS = [
    "ID venta",
    "Fecha venta",
    "Cliente",
    "Producto",
    "Precio pactado $",
    "Base del precio",
    "Cobros aplicados $",
    "Saldo $ ref.",
    "Estado",
    "Días vencidos",
    "Costo histórico $",
    "Vendedor",
    "Plazo días",
    "Vencimiento",
    "Fecha cierre confirmado",
    "Tratamiento",
    "Observaciones",
    "Origen",
    "Cobros por conciliar",
    "Diferencia al cierre $",
]
CAB_PAGOS = [
    "ID pago",
    "Fecha cobro",
    "ID venta",
    "Cliente",
    "Producto",
    "Método",
    "Recibido Bs",
    "Equivalente acordado $",
    "Base",
    "Tasa Bs / $",
    "Abono aplicable $",
    "Referencia",
    "Concepto",
    "Tratamiento",
    "Observaciones",
    "Origen",
    "Control",
]
CAB_EGRESOS = [
    "ID egreso",
    "Fecha",
    "Tipo",
    "Concepto / lote",
    "Importe $ ref.",
    "Importe Bs",
    "Base",
    "Método",
    "Tratamiento",
    "Control",
    "Observaciones",
    "Origen",
]


def _libro(tmp_path: Path, ventas=(), pagos=(), egresos=(), nombre="libro.xlsx") -> Path:
    """Un libro con la forma del real: titulo, instrucciones y despues la cabecera."""
    wb = Workbook()
    wb.remove(wb.active)
    for hoja, cabecera, filas in (
        ("VENTAS", CAB_VENTAS, ventas),
        ("PAGOS", CAB_PAGOS, pagos),
        ("GASTOS Y COMPRAS", CAB_EGRESOS, egresos),
    ):
        ws = wb.create_sheet(hoja)
        ws.append([hoja.title()])
        ws.append(["Instrucciones que el ETL tiene que saltar."])
        ws.append(cabecera)
        for f in filas:
            ws.append([f.get(c) for c in cabecera])
    ruta = tmp_path / nombre
    wb.save(ruta)
    return ruta


def _venta(ref, cliente, producto, precio, fecha, **extra):
    return {
        "ID venta": ref,
        "Fecha venta": datetime.combine(fecha, datetime.min.time()),
        "Cliente": cliente,
        "Producto": producto,
        "Precio pactado $": precio,
        "Base del precio": "BCV",
        "Tratamiento": "Incluir",
        "Plazo días": 30,
        **extra,
    }


def _pago(ref, venta_ref, fecha, **extra):
    return {
        "ID pago": ref,
        "Fecha cobro": datetime.combine(fecha, datetime.min.time()),
        "ID venta": venta_ref,
        "Método": "Pago móvil",
        "Base": "BCV",
        "Tratamiento": "Incluir",
        **extra,
    }


@pytest.fixture
def sesion(conn):
    with Session(bind=conn) as s:
        yield s


def _tasa(sesion, fecha: date, valor: str) -> None:
    sesion.execute(
        SQL_GUARDAR_TASA,
        {"f": fecha, "t": "bcv", "v": Decimal(valor), "o": "api_dolarapi", "c": "alta", "p": "{}"},
    )


def _planificar(sesion, ruta):
    return cruce.planificar(sesion, libro.leer(ruta), mapeo=libro.MAPEO_VERSION)


def _tipos(plan, etapa):
    return {a.ref: a.tipo for a in plan.de(etapa)}


def _venta_existente(sesion, cliente: str, producto: str, total: str, fecha: date) -> int:
    """Una venta cargada por fuera del ETL, como las que dejo la migracion original."""
    from app.db.session import fijar_contexto
    from app.models.enums import Moneda, NivelPrecio
    from app.services import ventas as svc

    # Como la API: sin esta marca los triggers de compatibilidad le agregan su linea.
    fijar_contexto(sesion, escritor="api")
    cliente_id = crear_cliente(sesion.connection(), nombre=cliente)
    producto_id = sesion.execute(
        text(
            "INSERT INTO productos (nombre, estado, costo, precio_divisa, precio_bcv, stock, "
            "precio_unitario, precio_original, precio_team, precio_revendedor) "
            "VALUES (:n, 'borrador_por_revisar', 0,0,0,0,0,0,0,0) RETURNING id"
        ),
        {"n": producto},
    ).scalar_one()
    return svc.crear(
        sesion,
        svc.VentaEntrada(
            cliente_id=cliente_id,
            vendedor_usuario_id=1,
            fecha=fecha,
            moneda_cotizacion=Moneda.USD,
            nivel_precio=NivelPrecio.PUBLICO,
            lineas=[
                svc.LineaEntrada(
                    producto_id=producto_id, cantidad=1, precio_unitario_usd=Decimal(total)
                )
            ],
            permitir_sobreventa=True,
            plazo_dias=15,
        ),
        usuario_id=None,
        es_admin=True,
    )


# ------------------------------------------------------------------- extraer
def test_las_filas_de_plantilla_no_son_ventas(tmp_path):
    """El libro real trae 250 IDs de venta generados y solo 75 con datos."""
    ruta = _libro(
        tmp_path,
        ventas=[
            _venta("V-001", "Ana", "Cloud", 30, date(2026, 7, 1)),
            {"ID venta": "V-002"},
            {"ID venta": "V-003"},
        ],
    )
    datos = libro.leer(ruta)
    assert [v.ref for v in datos.ventas] == ["V-001"]


def test_los_montos_no_pasan_por_float(tmp_path):
    ruta = _libro(
        tmp_path, pagos=[_pago("P-001", "V-001", date(2026, 7, 1), **{"Recibido Bs": 7466.56})]
    )
    assert libro.leer(ruta).pagos[0].monto_bs == Decimal("7466.56")


# ----------------------------------------------------------------- planificar
def test_planificar_no_escribe_nada(sesion, tmp_path):
    ruta = _libro(tmp_path, ventas=[_venta("V-001", "Ana Nueva", "Cloud", 30, date(2026, 7, 1))])
    antes = sesion.execute(text("SELECT count(*) FROM ventas")).scalar_one()
    plan = _planificar(sesion, ruta)
    assert _tipos(plan, "ventas") == {"V-001": "crear"}
    assert sesion.execute(text("SELECT count(*) FROM ventas")).scalar_one() == antes


def test_lo_que_el_libro_no_confirma_no_se_carga(sesion, tmp_path):
    """Nada se inventa: sin precio, sin base o en revision, la venta se omite."""
    ruta = _libro(
        tmp_path,
        ventas=[
            _venta("V-001", "Ana", "Cloud", None, date(2026, 7, 1)),
            _venta(
                "V-002",
                "Ana",
                "Cloud",
                30,
                date(2026, 7, 1),
                **{"Base del precio": "Sin confirmar"},
            ),
            _venta("V-003", "Ana", "Cloud", 30, date(2026, 7, 1), Tratamiento="Revisar"),
        ],
    )
    assert set(_tipos(_planificar(sesion, ruta), "ventas").values()) == {"omitir"}


def test_la_misma_venta_con_otra_fecha_se_actualiza_no_se_duplica(sesion, tmp_path):
    """La migracion original no tenia fecha de venta: la de la base es sintetizada."""
    vid = _venta_existente(sesion, "Ángel", "Bharara King", "42", date(2026, 6, 28))
    ruta = _libro(
        tmp_path, ventas=[_venta("V-002", "Angel", "Bharara King", 42, date(2026, 6, 20))]
    )
    plan = _planificar(sesion, ruta)
    accion = plan.de("ventas")[0]
    assert accion.tipo == "actualizar"
    assert accion.destino_id == vid
    assert accion.cambios["fecha"] == ["2026-06-28", "2026-06-20"]

    carga.aplicar(sesion, plan, usuario_id=1)
    fecha, vence = sesion.execute(
        text("SELECT fecha, fecha_vencimiento FROM ventas WHERE id = :i"), {"i": vid}
    ).one()
    assert fecha == date(2026, 6, 20)
    # El vencimiento sale de la cuota implicita: si no se movia, la mora quedaba vieja.
    assert vence == date(2026, 7, 20)
    assert sesion.execute(text("SELECT count(*) FROM ventas")).scalar_one() == 1


def test_un_empate_lo_desempata_el_precio(sesion, tmp_path):
    """Dos compras del mismo perfume por el mismo cliente: el ID de hoja no desempata."""
    vid = _venta_existente(sesion, "Ricardo", "Acqua di Gio", "24", date(2026, 8, 2))
    ruta = _libro(
        tmp_path,
        ventas=[
            _venta("V-023", "Ricardo", "Acqua di Gio", 24, date(2026, 8, 8)),
            _venta("V-049", "Ricardo", "Acqua di Gio", 16, date(2026, 8, 24)),
        ],
    )
    plan = _planificar(sesion, ruta)
    por_ref = {a.ref: a for a in plan.de("ventas")}
    assert por_ref["V-023"].destino_id == vid
    assert por_ref["V-049"].tipo == "crear"


def test_un_cliente_abreviado_se_asocia_si_es_unico(sesion, tmp_path):
    """El libro dice "Landaeta" y un socio ya habia creado a "landaeta juan"."""
    cid = crear_cliente(sesion.connection(), nombre="landaeta juan")
    ruta = _libro(tmp_path, ventas=[_venta("V-044", "Landaeta", "Asad", 22, date(2026, 8, 17))])
    accion = _planificar(sesion, ruta).de("ventas")[0]
    assert accion.datos["cliente_id"] == cid
    assert accion.confianza == "media"
    assert any("landaeta juan" in a for a in accion.avisos)


# --------------------------------------------------------------------- pagos
def test_un_abono_mal_convertido_se_corrige_con_su_fecha_original(sesion, tmp_path):
    """Lo acordado manda. El reverso cae en el mes del abono, no en el de la carga."""
    from app.models.enums import CanalPago
    from app.services import pagos as pagos_svc

    vid = _venta_existente(sesion, "Polanco", "Honor & Glory", "35", date(2026, 6, 30))
    malo = pagos_svc.registrar(
        sesion,
        venta_id=vid,
        fecha=date(2026, 7, 11),
        canal=CanalPago.PAGO_MOVIL,
        monto_moneda=Decimal("14193.87"),
        tasa_manual=Decimal("1088.44"),
        referencia="5460",
    )
    ruta = _libro(
        tmp_path,
        ventas=[_venta("V-008", "Polanco", "Honor & Glory", 35, date(2026, 6, 30))],
        pagos=[
            _pago(
                "P-019",
                "V-008",
                date(2026, 7, 11),
                **{"Recibido Bs": 14193.87, "Equivalente acordado $": 20, "Referencia": "5460"},
            )
        ],
    )
    plan = _planificar(sesion, ruta)
    assert _tipos(plan, "pagos") == {"P-019": "corregir"}

    carga.aplicar(sesion, plan, usuario_id=1)
    reverso = sesion.execute(
        text("SELECT fecha, monto_usd FROM pagos WHERE anula_pago_id = :p"), {"p": malo["pago_id"]}
    ).one()
    assert reverso.fecha == date(2026, 7, 11)
    assert reverso.monto_usd == Decimal("-13.04")
    saldo = sesion.execute(text("SELECT saldo_usd FROM ventas WHERE id = :i"), {"i": vid}).scalar()
    assert saldo == Decimal("15.00")
    assert (
        sesion.execute(text("SELECT count(*) FROM v_conciliacion_pagos WHERE NOT ok")).scalar() == 0
    )


def test_varios_abonos_mal_convertidos_se_corrigen_juntos(sesion, tmp_path):
    """Suman bien en total y mal uno por uno: corregir de a uno "excede" el saldo."""
    from app.models.enums import CanalPago
    from app.services import pagos as pagos_svc

    vid = _venta_existente(sesion, "Ricardo", "Universe", "42", date(2026, 7, 3))
    for fecha, bs, ref in (
        (date(2026, 6, 29), "11823", "9373"),
        (date(2026, 7, 16), "8730", "1008"),
        (date(2026, 8, 5), "8307", "542"),
    ):
        pagos_svc.registrar(
            sesion,
            venta_id=vid,
            fecha=fecha,
            canal=CanalPago.PAGO_MOVIL,
            monto_moneda=Decimal(bs),
            tasa_manual=Decimal("687.14"),
            referencia=ref,
        )
    ruta = _libro(
        tmp_path,
        ventas=[_venta("V-004", "Ricardo", "Universe", 42, date(2026, 7, 3))],
        pagos=[
            _pago(
                "P-007",
                "V-004",
                date(2026, 6, 29),
                **{"Recibido Bs": 11823, "Equivalente acordado $": 19, "Referencia": "9373"},
            ),
            _pago(
                "P-008",
                "V-004",
                date(2026, 7, 16),
                **{"Recibido Bs": 8730, "Equivalente acordado $": 12, "Referencia": "1008"},
            ),
            _pago(
                "P-009",
                "V-004",
                date(2026, 8, 5),
                **{"Recibido Bs": 8307, "Equivalente acordado $": 11, "Referencia": "0542"},
            ),
        ],
    )
    carga.aplicar(sesion, _planificar(sesion, ruta), usuario_id=1)
    saldo = sesion.execute(text("SELECT saldo_usd FROM ventas WHERE id = :i"), {"i": vid}).scalar()
    assert saldo == Decimal("0.00")


def test_sin_tasa_reciente_el_pago_en_bolivares_no_se_convierte(sesion, tmp_path):
    """Una tasa de hace tres semanas es un job de captura caido, no la tasa del dia."""
    _tasa(sesion, date(2026, 9, 1), "800")
    ruta = _libro(
        tmp_path,
        ventas=[_venta("V-001", "Ana Tasa", "Cloud", 30, date(2026, 9, 1))],
        pagos=[_pago("P-001", "V-001", date(2026, 9, 24), **{"Recibido Bs": 8000})],
    )
    accion = _planificar(sesion, ruta).de("pagos")[0]
    assert accion.tipo == "omitir"
    assert "tasa" in accion.motivo.lower()


def test_con_tasa_del_dia_se_convierte_como_la_pantalla(sesion, tmp_path):
    _tasa(sesion, date(2026, 9, 18), "848.5")
    ruta = _libro(
        tmp_path,
        ventas=[_venta("V-001", "Ana Tasa2", "Cloud", 30, date(2026, 9, 1))],
        pagos=[_pago("P-001", "V-001", date(2026, 9, 18), **{"Recibido Bs": 848.5})],
    )
    accion = _planificar(sesion, ruta).de("pagos")[0]
    assert accion.tipo == "crear"
    assert accion.datos["monto_usd"] == Decimal("1.00")
    assert accion.confianza == "media"


def test_un_abono_que_excede_la_deuda_se_omite_en_vez_de_tumbar_la_carga(sesion, tmp_path):
    ruta = _libro(
        tmp_path,
        ventas=[_venta("V-059", "Landaeta X", "Cloud", 26, date(2026, 9, 10))],
        pagos=[
            _pago(
                "P-074",
                "V-059",
                date(2026, 9, 10),
                **{"Equivalente acordado $": 13, "Método": "Efectivo", "Base": "Divisa"},
            ),
            _pago(
                "P-067",
                "V-059",
                date(2026, 9, 18),
                **{"Equivalente acordado $": 15, "Método": "Efectivo", "Base": "Divisa"},
            ),
        ],
    )
    assert _tipos(_planificar(sesion, ruta), "pagos") == {"P-074": "crear", "P-067": "omitir"}


# ------------------------------------------------------------------- egresos
def test_una_compra_sin_detalle_suma_su_total_sin_tocar_stock(sesion, tmp_path):
    """El total del lote sale de sus lineas: sin linea, el lote contaria $0."""
    ruta = _libro(
        tmp_path,
        egresos=[
            {
                "ID egreso": "E-004",
                "Fecha": datetime(2026, 6, 19),
                "Tipo": "Compra",
                "Concepto / lote": "Lote 19/06/2026",
                "Importe $ ref.": 99,
                "Base": "USDT",
                "Método": "Binance",
                "Tratamiento": "Incluir",
            },
            {
                "ID egreso": "E-002",
                "Fecha": datetime(2026, 8, 12),
                "Tipo": "Gasto",
                "Concepto / lote": "Muestra",
                "Importe $ ref.": 1,
                "Tratamiento": "Sin caja",
            },
        ],
    )
    plan = _planificar(sesion, ruta)
    assert _tipos(plan, "egresos") == {"E-004": "crear", "E-002": "omitir"}
    carga.aplicar(sesion, plan, usuario_id=1)
    total, pagado = sesion.execute(
        text(
            "SELECT l.subtotal_calculado_usd, "
            "(SELECT sum(monto_usd) FROM pagos_compra WHERE lote_id = l.id) "
            "FROM lotes_compra l WHERE codigo = 'EXCEL-E-004'"
        )
    ).one()
    assert total == Decimal("99.00") and pagado == Decimal("99.00")
    assert sesion.execute(text("SELECT count(*) FROM movimientos_stock")).scalar() == 0


# ------------------------------------------------------------------ repetir
def test_aplicar_dos_veces_el_mismo_archivo_se_rechaza(sesion, tmp_path):
    ruta = _libro(tmp_path, ventas=[_venta("V-001", "Ana Repetida", "Cloud", 30, date(2026, 7, 1))])
    carga.aplicar(sesion, _planificar(sesion, ruta), usuario_id=1)
    with pytest.raises(carga.PlanYaAplicado):
        carga.aplicar(sesion, _planificar(sesion, ruta), usuario_id=1)


def test_una_version_nueva_del_libro_solo_aplica_lo_distinto(sesion, tmp_path):
    """El linaje reconoce cada fila por su ID de hoja, no por parecido."""
    v1 = _libro(
        tmp_path,
        ventas=[_venta("V-001", "Ana Linaje", "Cloud", 30, date(2026, 7, 1))],
        nombre="v1.xlsx",
    )
    carga.aplicar(sesion, _planificar(sesion, v1), usuario_id=1)
    v2 = _libro(
        tmp_path,
        ventas=[
            _venta("V-001", "Ana Linaje", "Cloud", 30, date(2026, 7, 2)),
            _venta("V-002", "Ana Linaje", "Yara", 24, date(2026, 7, 5)),
        ],
        nombre="v2.xlsx",
    )
    plan = _planificar(sesion, v2)
    assert _tipos(plan, "ventas") == {"V-001": "actualizar", "V-002": "crear"}
    assert plan.de("ventas")[0].metodo == "manual", "cruzada por linaje, no por parecido"


# ------------------------------------------------------ regresion del reverso
def test_un_reverso_no_descuadra_la_conciliacion(sesion):
    """El reverso copiaba los bolivares en positivo y cada uno era un descuadre."""
    from app.models.enums import CanalPago
    from app.services import pagos as pagos_svc

    vid = _venta_existente(sesion, "Belisario", "Bad Boy", "24", date(2026, 7, 29))
    pago = pagos_svc.registrar(
        sesion,
        venta_id=vid,
        fecha=date(2026, 8, 1),
        canal=CanalPago.PAGO_MOVIL,
        monto_moneda=Decimal("7500"),
        tasa_manual=Decimal("750"),
    )
    pagos_svc.reversar(sesion, pago_id=pago["pago_id"], motivo="cargado dos veces")
    malos = sesion.execute(text("SELECT count(*) FROM v_conciliacion_pagos WHERE NOT ok")).scalar()
    assert malos == 0


# ------------------------------------------- linaje despues de corregir o anular
def test_un_abono_corregido_despues_de_importar_no_se_vuelve_a_cargar(sesion, tmp_path):
    """El linaje apunta al abono original; si se reverso y reemplazo, se busca el nuevo.

    Paso en produccion: sin esto, reimportar el libro trataba el pago como nuevo y,
    con saldo disponible, lo habria registrado dos veces.
    """
    from app.models.enums import CanalPago
    from app.services import pagos as pagos_svc

    _tasa(sesion, date(2026, 6, 26), "622.2135")
    ruta = _libro(
        tmp_path,
        ventas=[_venta("V-003", "Amarista Linaje", "Khamrah", 42, date(2026, 6, 20))],
        pagos=[_pago("P-003", "V-003", date(2026, 6, 27), **{"Recibido Bs": 13066.48})],
    )
    carga.aplicar(sesion, _planificar(sesion, ruta), usuario_id=1)
    pago_id, venta_id = sesion.execute(
        text("SELECT id, venta_id FROM pagos WHERE monto_moneda = 13066.48 AND tipo = 'abono'")
    ).one()
    # Un socio lo corrige a mano: reverso con su fecha y registro con otra tasa.
    pagos_svc.reversar(sesion, pago_id=pago_id, motivo="tasa mal", fecha=date(2026, 6, 27))
    pagos_svc.registrar(sesion, venta_id=venta_id, fecha=date(2026, 6, 27),
                        canal=CanalPago.PAGO_MOVIL, monto_moneda=Decimal("13066.48"),
                        tasa_manual=Decimal("622.2135"))

    v2 = _libro(tmp_path, nombre="v2.xlsx",
                ventas=[_venta("V-003", "Amarista Linaje", "Khamrah", 42, date(2026, 6, 20))],
                pagos=[_pago("P-003", "V-003", date(2026, 6, 27), **{"Recibido Bs": 13066.48})])
    assert _tipos(_planificar(sesion, v2), "pagos") == {"P-003": "igual"}


def test_una_venta_anulada_despues_de_importar_no_se_recrea(sesion, tmp_path):
    from app.services import ventas as ventas_svc

    ruta = _libro(tmp_path, ventas=[_venta("V-001", "Ana Anulada", "Cloud", 30, date(2026, 7, 1))])
    resultado = carga.aplicar(sesion, _planificar(sesion, ruta), usuario_id=1)
    ventas_svc.anular(sesion, venta_id=resultado.creados["V-001"], motivo="cargada por error")

    v2 = _libro(tmp_path, nombre="v2.xlsx",
                ventas=[_venta("V-001", "Ana Anulada", "Cloud", 30, date(2026, 7, 2))])
    accion = _planificar(sesion, v2).de("ventas")[0]
    assert accion.tipo == "omitir"
    assert "anuló" in accion.motivo
