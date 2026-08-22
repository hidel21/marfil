"""Registro de abonos. Ningun camino inventa una tasa.

Lo que cambia respecto de la app vieja:
 - **`Efectivo USD` es una ruta explicita**, no un `tasa_bcv = 1.00` metido a la
   fuerza. Esos dos registros existen en la base y contaminaban el total en bolivares
   con 28 Bs que nunca fueron bolivares.
 - **El monto en dolares lo calcula el servidor.** Si el cliente manda uno que
   difiere mas de un centavo, es un 422: es la unica forma de que el libro y la
   pantalla no puedan discrepar.
 - **El excedente se ofrece, no se rechaza.** Antes tiraba "el abono supera la deuda
   pendiente", y los clientes redondean sus transferencias para arriba.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errors import (
    CODIGO_MONTO_USD_INCONSISTENTE,
    Conflicto,
    ErrorNegocio,
    NoEncontrado,
)
from app.core.dinero import convertir_a_usd, cuantizar
from app.models.enums import CanalPago, Moneda, OrigenTasa

#: Canales que se cobran en bolivares y por lo tanto exigen tasa.
CANALES_EN_BOLIVARES = {CanalPago.PAGO_MOVIL, CanalPago.TRANSFERENCIA, CanalPago.EFECTIVO_BS}
#: Canales que se cobran en dolares o equivalente: no llevan tasa.
CANALES_EN_DIVISA = {CanalPago.EFECTIVO_USD, CanalPago.ZELLE, CanalPago.BINANCE, CanalPago.USDT}


@dataclass
class TasaResuelta:
    valor: Decimal
    origen: OrigenTasa
    tasa_id: int | None
    #: Que se le muestra al usuario sobre de donde salio.
    procedencia: str
    es_respaldo: bool = False


def resolver_tasa(
    sesion: Session,
    *,
    en_fecha: date,
    tasa_manual: Decimal | None = None,
    tasa_id: int | None = None,
) -> TasaResuelta:
    """El orden importa y no hay un camino que invente una tasa.

    El `DEFAULT_BCV_USD_RATE` hardcodeado de la app vieja **nunca** llega al libro:
    solo puede aparecer en pantalla con una insignia de "tasa de respaldo".
    """
    if tasa_id is not None:
        fila = sesion.execute(
            text("SELECT id, valor, fecha, origen::text AS origen FROM tasas_cambio WHERE id = :i"),
            {"i": tasa_id},
        ).one_or_none()
        if fila is None:
            raise NoEncontrado("esa tasa")
        return TasaResuelta(
            fila.valor, OrigenTasa(fila.origen), fila.id, f"Tasa del {fila.fecha:%d/%m/%Y}"
        )

    if tasa_manual is not None:
        if tasa_manual <= 1:
            raise ErrorNegocio(
                "TASA_INVALIDA",
                "Una tasa en bolívares tiene que ser mayor que 1.",
                campo="tasa_aplicada",
                sugerencia=(
                    "Si el pago fue en dólares en efectivo, elegí el método "
                    "'Efectivo USD': no lleva tasa."
                ),
            )
        return TasaResuelta(tasa_manual, OrigenTasa.MANUAL, None, "Tasa ingresada a mano")

    fila = sesion.execute(
        text(
            "SELECT id, valor, fecha, origen::text AS origen FROM tasas_cambio "
            "WHERE tipo = 'bcv' AND fecha <= :f ORDER BY fecha DESC LIMIT 1"
        ),
        {"f": en_fecha},
    ).one_or_none()
    if fila is None:
        raise ErrorNegocio(
            "SIN_TASA_DISPONIBLE",
            "No hay ninguna tasa BCV registrada para esa fecha.",
            campo="tasa_aplicada",
            sugerencia=(
                "Ingresá la tasa a mano o esperá el próximo snapshot automático. "
                "El sistema no inventa una tasa: es lo que hacía irreconstruible la "
                "cobranza en dólares."
            ),
        )
    vieja = (en_fecha - fila.fecha).days
    return TasaResuelta(
        fila.valor,
        OrigenTasa(fila.origen),
        fila.id,
        f"Tasa BCV del {fila.fecha:%d/%m/%Y}"
        + (f" (de hace {vieja} día(s))" if vieja else " (de hoy)"),
        es_respaldo=vieja > 1,
    )


@dataclass
class Aplicacion:
    cuota_id: int | None
    numero: int | None
    monto_usd: Decimal
    completa: bool


def registrar(
    sesion: Session,
    *,
    venta_id: int,
    fecha: date,
    canal: CanalPago,
    monto_moneda: Decimal,
    tasa_manual: Decimal | None = None,
    tasa_id: int | None = None,
    monto_usd_cliente: Decimal | None = None,
    referencia: str | None = None,
    cuota_id: int | None = None,
    notas: str | None = None,
    comprobante_url: str | None = None,
    usuario_id: int | None = None,
    permitir_excedente: bool = False,
) -> dict:
    """Registra el abono. Devuelve el pago, el saldo nuevo y como se aplico."""
    venta = sesion.execute(
        text(
            "SELECT id, codigo, total_usd, saldo_usd, cliente_id, anulada_at "
            "FROM ventas WHERE id = :i FOR UPDATE"
        ),
        {"i": venta_id},
    ).one_or_none()
    if venta is None:
        raise NoEncontrado("esa venta")
    if venta.anulada_at is not None:
        raise Conflicto("VENTA_ANULADA", "Esa venta está anulada.")
    if venta.saldo_usd <= 0:
        raise Conflicto(
            "VENTA_YA_PAGADA",
            f"La venta {venta.codigo} ya está pagada.",
            sugerencia="Si el cliente pagó de más, registrá el abono en otra venta suya.",
        )

    en_bolivares = canal in CANALES_EN_BOLIVARES
    if en_bolivares:
        tasa = resolver_tasa(sesion, en_fecha=fecha, tasa_manual=tasa_manual, tasa_id=tasa_id)
        moneda = Moneda.VES
        monto_usd = convertir_a_usd(monto_moneda, tasa.valor)
    else:
        # Sin tasa: el monto ya viene en dolares o equivalente.
        tasa = TasaResuelta(Decimal(1), OrigenTasa.MANUAL, None, "Pago en divisa, sin conversión")
        moneda = Moneda.USDT if canal == CanalPago.USDT else Moneda.USD
        monto_usd = cuantizar(monto_moneda)

    if monto_usd <= 0:
        raise ErrorNegocio(
            "MONTO_INVALIDO", "El abono tiene que ser mayor que cero.", campo="monto_moneda"
        )

    # El servidor manda. Si el cliente calculo otra cosa, es un bug de la UI y hay que
    # verlo, no arreglarlo en silencio.
    if monto_usd_cliente is not None and abs(monto_usd_cliente - monto_usd) > Decimal("0.01"):
        raise ErrorNegocio(
            CODIGO_MONTO_USD_INCONSISTENTE,
            f"El equivalente en dólares no coincide: calculé ${monto_usd} y recibí "
            f"${cuantizar(monto_usd_cliente)}.",
            detalles={
                "monto_usd_servidor": str(monto_usd),
                "monto_usd_cliente": str(cuantizar(monto_usd_cliente)),
                "tasa": str(tasa.valor),
            },
        )

    excedente = Decimal(0)
    if monto_usd > venta.saldo_usd + Decimal("0.005"):
        excedente = cuantizar(monto_usd - venta.saldo_usd)
        if not permitir_excedente:
            otras = sesion.execute(
                text(
                    "SELECT id, codigo, saldo_usd FROM ventas "
                    "WHERE cliente_id = :c AND saldo_usd > 0 AND id <> :v "
                    "ORDER BY fecha_vencimiento LIMIT 5"
                ),
                {"c": venta.cliente_id, "v": venta_id},
            ).all()
            raise ErrorNegocio(
                "ABONO_SUPERA_SALDO",
                f"El abono (${monto_usd}) supera el saldo de la venta (${venta.saldo_usd}): "
                f"sobran ${excedente}.",
                detalles={
                    "saldo": str(venta.saldo_usd),
                    "abono": str(monto_usd),
                    "excedente": str(excedente),
                    "otras_ventas": [
                        {"venta_id": o.id, "codigo": o.codigo, "saldo_usd": str(o.saldo_usd)}
                        for o in otras
                    ],
                },
                sugerencia=(
                    "Los clientes redondean para arriba. Aplicá el resto a otra venta "
                    "del mismo cliente, o confirmá para dejarlo como saldo a favor."
                ),
            )
        monto_usd = cuantizar(venta.saldo_usd)

    if cuota_id is None:
        cuota_id = sesion.execute(
            text(
                "SELECT id FROM cuotas WHERE venta_id = :v AND monto_abonado_usd < monto_usd "
                "ORDER BY numero LIMIT 1"
            ),
            {"v": venta_id},
        ).scalar()

    referencia_limpia = (referencia or "").strip() or None
    pago_id = sesion.execute(
        text(
            "INSERT INTO pagos (venta_id, cuota_id, fecha, tipo, moneda, monto_moneda, "
            "tasa_aplicada, tasa_id, origen_tasa, confianza_tasa, monto_usd, canal, "
            "referencia, comprobante_url, notas, registrado_por_usuario_id) "
            "VALUES (:v, :cuota, :f, 'abono', :moneda, :monto, :tasa, :tasa_id, :origen, "
            "'alta', :usd, :canal, :ref, :comp, :notas, :u) RETURNING id"
        ),
        {
            "v": venta_id,
            "cuota": cuota_id,
            "f": fecha,
            "moneda": moneda.value,
            "monto": cuantizar(monto_moneda),
            "tasa": tasa.valor,
            "tasa_id": tasa.tasa_id,
            "origen": tasa.origen.value,
            "usd": monto_usd,
            "canal": canal.value,
            "ref": referencia_limpia,
            "comp": comprobante_url,
            "notas": notas,
            "u": usuario_id,
        },
    ).scalar_one()

    nueva = sesion.execute(
        text(
            "SELECT saldo_usd, estado_cobro::text AS estado_cobro FROM ventas WHERE id = :i"
        ),
        {"i": venta_id},
    ).one()
    cuotas = sesion.execute(
        text(
            "SELECT id, numero, monto_usd, monto_abonado_usd FROM cuotas "
            "WHERE venta_id = :v ORDER BY numero"
        ),
        {"v": venta_id},
    ).all()

    return {
        "pago_id": pago_id,
        "monto_usd": monto_usd,
        "moneda": moneda.value,
        "monto_moneda": cuantizar(monto_moneda),
        "tasa_aplicada": tasa.valor,
        "tasa_procedencia": tasa.procedencia,
        "tasa_es_respaldo": tasa.es_respaldo,
        "saldo_usd": nueva.saldo_usd,
        "estado_cobro": nueva.estado_cobro,
        "excedente_usd": excedente,
        "cuotas": [
            {
                "cuota_id": c.id,
                "numero": c.numero,
                "monto_usd": c.monto_usd,
                "abonado_usd": c.monto_abonado_usd,
                "completa": c.monto_abonado_usd >= c.monto_usd,
            }
            for c in cuotas
        ],
    }


def reversar(
    sesion: Session, *, pago_id: int, motivo: str, usuario_id: int | None = None
) -> int:
    """Anula un pago con una fila negativa. El original no se toca.

    Es lo que permite corregir sin reescribir la historia: el trigger de
    inmutabilidad rechaza cualquier UPDATE o DELETE sobre el libro.
    """
    original = sesion.execute(
        text(
            "SELECT id, venta_id, cuota_id, moneda::text AS moneda, monto_moneda, "
            "tasa_aplicada, origen_tasa::text AS origen_tasa, monto_usd, "
            "canal::text AS canal FROM pagos WHERE id = :i AND tipo = 'abono'"
        ),
        {"i": pago_id},
    ).one_or_none()
    if original is None:
        raise NoEncontrado("ese abono")
    ya = sesion.execute(
        text("SELECT 1 FROM pagos WHERE anula_pago_id = :i"), {"i": pago_id}
    ).scalar()
    if ya:
        raise Conflicto("PAGO_YA_REVERSADO", "Ese abono ya tiene un reverso registrado.")

    return sesion.execute(
        text(
            "INSERT INTO pagos (venta_id, cuota_id, fecha, tipo, moneda, monto_moneda, "
            "tasa_aplicada, origen_tasa, monto_usd, canal, anula_pago_id, motivo, "
            "registrado_por_usuario_id) "
            "VALUES (:v, :cuota, CURRENT_DATE, 'reverso', :moneda, :monto, :tasa, :origen, "
            ":usd, :canal, :orig, :motivo, :u) RETURNING id"
        ),
        {
            "v": original.venta_id,
            "cuota": original.cuota_id,
            "moneda": original.moneda,
            "monto": original.monto_moneda,
            "tasa": original.tasa_aplicada,
            "origen": original.origen_tasa,
            "usd": -original.monto_usd,
            "canal": original.canal,
            "orig": pago_id,
            "motivo": motivo,
            "u": usuario_id,
        },
    ).scalar_one()
