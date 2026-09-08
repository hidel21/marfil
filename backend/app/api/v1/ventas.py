"""Ventas. `POST /ventas/cotizar` es el preview y `POST /ventas` la escritura, y las
dos pasan por la misma funcion del guardia de precio."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.deps import AdminOVendedor, AlcanceDatos, PuedeEscribir, SesionDb, SoloAdmin
from app.api.errors import NoEncontrado
from app.models.enums import Moneda, NivelPrecio
from app.services import ventas as svc

router = APIRouter(prefix="/ventas", tags=["ventas"])


class LineaEntrada(BaseModel):
    producto_id: int
    cantidad: int = Field(ge=1)
    precio_unitario_usd: Decimal = Field(ge=0)
    descripcion_libre: str | None = None
    costo_unitario_usd: Decimal | None = Field(default=None, ge=0)
    motivo_desviacion: str | None = None


class CuotaEntrada(BaseModel):
    numero: int = Field(ge=1)
    fecha_vencimiento: date
    monto_usd: Decimal = Field(gt=0)


class VentaEntrada(BaseModel):
    cliente_id: int
    fecha: date
    #: VES = tasa BCV (+120 %), USD/USDT = divisa (+70 %). **Obligatorio y sin default**:
    #: es el control que reemplaza el `moneda='BCV'` hardcodeado y que corta la fuga.
    moneda_cotizacion: Moneda
    lineas: list[LineaEntrada] = Field(min_length=1)
    nivel_precio: NivelPrecio = NivelPrecio.PUBLICO
    vendedor_usuario_id: int | None = None
    plazo_dias: int | None = Field(default=None, ge=0, le=365)
    plan_cuotas: list[CuotaEntrada] | None = None
    notas: str | None = None
    autorizaciones: dict[int, str] = Field(
        default_factory=dict,
        description="Motivo por índice de línea, para autorizar una excepción de precio",
    )
    permitir_sobreventa: bool = False


def _a_entrada(datos: VentaEntrada, vendedor_id: int) -> svc.VentaEntrada:
    return svc.VentaEntrada(
        cliente_id=datos.cliente_id,
        vendedor_usuario_id=datos.vendedor_usuario_id or vendedor_id,
        fecha=datos.fecha,
        moneda_cotizacion=datos.moneda_cotizacion,
        nivel_precio=datos.nivel_precio,
        plazo_dias=datos.plazo_dias,
        notas=datos.notas,
        autorizaciones=datos.autorizaciones,
        permitir_sobreventa=datos.permitir_sobreventa,
        lineas=[
            svc.LineaEntrada(
                producto_id=x.producto_id,
                cantidad=x.cantidad,
                precio_unitario_usd=x.precio_unitario_usd,
                descripcion_libre=x.descripcion_libre,
                costo_unitario_usd=x.costo_unitario_usd,
                motivo_desviacion=x.motivo_desviacion,
            )
            for x in datos.lineas
        ],
        plan_cuotas=(
            [
                svc.CuotaEntrada(
                    numero=c.numero, fecha_vencimiento=c.fecha_vencimiento, monto_usd=c.monto_usd
                )
                for c in datos.plan_cuotas
            ]
            if datos.plan_cuotas
            else None
        ),
    )


@router.post("/cotizar")
def cotizar(datos: VentaEntrada, db: SesionDb, actual: AdminOVendedor):
    """Evalúa la venta sin escribir. El frontend lo llama en cada cambio.

    Devuelve, por línea: el precio de política del nivel declarado, el del otro nivel
    (para poder ofrecer "cambiá el nivel" como salida), la desviación, el stock
    resultante y las advertencias con su sugerencia.
    """
    c = svc.cotizar(db, _a_entrada(datos, actual.id), es_admin=actual.es_admin)
    return {
        "total_usd": c.total_usd,
        "costo_usd": c.costo_usd if actual.ve_costos else None,
        "ganancia_usd": c.ganancia_usd if actual.ve_costos else None,
        "plazo_dias": c.plazo_dias,
        "fecha_vencimiento": c.fecha_vencimiento,
        "bloqueada": c.bloqueada,
        "exige_admin": c.exige_admin,
        "lineas": [
            {k: v for k, v in linea.items() if actual.ve_costos or k != "costo_unitario_usd"}
            for linea in c.lineas
        ],
    }


@router.post("", status_code=201)
def crear(datos: VentaEntrada, db: SesionDb, actual: AdminOVendedor, _: PuedeEscribir):
    venta_id = svc.crear(
        db, _a_entrada(datos, actual.id), usuario_id=actual.id, es_admin=actual.es_admin
    )
    db.commit()
    fila = db.execute(
        text(
            "SELECT codigo, total_usd, saldo_usd, estado_cobro::text AS estado_cobro, "
            "fecha_vencimiento FROM ventas WHERE id = :i"
        ),
        {"i": venta_id},
    ).one()
    return {"venta_id": venta_id, **dict(fila._mapping)}


class PlanSugeridoEntrada(BaseModel):
    total_usd: Decimal = Field(gt=0)
    cuotas: int = Field(ge=2, le=12)
    primera_fecha: date
    frecuencia_dias: int = Field(default=30, ge=7, le=60)


@router.post("/plan-sugerido")
def plan_sugerido(datos: PlanSugeridoEntrada):
    """Reparte el total en cuotas exactas: el resto va a la última, sin perder centavos."""
    cuotas = svc.plan_sugerido(
        datos.total_usd, datos.cuotas, datos.primera_fecha, datos.frecuencia_dias
    )
    return {
        "cuotas": [
            {"numero": c.numero, "fecha_vencimiento": c.fecha_vencimiento, "monto_usd": c.monto_usd}
            for c in cuotas
        ],
        "suma": sum(c.monto_usd for c in cuotas),
    }


class AnulacionEntrada(BaseModel):
    motivo: str = Field(min_length=5, max_length=500)


@router.post("/{venta_id}/anular")
def anular(
    venta_id: int,
    datos: AnulacionEntrada,
    db: SesionDb,
    actual: SoloAdmin,
    _: PuedeEscribir,
):
    """Anula una venta y devuelve su stock. Solo un socio, y con motivo escrito.

    El motivo no es burocracia: es lo que despues explica, en Auditoria, por que un
    mes tuvo menos ventas de las que se recordaban.
    """
    resultado = svc.anular(db, venta_id=venta_id, motivo=datos.motivo, usuario_id=actual.id)
    db.commit()
    return resultado


@router.get("")
def listar(
    db: SesionDb,
    ambito: AlcanceDatos,
    cliente_id: int | None = None,
    con_saldo: bool | None = None,
    limite: int = Query(default=100, le=500),
):
    where, params = ambito.ventas_where
    params = dict(params)
    params["limite"] = limite
    condiciones = [where]
    if cliente_id:
        condiciones.append("v.cliente_id = :cliente")
        params["cliente"] = cliente_id
    if con_saldo is not None:
        condiciones.append("v.saldo_usd > 0" if con_saldo else "v.saldo_usd = 0")

    filas = db.execute(
        text(
            f"""
            SELECT v.id, v.codigo, v.fecha, c.nombre AS cliente, u.nombre AS vendedor,
                   v.moneda_cotizacion::text AS moneda, v.total_usd, v.saldo_usd,
                   v.estado_cobro::text AS estado_cobro, v.fecha_vencimiento,
                   v.tiene_plan_cuotas,
                   (SELECT string_agg(i.descripcion_libre, ', ') FROM venta_items i
                      WHERE i.venta_id = v.id) AS productos
            FROM ventas v
            JOIN clientes c ON c.id = v.cliente_id
            JOIN usuarios u ON u.id = v.vendedor_usuario_id
            WHERE {" AND ".join(condiciones)}
            ORDER BY v.fecha DESC, v.id DESC LIMIT :limite
            """
        ),
        params,
    ).all()
    return [dict(f._mapping) for f in filas]


@router.get("/{venta_id}")
def detalle(venta_id: int, db: SesionDb, ambito: AlcanceDatos):
    where, params = ambito.ventas_where
    venta = db.execute(
        text(
            f"SELECT v.*, c.nombre AS cliente_nombre, u.nombre AS vendedor_nombre "
            f"FROM ventas v JOIN clientes c ON c.id = v.cliente_id "
            f"JOIN usuarios u ON u.id = v.vendedor_usuario_id "
            f"WHERE v.id = :i AND {where}"
        ),
        {**params, "i": venta_id},
    ).one_or_none()
    if venta is None:
        raise NoEncontrado("esa venta")

    lineas = db.execute(
        text("SELECT * FROM venta_items WHERE venta_id = :i ORDER BY linea"), {"i": venta_id}
    ).all()
    cuotas = db.execute(
        text("SELECT * FROM cuotas WHERE venta_id = :i ORDER BY numero"), {"i": venta_id}
    ).all()
    pagos = db.execute(
        text(
            "SELECT id, fecha, tipo::text AS tipo, moneda::text AS moneda, monto_moneda, "
            "tasa_aplicada, monto_usd, canal::text AS canal, referencia, "
            "origen_tasa::text AS origen_tasa, confianza_tasa::text AS confianza_tasa, notas "
            "FROM pagos WHERE venta_id = :i ORDER BY fecha, id"
        ),
        {"i": venta_id},
    ).all()
    conciliacion = db.execute(
        text("SELECT * FROM v_conciliacion_ventas WHERE venta_id = :i"), {"i": venta_id}
    ).one_or_none()

    datos = dict(venta._mapping)
    ocultar = {"costo_usd", "saldo_congelado_migracion"}
    if not ambito.usuario.ve_costos:
        datos = {k: v for k, v in datos.items() if k not in ocultar}
    return {
        "venta": datos,
        "lineas": [dict(f._mapping) for f in lineas],
        "cuotas": [dict(f._mapping) for f in cuotas],
        "pagos": [dict(f._mapping) for f in pagos],
        "conciliacion": dict(conciliacion._mapping) if conciliacion else None,
    }
