"""Analisis de ventas y cobros por periodo y por dimension. Ver `services/analisis.py`."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Query

from app.api.deps import SesionDb, SoloAdmin
from app.services import analisis as svc

router = APIRouter(prefix="/analisis", tags=["analisis"])


@router.get("")
def analizar(
    db: SesionDb,
    actual: SoloAdmin,
    desde: date | None = None,
    hasta: date | None = None,
    agrupar: str = Query(default="dia", pattern="^(dia|semana|quincena|mes)$"),
    vendedor_id: int | None = None,
    cliente_id: int | None = None,
    producto_id: int | None = None,
    linea: str | None = None,
    moneda: str | None = Query(default=None, pattern="^(VES|USD|USDT)$"),
    canal: str | None = None,
):
    """Solo socios: incluye costos y ganancia."""
    del actual
    hasta = hasta or date.today()
    desde = desde or hasta - timedelta(days=29)
    filtros = svc.Filtros(
        desde=desde, hasta=hasta, agrupar=agrupar, vendedor_id=vendedor_id,
        cliente_id=cliente_id, producto_id=producto_id, linea=linea or None,
        moneda=moneda, canal=canal or None,
    )
    return svc.analizar(db, filtros)


@router.get("/opciones")
def opciones(db: SesionDb, actual: SoloAdmin):
    del actual
    return svc.opciones(db)
