"""Cobranza: quien debe, cuanto, desde cuando, y como avisarle.

Lo que cambia respecto de la app vieja: la mora se calcula **con fechas**. Antes
"moroso" significaba `deuda > 0 AND pagos = 0`, asi que una venta de ayer y otra de
hace tres meses eran lo mismo. La vista `v_cobranza` ya trae `dias_mora`, `semaforo`
y `bucket`; este modulo agrupa por cliente, porque un recordatorio va a una persona y
no a una venta: 18 ventas son 14 personas, y mandarle a alguien cuatro mensajes
separados es como se pierde un cliente.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

#: Los tramos de antiguedad, en el orden en que se muestran.
BUCKETS = ("al_dia", "1_7", "8_15", "16_30", "31_60", "mas_60")
ETIQUETAS_BUCKET = {
    "al_dia": "Al día",
    "1_7": "1–7 días",
    "8_15": "8–15 días",
    "16_30": "16–30 días",
    "31_60": "31–60 días",
    "mas_60": "+60 días",
}
#: De mas grave a menos. El peor semaforo del cliente manda.
SEMAFOROS = ("incobrable", "moroso", "vencido", "por_vencer", "al_dia")
ETIQUETAS_SEMAFORO = {
    "al_dia": "Al día",
    "por_vencer": "Por vencer",
    "vencido": "Vencido",
    "moroso": "Moroso",
    "incobrable": "Incobrable",
    "anulada": "Anulada",
}


@dataclass
class ResumenCobranza:
    deuda_total_usd: Decimal
    deuda_clientes_usd: Decimal
    deuda_socios_usd: Decimal
    clientes_con_deuda: int
    ventas_abiertas: int
    vencidas: int
    monto_vencido_usd: Decimal
    sin_telefono: int
    monto_sin_telefono_usd: Decimal
    buckets: list[dict[str, Any]]
    semaforos: list[dict[str, Any]]
    calculado_at: datetime


def resumen(sesion: Session) -> ResumenCobranza:
    """Las cifras de encabezado de la pantalla de cobranza."""
    fila = sesion.execute(
        text(
            """
            SELECT
              COALESCE(sum(saldo_usd), 0)                                   AS deuda_total,
              COALESCE(sum(saldo_usd) FILTER (WHERE NOT cliente_es_socio), 0) AS deuda_clientes,
              COALESCE(sum(saldo_usd) FILTER (WHERE cliente_es_socio), 0)     AS deuda_socios,
              count(DISTINCT cliente_id)                                    AS clientes,
              count(*)                                                      AS ventas,
              count(*) FILTER (WHERE dias_mora > 0)                         AS vencidas,
              COALESCE(sum(saldo_usd) FILTER (WHERE dias_mora > 0), 0)      AS monto_vencido,
              count(DISTINCT cliente_id) FILTER (WHERE NOT puede_notificar) AS sin_tel,
              COALESCE(sum(saldo_usd) FILTER (WHERE NOT puede_notificar), 0) AS monto_sin_tel
            FROM v_cobranza WHERE saldo_usd > 0
            """
        )
    ).one()

    por_bucket = dict(
        sesion.execute(
            text(
                "SELECT bucket, json_build_object('cantidad', count(*), 'monto', "
                "COALESCE(sum(saldo_usd), 0)) FROM v_cobranza WHERE saldo_usd > 0 GROUP BY 1"
            )
        ).all()
    )
    por_semaforo = dict(
        sesion.execute(
            text(
                "SELECT semaforo, json_build_object('cantidad', count(*), 'monto', "
                "COALESCE(sum(saldo_usd), 0)) FROM v_cobranza WHERE saldo_usd > 0 GROUP BY 1"
            )
        ).all()
    )

    return ResumenCobranza(
        deuda_total_usd=fila.deuda_total,
        deuda_clientes_usd=fila.deuda_clientes,
        deuda_socios_usd=fila.deuda_socios,
        clientes_con_deuda=fila.clientes,
        ventas_abiertas=fila.ventas,
        vencidas=fila.vencidas,
        monto_vencido_usd=fila.monto_vencido,
        sin_telefono=fila.sin_tel,
        monto_sin_telefono_usd=fila.monto_sin_tel,
        buckets=[
            {
                "clave": b,
                "etiqueta": ETIQUETAS_BUCKET[b],
                "cantidad": (por_bucket.get(b) or {}).get("cantidad", 0),
                "monto_usd": Decimal(str((por_bucket.get(b) or {}).get("monto", 0))),
            }
            for b in BUCKETS
        ],
        semaforos=[
            {
                "clave": s,
                "etiqueta": ETIQUETAS_SEMAFORO[s],
                "cantidad": (por_semaforo.get(s) or {}).get("cantidad", 0),
                "monto_usd": Decimal(str((por_semaforo.get(s) or {}).get("monto", 0))),
            }
            for s in SEMAFOROS
            if s in por_semaforo
        ],
        calculado_at=datetime.now(),
    )


def por_cliente(
    sesion: Session,
    *,
    bucket: str | None = None,
    semaforo: str | None = None,
    sin_abonos: bool | None = None,
    sin_telefono: bool | None = None,
    incluir_socios: bool = True,
    vendedor_usuario_id: int | None = None,
) -> list[dict[str, Any]]:
    """Vista por persona: es la que manda, porque el recordatorio va a una persona."""
    condiciones = ["cb.saldo_usd > 0"]
    params: dict[str, Any] = {}
    if bucket:
        condiciones.append("cb.bucket = :bucket")
        params["bucket"] = bucket
    if semaforo:
        condiciones.append("cb.semaforo = :semaforo")
        params["semaforo"] = semaforo
    if sin_abonos is not None:
        condiciones.append("cb.sin_abonos = :sin_abonos")
        params["sin_abonos"] = sin_abonos
    if sin_telefono is not None:
        condiciones.append("cb.puede_notificar = :puede")
        params["puede"] = not sin_telefono
    if not incluir_socios:
        condiciones.append("NOT cb.cliente_es_socio")
    if vendedor_usuario_id is not None:
        condiciones.append("cb.vendedor_usuario_id = :vend")
        params["vend"] = vendedor_usuario_id

    filas = sesion.execute(
        text(
            f"""
            SELECT cb.cliente_id, cb.cliente, cb.telefono_e164, cb.puede_notificar,
                   cb.cliente_es_socio,
                   count(*)                       AS ventas_abiertas,
                   sum(cb.saldo_usd)              AS deuda_usd,
                   max(cb.dias_mora)              AS dias_mora_maximo,
                   min(cb.fecha_vencimiento)      AS vencimiento_mas_viejo,
                   max(cb.ultimo_abono_fecha)     AS ultimo_abono_fecha,
                   max(cb.ultimo_recordatorio_at) AS ultimo_recordatorio_at,
                   bool_and(cb.sin_abonos)        AS nunca_abono,
                   -- El vendedor de la venta mas reciente: es a quien el cliente le
                   -- va a escribir si quiere arreglar el pago.
                   (array_agg(cb.vendedor ORDER BY cb.fecha DESC))[1] AS vendedor,
                   min(array_position(:orden ::text[], cb.semaforo)) AS peor_idx,
                   json_agg(json_build_object(
                       'venta_id', cb.venta_id, 'codigo', cb.codigo, 'fecha', cb.fecha,
                       'producto', (SELECT string_agg(i.descripcion_libre, ', ')
                                      FROM venta_items i WHERE i.venta_id = cb.venta_id),
                       'total_usd', cb.total_usd, 'saldo_usd', cb.saldo_usd,
                       'fecha_vencimiento', cb.fecha_vencimiento,
                       'dias_mora', cb.dias_mora, 'semaforo', cb.semaforo,
                       'cantidad_abonos', cb.cantidad_abonos
                   ) ORDER BY cb.fecha_vencimiento) AS ventas
            FROM v_cobranza cb
            WHERE {" AND ".join(condiciones)}
            GROUP BY cb.cliente_id, cb.cliente, cb.telefono_e164, cb.puede_notificar,
                     cb.cliente_es_socio
            ORDER BY max(cb.dias_mora) DESC, sum(cb.saldo_usd) DESC
            """
        ),
        {**params, "orden": list(SEMAFOROS)},
    ).all()

    return [
        {
            "cliente_id": f.cliente_id,
            "cliente": f.cliente,
            "telefono_e164": f.telefono_e164,
            "puede_notificar": f.puede_notificar,
            "es_socio": f.cliente_es_socio,
            "ventas_abiertas": f.ventas_abiertas,
            "deuda_usd": f.deuda_usd,
            "dias_mora_maximo": f.dias_mora_maximo,
            "vencimiento_mas_viejo": f.vencimiento_mas_viejo,
            "ultimo_abono_fecha": f.ultimo_abono_fecha,
            "ultimo_recordatorio_at": f.ultimo_recordatorio_at,
            "nunca_abono": f.nunca_abono,
            "vendedor": f.vendedor,
            "semaforo": SEMAFOROS[(f.peor_idx or len(SEMAFOROS)) - 1],
            "etiqueta_semaforo": ETIQUETAS_SEMAFORO[SEMAFOROS[(f.peor_idx or len(SEMAFOROS)) - 1]],
            "ventas": f.ventas,
        }
        for f in filas
    ]


def por_venta(
    sesion: Session,
    *,
    bucket: str | None = None,
    semaforo: str | None = None,
    solo_con_saldo: bool = True,
) -> list[dict[str, Any]]:
    condiciones = []
    params: dict[str, Any] = {}
    if solo_con_saldo:
        condiciones.append("saldo_usd > 0")
    if bucket:
        condiciones.append("bucket = :bucket")
        params["bucket"] = bucket
    if semaforo:
        condiciones.append("semaforo = :semaforo")
        params["semaforo"] = semaforo
    where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
    return [
        dict(f._mapping)
        for f in sesion.execute(
            text(
                f"SELECT * FROM v_cobranza {where} "
                "ORDER BY dias_mora DESC, saldo_usd DESC"
            ),
            params,
        ).all()
    ]


def antiguedad_de(sesion: Session, cliente_id: int, hoy: date | None = None) -> int:
    del hoy
    return (
        sesion.execute(
            text(
                "SELECT COALESCE(max(dias_mora), 0) FROM v_cobranza "
                "WHERE cliente_id = :c AND saldo_usd > 0"
            ),
            {"c": cliente_id},
        ).scalar_one()
    )
