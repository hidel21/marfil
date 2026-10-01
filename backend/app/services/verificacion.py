"""Verificacion bancaria de los abonos: confirmar que la plata llego.

Tres estados, derivados y no guardados en `pagos` (ver la revision 0015):

- **pendiente**: un abono vivo sin fila en `verificaciones_pago`;
- **confirmado**: alguien lo comparo contra el banco y llego;
- **rechazado**: no llego. Se reversa en la misma transaccion, con la fecha del
  abono original, y la deuda del cliente vuelve.

Los reversos no se verifican: no son plata que entra, son correcciones de una que ya
se verifico (o no). Un abono reversado por otro camino tampoco queda pendiente: ya no
cuenta para nada.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errors import Conflicto, ErrorNegocio, NoEncontrado
from app.services import pagos as pagos_svc

ESTADOS = ("pendiente", "confirmado", "rechazado")

#: Un abono "vivo": no es un reverso y nadie lo reverso.
_VIVO = (
    "p.tipo = 'abono' AND NOT EXISTS (SELECT 1 FROM pagos r WHERE r.anula_pago_id = p.id)"
)


def listar(sesion: Session, *, estado: str = "pendiente", limite: int = 200) -> list[dict]:
    if estado not in ESTADOS:
        raise ErrorNegocio("ESTADO_INVALIDO", f"Estado desconocido: {estado!r}.")
    if estado == "pendiente":
        filtro = f"{_VIVO} AND vp.id IS NULL"
    elif estado == "confirmado":
        filtro = "vp.estado = 'confirmado'"
    else:
        filtro = "vp.estado = 'rechazado'"
    filas = sesion.execute(
        text(
            f"""
            SELECT p.id, p.fecha, v.id AS venta_id, v.codigo AS venta, c.nombre AS cliente,
                   p.canal::text AS canal, p.referencia, p.moneda::text AS moneda,
                   p.monto_moneda, p.tasa_aplicada, p.monto_usd, p.notas,
                   ur.nombre AS registrado_por, p.created_at AS registrado_at,
                   COALESCE(vp.estado, 'pendiente') AS estado,
                   uv.nombre AS verificado_por, vp.verificado_at, vp.nota AS nota_verificacion
              FROM pagos p
              JOIN ventas v ON v.id = p.venta_id
              JOIN clientes c ON c.id = v.cliente_id
              LEFT JOIN verificaciones_pago vp ON vp.pago_id = p.id
              LEFT JOIN usuarios ur ON ur.id = p.registrado_por_usuario_id
              LEFT JOIN usuarios uv ON uv.id = vp.usuario_id
             WHERE {filtro}
             ORDER BY p.fecha DESC, p.id DESC
             LIMIT :limite
            """
        ),
        {"limite": limite},
    ).all()
    return [dict(f._mapping) for f in filas]


def resumen(sesion: Session) -> dict:
    fila = sesion.execute(
        text(
            f"""
            SELECT count(*) AS cantidad, COALESCE(sum(p.monto_usd), 0) AS monto_usd
              FROM pagos p LEFT JOIN verificaciones_pago vp ON vp.pago_id = p.id
             WHERE {_VIVO} AND vp.id IS NULL
            """
        )
    ).one()
    return {"pendientes": fila.cantidad, "pendientes_usd": fila.monto_usd}


def _verificable(sesion: Session, pago_id: int):
    pago = sesion.execute(
        text(
            f"""
            SELECT p.id, p.fecha, ({_VIVO}) AS vivo, p.tipo::text AS tipo,
                   (SELECT estado FROM verificaciones_pago WHERE pago_id = p.id) AS estado
              FROM pagos p WHERE p.id = :i FOR UPDATE
            """
        ),
        {"i": pago_id},
    ).one_or_none()
    if pago is None:
        raise NoEncontrado("ese pago")
    if pago.tipo != "abono":
        raise ErrorNegocio("NO_VERIFICABLE", "Un reverso no se verifica: no es plata que entra.")
    if pago.estado is not None:
        raise Conflicto(
            "PAGO_YA_VERIFICADO", f"El pago #{pago_id} ya estaba {pago.estado}."
        )
    if not pago.vivo:
        raise Conflicto(
            "PAGO_REVERSADO", f"El pago #{pago_id} ya fue reversado: no hay nada que verificar."
        )
    return pago


def confirmar(
    sesion: Session, *, pago_ids: list[int], usuario_id: int, nota: str | None = None
) -> int:
    """Confirma uno o varios. Todo o nada: si uno no se puede, no se confirma ninguno.

    Confirmar a medias un lote obligaria a quien confirma a averiguar cuales entraron.
    """
    for pago_id in pago_ids:
        _verificable(sesion, pago_id)
    for pago_id in pago_ids:
        sesion.execute(
            text(
                "INSERT INTO verificaciones_pago (pago_id, estado, usuario_id, nota) "
                "VALUES (:p, 'confirmado', :u, :n)"
            ),
            {"p": pago_id, "u": usuario_id, "n": nota},
        )
    return len(pago_ids)


def rechazar(sesion: Session, *, pago_id: int, usuario_id: int, motivo: str) -> int:
    """El pago no llego: se reversa con su fecha original y queda el rechazo escrito.

    Fecha original y no la de hoy: un pago que nunca existio es un error de carga, no
    una devolucion. Con la de hoy, las finanzas mostrarian un cobro en el mes del pago
    y una devolucion en el mes de la revision, y ninguna de las dos ocurrio.
    """
    pago = _verificable(sesion, pago_id)
    reverso_id = pagos_svc.reversar(
        sesion,
        pago_id=pago_id,
        motivo=f"Rechazado en la verificación bancaria: {motivo}"[:500],
        usuario_id=usuario_id,
        fecha=pago.fecha,
    )
    sesion.execute(
        text(
            "INSERT INTO verificaciones_pago (pago_id, estado, usuario_id, nota) "
            "VALUES (:p, 'rechazado', :u, :n)"
        ),
        {"p": pago_id, "u": usuario_id, "n": motivo},
    )
    return reverso_id
