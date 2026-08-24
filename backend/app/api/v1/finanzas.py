"""Resultados, comisiones, caja y reparto informativo entre socios."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.deps import PuedeEscribir, SesionDb, SoloAdmin
from app.api.errors import NoEncontrado

router = APIRouter(prefix="/finanzas", tags=["finanzas"])


@router.get("/resumen")
def resumen(db: SesionDb, actual: SoloAdmin):
    del actual
    mensual = (
        db.execute(text("SELECT * FROM v_finanzas_mensuales ORDER BY mes DESC LIMIT 12"))
        .mappings()
        .all()
    )
    actual_mes = mensual[0] if mensual else {}
    cuentas = (
        db.execute(
            text(
                "SELECT COALESCE(sum(saldo_usd), 0) AS por_pagar_usd, "
                "count(*) FILTER (WHERE saldo_usd > 0) AS cuentas_abiertas FROM v_cuentas_pagar"
            )
        )
        .mappings()
        .one()
    )
    inventario = (
        db.execute(
            text(
                "SELECT COALESCE(sum(stock * costo_usd), 0) AS valor_costo_usd, "
                "COALESCE(sum(stock), 0) AS unidades FROM productos "
                "WHERE estado <> 'fusionado'"
            )
        )
        .mappings()
        .one()
    )
    return {
        "mes_actual": dict(actual_mes),
        "mensual": [dict(f) for f in reversed(mensual)],
        "cuentas_por_pagar": dict(cuentas),
        "inventario": dict(inventario),
    }


@router.get("/comisiones")
def comisiones(
    db: SesionDb, actual: SoloAdmin, desde: date | None = None, hasta: date | None = None
):
    del actual
    desde = desde or date.today().replace(day=1)
    hasta = hasta or date.today()
    tasa = db.execute(
        text(
            "SELECT COALESCE((SELECT valor FROM parametros_precio "
            "WHERE clave = 'TASA_COMISION' AND vigencia @> :fecha LIMIT 1), 0)"
        ),
        {"fecha": hasta},
    ).scalar_one()
    filas = (
        db.execute(
            text(
                """
            SELECT u.id AS usuario_id, u.nombre AS vendedor, count(v.id) AS ventas,
                   COALESCE(sum(v.total_usd), 0) AS vendido_usd,
                   COALESCE(sum(v.total_usd) * :tasa, 0) AS comision_usd
              FROM usuarios u LEFT JOIN ventas v ON v.vendedor_usuario_id = u.id
               AND v.fecha BETWEEN :desde AND :hasta AND v.estado_cobro <> 'anulada'
             WHERE u.rol IN ('admin', 'vendedor') AND u.activo
             GROUP BY u.id, u.nombre ORDER BY vendido_usd DESC
            """
            ),
            {"desde": desde, "hasta": hasta, "tasa": tasa},
        )
        .mappings()
        .all()
    )
    return {"desde": desde, "hasta": hasta, "tasa": tasa, "items": [dict(f) for f in filas]}


@router.get("/socios")
def socios(db: SesionDb, actual: SoloAdmin):
    del actual
    utilidad = db.execute(
        text(
            "SELECT COALESCE(utilidad_neta_usd, 0) FROM v_finanzas_mensuales "
            "WHERE mes = date_trunc('month', CURRENT_DATE)::date"
        )
    ).scalar() or Decimal(0)
    total_capital = db.execute(
        text("SELECT COALESCE(sum(capital_invertido), 0) FROM socios")
    ).scalar_one()
    filas = (
        db.execute(
            text(
                """
            SELECT s.id, s.nombre, s.capital_invertido, s.usuario_id, u.email,
                   CASE WHEN :capital > 0 THEN s.capital_invertido / :capital ELSE 0 END
                     AS participacion,
                   CASE WHEN :capital > 0 THEN :utilidad * s.capital_invertido / :capital ELSE 0 END
                     AS utilidad_estimada_usd
              FROM socios s LEFT JOIN usuarios u ON u.id = s.usuario_id ORDER BY s.nombre
            """
            ),
            {"capital": total_capital, "utilidad": utilidad},
        )
        .mappings()
        .all()
    )
    return {
        "capital_total_usd": total_capital,
        "utilidad_mes_usd": utilidad,
        "items": [dict(f) for f in filas],
    }


class CapitalEntrada(BaseModel):
    capital_invertido: Decimal = Field(ge=0)


@router.put("/socios/{socio_id}", status_code=204)
def actualizar_socio(
    socio_id: int, datos: CapitalEntrada, db: SesionDb, actual: SoloAdmin, _: PuedeEscribir
):
    afectadas = db.execute(
        text("UPDATE socios SET capital_invertido = :c, updated_at = now() WHERE id = :i"),
        {"c": datos.capital_invertido, "i": socio_id},
    ).rowcount
    if not afectadas:
        raise NoEncontrado("ese socio")
    db.commit()
