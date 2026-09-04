"""Abonos y su reverso."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.deps import AdminOVendedor, PuedeEscribir, SesionDb, SoloAdmin
from app.models.enums import CanalPago
from app.services import pagos as svc

router = APIRouter(prefix="/pagos", tags=["pagos"])


class PagoEntrada(BaseModel):
    venta_id: int
    fecha: date
    #: `efectivo_usd`, `zelle`, `binance` y `usdt` no llevan tasa: el monto ya es en
    #: dolares. Es la ruta explicita que reemplaza el `tasa_bcv = 1.00` de la app vieja.
    canal: CanalPago
    monto_moneda: Decimal = Field(gt=0, description="Bolívares o dólares, según el canal")
    tasa_aplicada: Decimal | None = Field(default=None, gt=0)
    tasa_id: int | None = None
    #: Que serie usar para convertir. Solo aplica a los canales en bolivares.
    tipo_tasa: str = Field(default=svc.TIPO_TASA_POR_DEFECTO)
    #: Obligatorio solo con el canal `otro`, que puede ser de cualquiera de los dos
    #: lados. El resto de canales ya define su moneda.
    en_bolivares: bool | None = None
    monto_usd: Decimal | None = Field(
        default=None, description="Opcional: el servidor lo recalcula y verifica"
    )
    referencia: str | None = None
    cuota_id: int | None = None
    notas: str | None = None
    comprobante_url: str | None = None
    permitir_excedente: bool = False


@router.post("", status_code=201)
def registrar(datos: PagoEntrada, db: SesionDb, actual: AdminOVendedor, _: PuedeEscribir):
    resultado = svc.registrar(
        db,
        venta_id=datos.venta_id,
        fecha=datos.fecha,
        canal=datos.canal,
        monto_moneda=datos.monto_moneda,
        tasa_manual=datos.tasa_aplicada,
        tasa_id=datos.tasa_id,
        tipo_tasa=datos.tipo_tasa,
        en_bolivares_declarado=datos.en_bolivares,
        monto_usd_cliente=datos.monto_usd,
        referencia=datos.referencia,
        cuota_id=datos.cuota_id,
        notas=datos.notas,
        comprobante_url=datos.comprobante_url,
        usuario_id=actual.id,
        permitir_excedente=datos.permitir_excedente,
    )
    db.commit()
    return resultado


@router.get("/tasa-sugerida")
def tasa_sugerida(
    db: SesionDb,
    actual: AdminOVendedor,
    en_fecha: date | None = None,
    tipo: str = svc.TIPO_TASA_POR_DEFECTO,
):
    """La tasa que el formulario prefila, con su procedencia visible.

    `es_respaldo` es lo que la UI muestra como advertencia: la app vieja caía a un
    valor fijo de hace meses sin decirlo, y este negocio congela tasas por pago.
    """
    del actual
    from app.api.errors import ErrorNegocio

    try:
        t = svc.resolver_tasa(db, en_fecha=en_fecha or date.today(), tipo=tipo)
    except ErrorNegocio as exc:
        return {"disponible": False, "codigo": exc.codigo, "mensaje": exc.mensaje}
    return {
        "disponible": True,
        "tipo": tipo,
        "valor": t.valor,
        "origen": t.origen.value,
        "tasa_id": t.tasa_id,
        "procedencia": t.procedencia,
        "es_respaldo": t.es_respaldo,
    }


@router.get("/referencia-existe")
def referencia_existe(
    db: SesionDb,
    actual: AdminOVendedor,
    referencia: str = Query(min_length=1),
    monto_moneda: Decimal | None = None,
):
    """Evita contabilizar dos veces la misma transferencia. Barato y silencioso."""
    del actual
    filas = db.execute(
        text(
            "SELECT p.id, p.fecha, p.monto_moneda, p.moneda::text AS moneda, v.codigo "
            "FROM pagos p JOIN ventas v ON v.id = p.venta_id "
            "WHERE p.referencia = :r AND p.tipo = 'abono' ORDER BY p.fecha DESC LIMIT 5"
        ),
        {"r": referencia.strip()},
    ).all()
    return {
        "existe": bool(filas),
        "coincidencias": [dict(f._mapping) for f in filas],
        "mismo_monto": any(
            monto_moneda is not None and f.monto_moneda == monto_moneda for f in filas
        ),
    }


class ReversoEntrada(BaseModel):
    motivo: str = Field(min_length=5, description="Queda en el libro y en la auditoría")


@router.post("/{pago_id}/reversar", status_code=201)
def reversar(
    pago_id: int,
    datos: ReversoEntrada,
    db: SesionDb,
    actual: SoloAdmin,
    _: PuedeEscribir,
):
    """Anula un abono con una fila negativa: el original queda intacto.

    El libro es append-only por trigger, así que corregir es agregar, nunca editar.
    """
    reverso_id = svc.reversar(db, pago_id=pago_id, motivo=datos.motivo, usuario_id=actual.id)
    db.commit()
    return {"reverso_id": reverso_id, "anula_pago_id": pago_id}


@router.get("")
def listar(
    db: SesionDb,
    actual: AdminOVendedor,
    venta_id: int | None = None,
    limite: int = Query(default=100, le=500),
):
    del actual
    condiciones, params = ["TRUE"], {"limite": limite}
    if venta_id:
        condiciones.append("p.venta_id = :v")
        params["v"] = venta_id
    filas = db.execute(
        text(
            f"""
            SELECT p.id, p.fecha, p.tipo::text AS tipo, v.codigo AS venta, c.nombre AS cliente,
                   p.moneda::text AS moneda, p.monto_moneda, p.tasa_aplicada, p.monto_usd,
                   p.canal::text AS canal, p.referencia,
                   p.origen_tasa::text AS origen_tasa,
                   p.confianza_tasa::text AS confianza_tasa, p.motivo, p.notas
            FROM pagos p JOIN ventas v ON v.id = p.venta_id
            JOIN clientes c ON c.id = v.cliente_id
            WHERE {" AND ".join(condiciones)}
            ORDER BY p.fecha DESC, p.id DESC LIMIT :limite
            """
        ),
        params,
    ).all()
    return [dict(f._mapping) for f in filas]
