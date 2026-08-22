"""Generacion de recordatorios de cobranza.

Tres garantias, y cada una vive donde no se puede evitar:

1. **Nadie recibe dos recordatorios de la misma venta el mismo dia**: es el indice
   unico `uq_recordatorios_dia`, en la base. Un segundo intento es un 23505 haga lo
   que haga quien llame. El cooldown mas blando (`DIAS_ENTRE_RECORDATORIOS`) se
   comprueba aca; el indice es la red.

2. **Sin datos de pago no se genera nada.** Falla la generacion, no el envio: nunca
   existe un mensaje renderizable con un hueco donde deberian ir los datos de cobro.

3. **El cuerpo se congela al generar.** Editar la plantilla despues no puede dejarte
   sin poder probar que se le dijo al cliente: una discusion se responde con "este es
   literalmente el mensaje que enviamos el 14/08".

El cooldown se devuelve como omision con motivo, no como error: un lote de 12 tiene
que decir "9 listos, 2 en cooldown, 1 sin telefono" y no fallar entero por uno.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.integrations.notificaciones.base import Accion, obtener_proveedor
from app.models.parametro import CLAVE_NOMBRE_NEGOCIO, CLAVE_PROVEEDOR_NOTIFICACIONES
from app.models.recordatorio import (
    TIPO_MOROSO,
    TIPO_POR_VENCER,
    TIPO_VENCIDO,
)
from app.services import cobranza as svc_cobranza
from app.services.parametros import entero
from app.services.plantillas import contexto_cobranza, leer_datos_pago, renderizar

MOTIVOS = {
    "cooldown": "Ya se le escribió hace poco",
    "sin_telefono": "No tiene teléfono cargado",
    "ya_pagado": "Ya no debe nada",
    "limite_mensual": "Alcanzó el máximo de recordatorios del mes",
}


@dataclass
class Omitido:
    cliente_id: int
    cliente: str
    motivo: str
    detalle: str
    #: Un admin puede forzar; el vendedor no.
    forzable: bool = True


@dataclass
class Preparado:
    cliente_id: int
    cliente: str
    telefono_e164: str | None
    plantilla_clave: str
    cuerpo: str
    deuda_usd: Decimal
    dias_mora: int
    ventas: list[int]
    accion: Accion
    avisos: list[str] = field(default_factory=list)


@dataclass
class ResultadoLote:
    preparados: list[Preparado] = field(default_factory=list)
    omitidos: list[Omitido] = field(default_factory=list)

    @property
    def resumen(self) -> str:
        partes = [f"{len(self.preparados)} listos"]
        por_motivo: dict[str, int] = {}
        for o in self.omitidos:
            por_motivo[o.motivo] = por_motivo.get(o.motivo, 0) + 1
        for motivo, n in por_motivo.items():
            partes.append(f"{n} {MOTIVOS.get(motivo, motivo).lower()}")
        return " · ".join(partes)


def _config(sesion: Session, clave: str, defecto: str) -> str:
    valor = sesion.execute(
        text("SELECT valor FROM configuracion WHERE clave = :k"), {"k": clave}
    ).scalar()
    if isinstance(valor, dict):
        return str(valor.get("valor") or defecto)
    return defecto


def plantilla_para(semaforo: str) -> str:
    """Que plantilla corresponde segun el estado. Un moroso no se saluda igual."""
    return {
        "por_vencer": TIPO_POR_VENCER,
        "vencido": TIPO_VENCIDO,
        "moroso": TIPO_MOROSO,
        "incobrable": TIPO_MOROSO,
    }.get(semaforo, TIPO_VENCIDO)


def _tasa_del_dia(sesion: Session) -> tuple[Decimal | None, Any]:
    fila = sesion.execute(
        text(
            "SELECT valor, fecha FROM tasas_cambio WHERE tipo = 'bcv' "
            "ORDER BY fecha DESC LIMIT 1"
        )
    ).one_or_none()
    return (fila.valor, fila.fecha) if fila else (None, None)


def _ultimo_recordatorio(sesion: Session, cliente_id: int) -> datetime | None:
    return sesion.execute(
        text(
            "SELECT max(generado_at) FROM recordatorios "
            "WHERE cliente_id = :c AND estado <> 'omitido'"
        ),
        {"c": cliente_id},
    ).scalar()


def _cuenta_del_mes(sesion: Session, venta_ids: list[int]) -> int:
    if not venta_ids:
        return 0
    return sesion.execute(
        text(
            "SELECT count(*) FROM recordatorios "
            "WHERE venta_id = ANY(:v) AND estado <> 'omitido' "
            "AND generado_at >= date_trunc('month', now())"
        ),
        {"v": venta_ids},
    ).scalar_one()


def preparar_lote(
    sesion: Session,
    *,
    cliente_ids: list[int] | None = None,
    plantilla_clave: str | None = None,
    incluir_socios: bool = False,
    forzar: bool = False,
) -> ResultadoLote:
    """Arma los mensajes sin escribir nada. Es el preview del lote.

    `incluir_socios=False` por defecto: mandarle un recordatorio de cobranza a un
    socio por su propio autoconsumo es ruido.
    """
    # Se valida una sola vez, al principio: si faltan los datos de pago no hay lote.
    leer_datos_pago(sesion).como_bloque()

    negocio = _config(sesion, CLAVE_NOMBRE_NEGOCIO, "Sistema Marfil")
    proveedor = obtener_proveedor(_config(sesion, CLAVE_PROVEEDOR_NOTIFICACIONES, None))
    dias_cooldown = entero(sesion, "DIAS_ENTRE_RECORDATORIOS")
    max_mes = entero(sesion, "MAX_RECORDATORIOS_POR_VENTA_MES")
    tasa, fecha_tasa = _tasa_del_dia(sesion)

    clientes = svc_cobranza.por_cliente(sesion, incluir_socios=incluir_socios)
    if cliente_ids is not None:
        elegidos = set(cliente_ids)
        clientes = [c for c in clientes if c["cliente_id"] in elegidos]

    resultado = ResultadoLote()
    for c in clientes:
        venta_ids = [v["venta_id"] for v in c["ventas"]]

        if not c["puede_notificar"]:
            resultado.omitidos.append(
                Omitido(
                    c["cliente_id"],
                    c["cliente"],
                    "sin_telefono",
                    f"Debe ${c['deuda_usd']} y no hay número para avisarle.",
                    forzable=False,
                )
            )
            continue

        if not forzar:
            ultimo = _ultimo_recordatorio(sesion, c["cliente_id"])
            if ultimo and (datetime.now(ultimo.tzinfo) - ultimo).days < dias_cooldown:
                dias = (datetime.now(ultimo.tzinfo) - ultimo).days
                resultado.omitidos.append(
                    Omitido(
                        c["cliente_id"],
                        c["cliente"],
                        "cooldown",
                        f"Se le escribió hace {dias} día(s); el mínimo es {dias_cooldown}.",
                    )
                )
                continue
            if _cuenta_del_mes(sesion, venta_ids) >= max_mes:
                resultado.omitidos.append(
                    Omitido(
                        c["cliente_id"],
                        c["cliente"],
                        "limite_mensual",
                        f"Ya se le enviaron {max_mes} este mes.",
                    )
                )
                continue

        clave = plantilla_clave or plantilla_para(c["semaforo"])
        plantilla = sesion.execute(
            text(
                "SELECT clave, version, cuerpo FROM plantillas_mensaje "
                "WHERE clave = :k AND activa"
            ),
            {"k": clave},
        ).one_or_none()
        if plantilla is None:
            resultado.omitidos.append(
                Omitido(
                    c["cliente_id"],
                    c["cliente"],
                    "sin_plantilla",
                    f"No hay una plantilla activa '{clave}'.",
                    forzable=False,
                )
            )
            continue

        contexto = contexto_cobranza(
            sesion,
            nombre_cliente=c["cliente"],
            ventas=c["ventas"],
            tasa=tasa,
            fecha_tasa=fecha_tasa,
            nombre_negocio=negocio,
            vendedor=c.get("vendedor") or "",
            ultimo_abono_fecha=c.get("ultimo_abono_fecha"),
        )
        cuerpo = renderizar(plantilla.cuerpo, contexto)
        preparado = proveedor.preparar(telefono_e164=c["telefono_e164"], cuerpo=cuerpo)

        resultado.preparados.append(
            Preparado(
                cliente_id=c["cliente_id"],
                cliente=c["cliente"],
                telefono_e164=c["telefono_e164"],
                plantilla_clave=plantilla.clave,
                cuerpo=cuerpo,
                deuda_usd=c["deuda_usd"],
                dias_mora=c["dias_mora_maximo"] or 0,
                ventas=venta_ids,
                accion=preparado.accion,
                avisos=preparado.avisos,
            )
        )
    return resultado


def registrar(
    sesion: Session,
    preparado: Preparado,
    *,
    usuario_id: int | None,
    tasa: Decimal | None = None,
) -> int:
    """Guarda el recordatorio con el cuerpo congelado. Devuelve su id.

    Se escribe una fila **por venta**: es lo que hace que el indice unico por dia
    funcione y que el historial de una venta sea completo. El mensaje es uno solo.
    """
    if tasa is None:
        tasa, _ = _tasa_del_dia(sesion)
    plantilla_version = sesion.execute(
        text("SELECT version FROM plantillas_mensaje WHERE clave = :k"),
        {"k": preparado.plantilla_clave},
    ).scalar_one()

    primer_id: int | None = None
    for venta_id in preparado.ventas or [None]:
        nuevo = sesion.execute(
            text(
                "INSERT INTO recordatorios (cliente_id, venta_id, ventas_incluidas, canal, "
                "plantilla_clave, plantilla_version, cuerpo_renderizado, destino, "
                "saldo_usd_al_generar, tasa_al_generar, dias_mora_al_generar, estado, "
                "generado_por_usuario_id) "
                "VALUES (:cliente, :venta, :ventas, 'whatsapp_manual', :plantilla, :version, "
                ":cuerpo, :destino, :saldo, :tasa, :dias, 'listo', :usuario) RETURNING id"
            ),
            {
                "cliente": preparado.cliente_id,
                "venta": venta_id,
                "ventas": preparado.ventas,
                "plantilla": preparado.plantilla_clave,
                "version": plantilla_version,
                "cuerpo": preparado.cuerpo,
                "destino": preparado.telefono_e164,
                "saldo": preparado.deuda_usd,
                "tasa": tasa,
                "dias": preparado.dias_mora,
                "usuario": usuario_id,
            },
        ).scalar_one()
        primer_id = primer_id or nuevo
    return primer_id or 0


def marcar_enviado(sesion: Session, recordatorio_id: int, *, usuario_id: int | None) -> None:
    """Un deep link no confirma entrega: esto registra que un humano lo despacho."""
    sesion.execute(
        text(
            "UPDATE recordatorios SET estado = 'enviado', enviado_at = now(), "
            "marcado_enviado_por_usuario_id = :u, proveedor = 'whatsapp_manual' "
            "WHERE id = :i AND estado IN ('borrador', 'listo')"
        ),
        {"i": recordatorio_id, "u": usuario_id},
    )
