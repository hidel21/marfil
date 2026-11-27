"""La caja del negocio: saldo, movimientos y los aportes, retiros y ajustes."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.api.deps import PuedeEscribir, SesionDb, SoloAdmin
from app.models.enums import CanalPago
from app.services import caja as svc

router = APIRouter(prefix="/caja", tags=["caja"])


@router.get("")
def resumen(
    db: SesionDb,
    actual: SoloAdmin,
    desde: date | None = None,
    hasta: date | None = None,
    limite: int = Query(default=500, ge=1, le=2000),
):
    del actual
    return svc.resumen(db, desde=desde, hasta=hasta, limite=limite)


class MovimientoEntrada(BaseModel):
    fecha: date = Field(default_factory=date.today)
    tipo: Literal["aporte", "retiro", "ajuste"]
    monto_usd: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    concepto: str = Field(min_length=3, max_length=300)
    #: Solo para `ajuste`: un aporte siempre entra y un retiro siempre sale.
    sentido: Literal["entrada", "salida"] | None = None
    socio_id: int | None = None
    canal: CanalPago | None = None
    notas: str | None = Field(default=None, max_length=1000)


@router.post("/movimientos", status_code=201)
def registrar(datos: MovimientoEntrada, db: SesionDb, actual: SoloAdmin, _: PuedeEscribir):
    nuevo = svc.registrar(
        db,
        fecha=datos.fecha,
        tipo=datos.tipo,
        monto_usd=datos.monto_usd,
        concepto=datos.concepto,
        sentido=datos.sentido,
        socio_id=datos.socio_id,
        canal=datos.canal.value if datos.canal else None,
        notas=datos.notas,
        usuario_id=actual.id,
    )
    db.commit()
    return {"movimiento_id": nuevo}


class AnulacionEntrada(BaseModel):
    motivo: str = Field(min_length=5, max_length=500)


@router.post("/movimientos/{movimiento_id}/anular")
def anular(
    movimiento_id: int,
    datos: AnulacionEntrada,
    db: SesionDb,
    actual: SoloAdmin,
    _: PuedeEscribir,
):
    svc.anular(db, movimiento_id=movimiento_id, motivo=datos.motivo, usuario_id=actual.id)
    db.commit()
    return {"movimiento_id": movimiento_id, "anulado": True}
