"""Renderizado de plantillas de mensaje.

**La decision central: `{{ datos_pago }}` es una variable, no texto.**

El bug que esto cierra: la app enviaba a clientes reales los marcadores literales
`C.I.: V-XX.XXX.XXX` y `Telefono: 04XX-XXX-XXXX`, porque estaban escritos dentro del
mensaje en el codigo. Aca los datos de pago salen de la tabla `configuracion` y la
plantilla solo los invoca. Consecuencias:

- es **estructuralmente imposible** que una plantilla contenga un placeholder de pago;
- si falta un dato, **falla la generacion, no solo el envio**: nunca existe un mensaje
  renderizable con un hueco adentro;
- y al guardar se rechaza cualquier cuerpo que parezca traer datos de pago escritos a
  mano, por si alguien lo intenta igual.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from jinja2 import Environment, StrictUndefined, TemplateError, meta
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errors import CODIGO_AJUSTES_PAGO_INCOMPLETOS, ErrorNegocio
from app.core.dinero import cuantizar, formatear_bs
from app.models.parametro import CAMPOS_DATOS_PAGO_REQUERIDOS, CLAVE_DATOS_PAGO

#: Jinja2 con StrictUndefined: una variable mal escrita revienta al renderizar en vez
#: de dejar un hueco silencioso en el mensaje que el cliente va a leer.
_entorno = Environment(undefined=StrictUndefined, autoescape=False, trim_blocks=False)

ETIQUETAS_DATOS_PAGO = {
    "titular": "Titular",
    "banco": "Banco",
    "codigo_banco": "Código",
    "documento": "C.I./RIF",
    "telefono": "Teléfono",
}

#: Lo que NO puede aparecer en el cuerpo de una plantilla: son datos de pago
#: escritos a mano, que es justo lo que se esta eliminando.
PATRONES_PROHIBIDOS = (
    (re.compile(r"X{2,}"), "marcadores de relleno tipo XXX"),
    (re.compile(r"\b04\s*X", re.I), "un teléfono de relleno tipo 04XX"),
    (re.compile(r"\b[VEJPG]-?\s*X", re.I), "un documento de relleno tipo V-XX"),
    (re.compile(r"\b0(412|414|416|424|426)[\s.-]?\d{7}\b"), "un teléfono escrito a mano"),
    (re.compile(r"\b[VEJPG]-?\d{7,9}\b"), "un documento escrito a mano"),
)

#: Las variables que el sistema sabe llenar. Se validan al guardar la plantilla para
#: que nadie descubra en produccion que `{{ deuda }}` no existe.
VARIABLES_DISPONIBLES = {
    "cliente": "Nombre completo del cliente",
    "cliente_primer_nombre": "Solo el primer nombre",
    "negocio": "Nombre del negocio",
    "vendedor": "Vendedor de la venta",
    "deuda_usd": "Saldo pendiente en dólares",
    "deuda_bs": "El mismo saldo en bolívares, a la tasa del día",
    "tasa": "Tasa usada para la conversión",
    "fecha_tasa": "Fecha de esa tasa",
    "dias_mora": "Días de atraso del vencimiento más viejo",
    "fecha_vencimiento": "Vencimiento más próximo",
    "detalle_ventas": "Lista de las ventas con saldo",
    "detalle_cuotas": "Lista de las cuotas del plan",
    "cuota_actual": "Número de la cuota que toca",
    "cuotas_total": "Cantidad de cuotas del plan",
    "monto_cuota_usd": "Monto de la cuota",
    "ultimo_abono_fecha": "Fecha del último abono",
    "ultimo_abono_usd": "Monto del último abono",
    "fecha_hoy": "Fecha de hoy",
    "datos_pago": "Bloque con los datos de pago móvil, desde la configuración",
}


@dataclass(frozen=True)
class DatosPago:
    campos: dict[str, str]
    faltantes: list[str]

    @property
    def completo(self) -> bool:
        return not self.faltantes

    def como_bloque(self) -> str:
        """El texto que reemplaza a `{{ datos_pago }}`."""
        if not self.completo:
            raise ErrorNegocio(
                CODIGO_AJUSTES_PAGO_INCOMPLETOS,
                "Faltan los datos de pago: " + ", ".join(self.faltantes) + ".",
                sugerencia=(
                    "Completalos en Ajustes → Datos de pago. Hasta entonces no se puede "
                    "generar ningún recordatorio: un mensaje sin datos de cobro no sirve "
                    "y uno con datos de relleno es peor."
                ),
                detalles={"faltantes": self.faltantes},
            )
        orden = ("titular", "banco", "codigo_banco", "documento", "telefono")
        lineas = [
            f"- {ETIQUETAS_DATOS_PAGO[c]}: {self.campos[c]}"
            for c in orden
            if self.campos.get(c)
        ]
        return "\n".join(lineas)


def leer_datos_pago(sesion: Session) -> DatosPago:
    valor = sesion.execute(
        text("SELECT valor FROM configuracion WHERE clave = :k"), {"k": CLAVE_DATOS_PAGO}
    ).scalar()
    campos = {k: str(v or "").strip() for k, v in (valor or {}).items()}
    faltantes = [
        ETIQUETAS_DATOS_PAGO.get(c, c)
        for c in CAMPOS_DATOS_PAGO_REQUERIDOS
        if not campos.get(c) or re.search(r"X{2,}", campos[c].upper())
    ]
    return DatosPago(campos=campos, faltantes=faltantes)


def validar_cuerpo(cuerpo: str) -> None:
    """Se corre al guardar una plantilla. Rechaza en vez de avisar."""
    for patron, descripcion in PATRONES_PROHIBIDOS:
        if patron.search(cuerpo):
            raise ErrorNegocio(
                "PLANTILLA_CON_DATOS_DE_PAGO",
                f"El cuerpo parece traer {descripcion}.",
                campo="cuerpo",
                sugerencia=(
                    "No escribas los datos de pago en la plantilla: usá "
                    "{{ datos_pago }} y salen de la configuración. Así no puede quedar "
                    "un dato viejo o de relleno en un mensaje que ya se envió."
                ),
            )

    try:
        arbol = _entorno.parse(cuerpo)
    except TemplateError as exc:
        raise ErrorNegocio(
            "PLANTILLA_INVALIDA", f"La plantilla no se puede leer: {exc}", campo="cuerpo"
        ) from exc

    desconocidas = sorted(meta.find_undeclared_variables(arbol) - set(VARIABLES_DISPONIBLES))
    if desconocidas:
        sugerencias = []
        for v in desconocidas:
            parecidas = [d for d in VARIABLES_DISPONIBLES if v in d or d in v]
            if parecidas:
                sugerencias.append(f"{{{{ {v} }}}} no existe, ¿quisiste {{{{ {parecidas[0]} }}}}?")
        raise ErrorNegocio(
            "PLANTILLA_VARIABLE_DESCONOCIDA",
            "La plantilla usa variables que el sistema no sabe llenar: "
            + ", ".join(desconocidas)
            + ".",
            campo="cuerpo",
            detalles={"desconocidas": desconocidas, "disponibles": sorted(VARIABLES_DISPONIBLES)},
            sugerencia=" ".join(sugerencias) if sugerencias else None,
        )


def _primer_nombre(nombre: str) -> str:
    partes = (nombre or "").split()
    return partes[0] if partes else nombre


def _fecha(valor: Any, formato: str = "%d/%m/%Y") -> str:
    """Formatea una fecha que puede venir como date o como string.

    Las ventas de un cliente llegan desde un `json_agg` de Postgres, asi que las
    fechas son strings ISO. Aceptar las dos formas evita que el renderizado del
    mensaje dependa de por donde entro el dato.
    """
    if valor is None or valor == "":
        return "—"
    if isinstance(valor, str):
        try:
            valor = date.fromisoformat(valor[:10])
        except ValueError:
            return valor
    return format(valor, formato)


def contexto_cobranza(
    sesion: Session,
    *,
    nombre_cliente: str,
    ventas: list[dict[str, Any]],
    tasa: Decimal | None,
    fecha_tasa: date | None,
    nombre_negocio: str,
    vendedor: str = "",
    ultimo_abono_fecha: Any = None,
) -> dict[str, Any]:
    """Arma las variables de un recordatorio de cobranza.

    Recibe los datos suelto y no un dict del cliente a proposito: asi el contrato es
    explicito y no depende de como se llame la clave en la consulta que lo alimenta.
    """
    deuda_usd = cuantizar(sum(Decimal(str(v["saldo_usd"])) for v in ventas))
    dias_mora = max((int(v.get("dias_mora") or 0) for v in ventas), default=0)
    vencimientos = sorted(
        _fecha(v["fecha_vencimiento"], "%Y-%m-%d") for v in ventas if v.get("fecha_vencimiento")
    )

    def _linea(v: dict[str, Any]) -> str:
        texto = f"• {v.get('producto') or 'venta'} — ${cuantizar(v['saldo_usd'])}"
        if v.get("dias_mora"):
            texto += f" — venció el {_fecha(v['fecha_vencimiento'], '%d/%m')} ({v['dias_mora']} d)"
        elif v.get("fecha_vencimiento"):
            texto += f" — vence el {_fecha(v['fecha_vencimiento'], '%d/%m')}"
        return texto

    detalle = "\n".join(_linea(v) for v in ventas)

    return {
        "cliente": nombre_cliente,
        "cliente_primer_nombre": _primer_nombre(nombre_cliente),
        "negocio": nombre_negocio,
        "vendedor": vendedor or "",
        "deuda_usd": f"{deuda_usd:,.2f}",
        "deuda_bs": formatear_bs(deuda_usd * tasa).removeprefix("Bs. ") if tasa else "—",
        "tasa": f"{tasa:,.2f}" if tasa else "—",
        "fecha_tasa": _fecha(fecha_tasa),
        "dias_mora": dias_mora,
        "fecha_vencimiento": _fecha(vencimientos[0]) if vencimientos else "—",
        "detalle_ventas": detalle,
        "detalle_cuotas": "",
        "cuota_actual": "",
        "cuotas_total": "",
        "monto_cuota_usd": "",
        "ultimo_abono_fecha": _fecha(ultimo_abono_fecha),
        "ultimo_abono_usd": "",
        "fecha_hoy": f"{date.today():%d/%m/%Y}",
        "datos_pago": leer_datos_pago(sesion).como_bloque(),
    }


def renderizar(cuerpo: str, contexto: dict[str, Any]) -> str:
    """Renderiza y normaliza los saltos de linea.

    Colapsa tres o mas saltos seguidos: las plantillas con condicionales de Jinja
    dejan huecos, y un mensaje de WhatsApp con lineas vacias de sobra se ve
    descuidado.
    """
    try:
        texto = _entorno.from_string(cuerpo).render(**contexto)
    except TemplateError as exc:
        raise ErrorNegocio(
            "PLANTILLA_NO_RENDERIZA",
            f"No se pudo armar el mensaje: {exc}",
            sugerencia="Revisá la plantilla en Ajustes → Plantillas.",
        ) from exc
    return re.sub(r"\n{3,}", "\n\n", texto).strip()
