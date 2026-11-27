"""La caja: cuanto dinero tiene el negocio y por que movimiento llego a eso.

Todo sale de `v_caja_movimientos` (revision 0016), que lee cobros, gastos y pagos a
proveedor de sus propios libros. Aca solo se calcula el saldo acumulado y se
administran los movimientos que no tienen otro libro: aportes, retiros y ajustes.

El saldo corrido se calcula sobre la historia completa y despues se filtra el
periodo. Al reves, el saldo de la primera fila del periodo arrancaria en cero.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errors import Conflicto, ErrorNegocio, NoEncontrado

TIPOS_MANUALES = ("aporte", "retiro", "ajuste")

#: Orden estable para el saldo corrido: dentro del mismo dia, en el orden en que se
#: cargaron. Sin `origen_id` dos filas con el mismo `created_at` (una importacion
#: entera comparte el instante de su transaccion) podrian intercambiarse entre una
#: consulta y otra, y el saldo de cada una "bailaria".
_ORDEN = "fecha, created_at, origen, origen_id"


def _saldo_hasta(sesion: Session, fecha: date | None, *, antes: bool) -> Decimal:
    if fecha is None:
        return sesion.execute(
            text("SELECT COALESCE(sum(monto_usd), 0) FROM v_caja_movimientos")
        ).scalar_one()
    operador = "<" if antes else "<="
    return sesion.execute(
        text(
            "SELECT COALESCE(sum(monto_usd), 0) FROM v_caja_movimientos "
            f"WHERE fecha {operador} :f"
        ),
        {"f": fecha},
    ).scalar_one()


def resumen(
    sesion: Session,
    *,
    desde: date | None = None,
    hasta: date | None = None,
    limite: int = 500,
) -> dict:
    if desde and hasta and desde > hasta:
        raise ErrorNegocio("PERIODO_INVALIDO", "La fecha inicial es posterior a la final.")

    condiciones, params = ["TRUE"], {"limite": limite}
    if desde:
        condiciones.append("fecha >= :desde")
        params["desde"] = desde
    if hasta:
        condiciones.append("fecha <= :hasta")
        params["hasta"] = hasta
    donde = " AND ".join(condiciones)

    movimientos = (
        sesion.execute(
            text(
                f"""
                WITH corrido AS (
                  SELECT *, sum(monto_usd) OVER (ORDER BY {_ORDEN}) AS saldo_usd,
                         row_number() OVER (ORDER BY {_ORDEN}) AS orden
                    FROM v_caja_movimientos
                )
                SELECT origen, origen_id, fecha, tipo, concepto, detalle, canal, moneda,
                       monto_moneda, monto_usd, saldo_usd
                  FROM corrido WHERE {donde}
                 ORDER BY orden DESC LIMIT :limite
                """
            ),
            params,
        )
        .mappings()
        .all()
    )

    # Entradas y salidas por la NATURALEZA del movimiento, no por su signo. Un reverso
    # de cobro es negativo, pero no es plata que salio: es un cobro que no fue (o que
    # estaba mal convertido). Contado como salida, un mes con correcciones mostraria
    # entradas y salidas infladas por el mismo monto. Va restando de las entradas.
    totales = (
        sesion.execute(
            text(
                f"""
                SELECT COALESCE(sum(monto_usd) FILTER (
                         WHERE tipo IN ('cobro', 'reverso_cobro', 'aporte')
                            OR (tipo = 'ajuste' AND monto_usd > 0)), 0) AS entradas_usd,
                       COALESCE(-sum(monto_usd) FILTER (
                         WHERE tipo IN ('gasto', 'compra', 'retiro')
                            OR (tipo = 'ajuste' AND monto_usd < 0)), 0) AS salidas_usd,
                       count(*) AS movimientos
                  FROM v_caja_movimientos WHERE {donde}
                """
            ),
            params,
        )
        .mappings()
        .one()
    )
    # Por la misma razon, cobros y reversos van en una sola linea: lo cobrado neto.
    por_tipo = (
        sesion.execute(
            text(
                f"""
                SELECT CASE WHEN tipo = 'reverso_cobro' THEN 'cobro' ELSE tipo END AS tipo,
                       count(*) FILTER (WHERE tipo <> 'reverso_cobro') AS movimientos,
                       sum(monto_usd) AS monto_usd
                  FROM v_caja_movimientos WHERE {donde}
                 GROUP BY 1 ORDER BY sum(monto_usd) DESC
                """
            ),
            params,
        )
        .mappings()
        .all()
    )
    # Lo que cada socio puso y saco por caja, de toda la historia. Es informativo: el
    # capital del reparto (`socios.capital_invertido`) lo siguen fijando los socios.
    por_socio = (
        sesion.execute(
            text(
                """
                SELECT s.id, s.nombre,
                       COALESCE(sum(m.monto_usd) FILTER (WHERE m.tipo = 'aporte'), 0)
                         AS aportado_usd,
                       COALESCE(-sum(m.monto_usd) FILTER (WHERE m.tipo = 'retiro'), 0)
                         AS retirado_usd
                  FROM socios s
                  LEFT JOIN movimientos_caja m
                         ON m.socio_id = s.id AND m.anulado_at IS NULL
                 GROUP BY s.id ORDER BY s.id
                """
            )
        )
        .mappings()
        .all()
    )

    return {
        "saldo_actual_usd": _saldo_hasta(sesion, None, antes=False),
        "periodo": {
            "desde": desde,
            "hasta": hasta,
            "saldo_inicial_usd": _saldo_hasta(sesion, desde, antes=True) if desde else Decimal(0),
            "saldo_final_usd": _saldo_hasta(sesion, hasta, antes=False),
            "entradas_usd": totales["entradas_usd"],
            "salidas_usd": totales["salidas_usd"],
            "movimientos": totales["movimientos"],
        },
        "por_tipo": [dict(f) for f in por_tipo],
        "por_socio": [dict(f) for f in por_socio],
        "movimientos": [dict(f) for f in movimientos],
        "truncado": totales["movimientos"] > len(movimientos),
    }


def registrar(
    sesion: Session,
    *,
    fecha: date,
    tipo: str,
    monto_usd: Decimal,
    concepto: str,
    sentido: str | None = None,
    socio_id: int | None = None,
    canal: str | None = None,
    notas: str | None = None,
    usuario_id: int | None = None,
) -> int:
    """Un aporte, un retiro o un ajuste. `monto_usd` llega siempre positivo."""
    if tipo not in TIPOS_MANUALES:
        raise ErrorNegocio(
            "TIPO_INVALIDO", f"Tipo de movimiento desconocido: {tipo!r}.", campo="tipo"
        )
    if monto_usd <= 0:
        raise ErrorNegocio(
            "MONTO_INVALIDO", "El monto tiene que ser mayor que cero.", campo="monto_usd"
        )
    if fecha > date.today():
        raise ErrorNegocio(
            "FECHA_FUTURA",
            "La caja registra lo que ya pasó: la fecha no puede ser posterior a hoy.",
            campo="fecha",
        )
    if tipo in ("aporte", "retiro"):
        if socio_id is None:
            raise ErrorNegocio(
                "FALTA_SOCIO", f"Un {tipo} es de un socio: indicá de cuál.", campo="socio_id"
            )
        existe = sesion.execute(
            text("SELECT 1 FROM socios WHERE id = :i"), {"i": socio_id}
        ).scalar()
        if not existe:
            raise NoEncontrado("ese socio")
        signo = 1 if tipo == "aporte" else -1
    else:
        if sentido not in ("entrada", "salida"):
            raise ErrorNegocio(
                "FALTA_SENTIDO",
                "Un ajuste puede sumar o restar: indicá si es entrada o salida.",
                campo="sentido",
            )
        signo = 1 if sentido == "entrada" else -1

    return sesion.execute(
        text(
            """
            INSERT INTO movimientos_caja
              (fecha, tipo, monto_usd, socio_id, concepto, canal, notas, creado_por_usuario_id)
            VALUES (:fecha, :tipo, :monto, :socio, :concepto, :canal, :notas, :usuario)
            RETURNING id
            """
        ),
        {
            "fecha": fecha,
            "tipo": tipo,
            "monto": signo * monto_usd,
            "socio": socio_id,
            "concepto": concepto.strip(),
            "canal": canal,
            "notas": (notas or "").strip() or None,
            "usuario": usuario_id,
        },
    ).scalar_one()


def anular(sesion: Session, *, movimiento_id: int, motivo: str, usuario_id: int | None) -> None:
    """Deja de contar, pero queda: con quién lo anuló, cuándo y por qué."""
    fila = sesion.execute(
        text("SELECT anulado_at FROM movimientos_caja WHERE id = :i FOR UPDATE"),
        {"i": movimiento_id},
    ).one_or_none()
    if fila is None:
        raise NoEncontrado("ese movimiento de caja")
    if fila.anulado_at is not None:
        raise Conflicto("YA_ANULADO", "Ese movimiento ya estaba anulado.")
    sesion.execute(
        text(
            "UPDATE movimientos_caja SET anulado_at = now(), anulado_por_usuario_id = :u, "
            "motivo_anulacion = :m WHERE id = :i"
        ),
        {"u": usuario_id, "m": motivo.strip(), "i": movimiento_id},
    )
