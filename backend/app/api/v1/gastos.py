"""Gastos operativos separados del costo de inventario."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.deps import PuedeEscribir, SesionDb, SoloAdmin
from app.models.enums import CanalPago

router = APIRouter(prefix="/gastos", tags=["gastos"])


class GastoEntrada(BaseModel):
    fecha: date = Field(default_factory=date.today)
    categoria: str = Field(min_length=2, max_length=64)
    descripcion: str = Field(min_length=2, max_length=300)
    monto_usd: Decimal = Field(gt=0)
    monto_bs: Decimal | None = Field(default=None, ge=0)
    tasa_aplicada: Decimal | None = Field(default=None, gt=0)
    canal: CanalPago | None = None
    lote_id: int | None = None
    notas: str | None = Field(default=None, max_length=1000)


@router.get("")
def listar(
    db: SesionDb,
    actual: SoloAdmin,
    desde: date | None = None,
    hasta: date | None = None,
    categoria: str | None = None,
    limite: int = Query(default=200, le=1000),
):
    del actual
    condiciones, params = ["TRUE"], {"limite": limite}
    if desde:
        condiciones.append("g.fecha >= :desde")
        params["desde"] = desde
    if hasta:
        condiciones.append("g.fecha <= :hasta")
        params["hasta"] = hasta
    if categoria:
        condiciones.append("lower(g.categoria) = lower(:categoria)")
        params["categoria"] = categoria
    filas = (
        db.execute(
            text(
                f"""
            SELECT g.id, g.fecha, g.categoria, g.descripcion, g.monto_usd, g.monto_bs,
                   g.tasa_aplicada, g.canal::text AS canal, g.notas, l.codigo AS lote
              FROM gastos g LEFT JOIN lotes_compra l ON l.id = g.lote_id
             WHERE {" AND ".join(condiciones)}
             ORDER BY g.fecha DESC, g.id DESC LIMIT :limite
            """
            ),
            params,
        )
        .mappings()
        .all()
    )
    total = sum((f.monto_usd for f in filas), Decimal(0))
    return {"items": [dict(f) for f in filas], "total_usd": total}


@router.post("", status_code=201)
def crear(datos: GastoEntrada, db: SesionDb, actual: SoloAdmin, _: PuedeEscribir):
    nuevo = db.execute(
        text(
            """
            INSERT INTO gastos
              (fecha, lote_id, categoria, descripcion, monto_usd, monto_bs,
               tasa_aplicada, canal, notas, creado_por_usuario_id)
            VALUES (:fecha, :lote, :categoria, :descripcion, :usd, :bs, :tasa,
                    :canal, :notas, :usuario)
            RETURNING id
            """
        ),
        {
            "fecha": datos.fecha,
            "lote": datos.lote_id,
            "categoria": datos.categoria.strip().lower(),
            "descripcion": datos.descripcion.strip(),
            "usd": datos.monto_usd,
            "bs": datos.monto_bs,
            "tasa": datos.tasa_aplicada,
            "canal": datos.canal.value if datos.canal else None,
            "notas": datos.notas,
            "usuario": actual.id,
        },
    ).scalar_one()
    db.commit()
    return {"gasto_id": nuevo}


@router.get("/categorias")
def categorias(db: SesionDb, actual: SoloAdmin):
    del actual
    return (
        db.execute(
            text(
                "SELECT categoria, count(*) AS usos FROM gastos "
                "GROUP BY categoria ORDER BY usos DESC"
            )
        )
        .mappings()
        .all()
    )
