"""Cobranza: quien debe, desde cuando, y como avisarle."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query

from app.api.deps import AlcanceDatos, SesionDb, Usuario
from app.core.dinero import cuantizar
from app.schemas.cobranza import (
    ClienteEnCobranza,
    ResumenCobranzaSalida,
    Tramo,
)
from app.schemas.comun import Drill, Metrica
from app.services import cobranza as svc

router = APIRouter(prefix="/cobranza", tags=["cobranza"])


@router.get("/resumen", response_model=ResumenCobranzaSalida)
def resumen(db: SesionDb, actual: Usuario):
    del actual
    r = svc.resumen(db)
    ahora = datetime.now()

    def metrica(clave, etiqueta, valor, definicion, params=None, moneda="USD"):
        es_monto = moneda is not None
        return Metrica(
            clave=clave,
            etiqueta=etiqueta,
            valor=(f"{cuantizar(valor):.2f}" if es_monto else str(int(valor))),
            es_monto=es_monto,
            moneda=moneda,
            definicion=definicion,
            calculado_at=ahora,
            drill=Drill(endpoint="/api/v1/cobranza", params=params or {}),
        )

    return ResumenCobranzaSalida(
        metricas=[
            metrica(
                "deuda_total",
                "Deuda total",
                r.deuda_total_usd,
                "Suma de ventas.saldo_usd donde saldo_usd > 0",
            ),
            metrica(
                "deuda_clientes",
                "Deuda de clientes",
                r.deuda_clientes_usd,
                "Lo mismo, excluyendo el autoconsumo de los socios",
                {"incluir_socios": False},
            ),
            metrica(
                "deuda_socios",
                "Autoconsumo de socios",
                r.deuda_socios_usd,
                "Deuda de clientes marcados como socios: no es ingreso real",
            ),
            metrica(
                "monto_vencido",
                "Vencido",
                r.monto_vencido_usd,
                "Saldo de las ventas cuyo vencimiento ya pasó",
                {"solo_vencidas": True},
            ),
            metrica(
                "sin_telefono",
                "Deudores sin teléfono",
                r.sin_telefono,
                "Clientes con saldo y sin telefono_e164: no se les puede notificar",
                {"sin_telefono": True},
                moneda=None,
            ),
            metrica(
                "monto_sin_telefono",
                "Deuda no notificable",
                r.monto_sin_telefono_usd,
                "Cuánta plata está vencida sin forma de reclamarla",
                {"sin_telefono": True},
            ),
        ],
        tramos=[Tramo(**t) for t in r.buckets],
        semaforos=[Tramo(**s) for s in r.semaforos],
        calculado_at=ahora,
    )


@router.get("", response_model=list[ClienteEnCobranza])
def listar(
    db: SesionDb,
    ambito: AlcanceDatos,
    tramo: str | None = Query(default=None, description="al_dia, 1_7, 8_15, 16_30, 31_60, mas_60"),
    semaforo: str | None = Query(default=None, description="al_dia, por_vencer, vencido, moroso"),
    sin_abonos: bool | None = Query(default=None, description="Los que nunca abonaron"),
    sin_telefono: bool | None = Query(default=None, description="Los que no se pueden notificar"),
    incluir_socios: bool = Query(default=True),
):
    """Vista por cliente. Es la que manda: el recordatorio va a una persona."""
    return svc.por_cliente(
        db,
        bucket=tramo,
        semaforo=semaforo,
        sin_abonos=sin_abonos,
        sin_telefono=sin_telefono,
        incluir_socios=incluir_socios,
        vendedor_usuario_id=(
            ambito.usuario.id if ambito.usuario.es_vendedor else None
        ),
    )


@router.get("/por-venta")
def listar_por_venta(
    db: SesionDb,
    actual: Usuario,
    tramo: str | None = None,
    semaforo: str | None = None,
):
    del actual
    return svc.por_venta(db, bucket=tramo, semaforo=semaforo)
