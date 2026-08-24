"""Auditoria: la actividad, las conciliaciones y la calidad de los datos."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Query
from sqlalchemy import text

from app.api.deps import SesionDb, SoloAdmin
from app.schemas.cobranza import TarjetaCalidad

router = APIRouter(prefix="/auditoria", tags=["auditoria"])


@router.get("/calidad", response_model=list[TarjetaCalidad])
def calidad(db: SesionDb, actual: SoloAdmin, incluir_resueltas: bool = False):
    """Las tarjetas del panel. Rojas primero, y solo las que tienen algo que hacer."""
    del actual
    filtro = "" if incluir_resueltas else "WHERE visible"
    return [
        dict(f._mapping) for f in db.execute(text(f"SELECT * FROM v_calidad_datos {filtro}")).all()
    ]


@router.get("/conciliacion")
def conciliacion(
    db: SesionDb,
    actual: SoloAdmin,
    tipo: str = Query(default="ventas", pattern="^(ventas|pagos|stock)$"),
    solo_descuadres: bool = True,
):
    """El saldo almacenado y el calculado, uno al lado del otro.

    Es el pedido de "auditar facilmente" comprimido en una pantalla: el almacenado es
    sobre el que actua el negocio, el calculado es la verdad.
    """
    del actual
    vista = {
        "ventas": "v_conciliacion_ventas",
        "pagos": "v_conciliacion_pagos",
        "stock": "v_conciliacion_stock",
    }[tipo]
    where = "WHERE NOT ok" if solo_descuadres else ""
    filas = [dict(f._mapping) for f in db.execute(text(f"SELECT * FROM {vista} {where}")).all()]
    total = db.execute(text(f"SELECT count(*) FROM {vista}")).scalar_one()
    descuadres = db.execute(text(f"SELECT count(*) FROM {vista} WHERE NOT ok")).scalar_one()
    return {
        "tipo": tipo,
        "filas_revisadas": total,
        "filas_descuadradas": descuadres,
        "ok": descuadres == 0,
        "items": filas,
    }


@router.get("/fuga-precio")
def fuga_precio(db: SesionDb, actual: SoloAdmin):
    """Las lineas cobradas bajo la politica, con nombre y monto.

    Convierte un hallazgo puntual de un informe en un numero vivo del que alguien es
    responsable.
    """
    del actual
    items = [
        dict(f._mapping)
        for f in db.execute(text("SELECT * FROM v_fuga_precio ORDER BY fuga_usd DESC")).all()
    ]
    por_vendedor = [
        dict(f._mapping)
        for f in db.execute(
            text(
                "SELECT vendedor, count(*) AS lineas, sum(fuga_usd) AS fuga_usd "
                "FROM v_fuga_precio GROUP BY vendedor ORDER BY 3 DESC"
            )
        ).all()
    ]
    return {
        "total_lineas": len(items),
        # Decimal(0) como inicio, no 0: con la lista vacia `sum()` devolveria un int y
        # el campo cambiaria de tipo entre "hay fuga" y "no hay". Un campo de dinero
        # es siempre un string.
        "fuga_total_usd": sum((i["fuga_usd"] or Decimal(0) for i in items), Decimal(0)),
        "por_vendedor": por_vendedor,
        "items": items,
    }


@router.get("/bajo-costo")
def ventas_bajo_costo(db: SesionDb, actual: SoloAdmin):
    """Líneas vendidas con pérdida, con el motivo que autorizó la excepción."""
    del actual
    filas = (
        db.execute(
            text(
                """
            SELECT v.codigo AS venta, v.fecha, c.nombre AS cliente, u.nombre AS vendedor,
                   i.descripcion_libre AS producto, i.cantidad, i.precio_unitario_usd,
                   i.costo_unitario_usd,
                   (i.costo_unitario_usd - i.precio_unitario_usd) * i.cantidad
                     AS perdida_usd,
                   i.motivo_desviacion
              FROM venta_items i JOIN ventas v ON v.id = i.venta_id
              JOIN clientes c ON c.id = v.cliente_id
              JOIN usuarios u ON u.id = v.vendedor_usuario_id
             WHERE i.precio_unitario_usd < i.costo_unitario_usd
             ORDER BY perdida_usd DESC, v.fecha DESC
            """
            )
        )
        .mappings()
        .all()
    )
    return [dict(f) for f in filas]


@router.get("/actividad")
def actividad(
    db: SesionDb,
    actual: SoloAdmin,
    tabla: str | None = None,
    usuario_id: int | None = None,
    solo_excepciones: bool = Query(
        default=False, description="Solo lo que lleva un motivo: la revisión de 30 segundos"
    ),
    limite: int = Query(default=100, le=500),
):
    del actual
    condiciones, params = ["TRUE"], {"limite": limite}
    if tabla:
        condiciones.append("tabla = :tabla")
        params["tabla"] = tabla
    if usuario_id:
        condiciones.append("usuario_id = :usuario")
        params["usuario"] = usuario_id
    if solo_excepciones:
        condiciones.append("motivo IS NOT NULL")

    filas = db.execute(
        text(
            f"""
            SELECT a.id, a.ocurrido_at, a.actor_tipo::text AS actor_tipo, a.usuario_id,
                   u.nombre AS usuario, a.accion::text AS accion, a.tabla, a.registro_id,
                   a.campos_cambiados, a.motivo, a.antes, a.despues
            FROM auditoria a LEFT JOIN usuarios u ON u.id = a.usuario_id
            WHERE {" AND ".join(condiciones)}
            ORDER BY a.ocurrido_at DESC LIMIT :limite
            """
        ),
        params,
    ).all()
    return [dict(f._mapping) for f in filas]
