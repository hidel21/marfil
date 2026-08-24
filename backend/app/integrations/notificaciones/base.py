"""La costura del proveedor de notificaciones.

Hoy no hay integracion con WhatsApp, asi que el sistema genera el mensaje y un link
`wa.me` que un socio abre y envia. Manana puede haber WhatsApp Cloud API o Twilio.

El diseno esta hecho para que ese cambio sea **una fila de configuracion**, no una
migracion mas una reescritura de la UI:

- `estado` en la tabla es el ciclo de vida completo (BORRADOR..LEIDO) aunque el
  proveedor manual solo llegue a ENVIADO;
- `proveedor` y `proveedor_mensaje_id` son columnas nulables desde el dia uno;
- y cada recordatorio viaja con una `accion` que dice **como** enviarlo, asi la UI
  tiene un solo componente que decide entre renderizar un `<a>` o disparar una
  mutacion. Todo lo demas —cola, lote, historial, cooldown, plantillas— es agnostico.

Un deep link no puede confirmar entrega, y la interfaz lo dice: `soporta_entrega` es
False para el proveedor manual, y por eso la UI rotula la columna "Entregado a
WhatsApp" y no "Entregado".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol
from urllib.parse import quote

from app.api.errors import CODIGO_CLIENTE_SIN_TELEFONO, ErrorNegocio


@dataclass(frozen=True)
class Capacidades:
    #: El proveedor envia por su cuenta (no hace falta que un humano clickee).
    envio_automatico: bool
    #: Puede confirmar que el mensaje llego.
    soporta_entrega: bool
    #: Exige plantillas aprobadas por Meta antes de poder mandar.
    exige_plantilla_aprobada: bool


@dataclass(frozen=True)
class Accion:
    """Como se entrega este mensaje. Lo consume un unico componente del frontend."""

    tipo: Literal["DEEP_LINK", "ENVIO_SERVIDOR"]
    url: str | None = None


@dataclass(frozen=True)
class Resultado:
    accion: Accion
    #: `enviado` solo cuando el proveedor confirma haber despachado.
    estado: Literal["listo", "enviado", "fallido"]
    proveedor: str
    proveedor_mensaje_id: str | None = None
    error: str | None = None
    avisos: list[str] = field(default_factory=list)


class ProveedorNotificaciones(Protocol):
    nombre: str

    def capacidades(self) -> Capacidades: ...

    def preparar(self, *, telefono_e164: str | None, cuerpo: str) -> Resultado: ...


class ProveedorWhatsAppManual:
    """El que se usa hoy: arma el link y deja el envio a un humano.

    Diferencia clave con la app vieja: el link **lleva el numero del cliente**. Antes
    era `wa.me/?text=...` sin destinatario, asi que abria WhatsApp sin saber a quien
    escribirle.
    """

    nombre = "whatsapp_manual"

    def capacidades(self) -> Capacidades:
        return Capacidades(
            envio_automatico=False, soporta_entrega=False, exige_plantilla_aprobada=False
        )

    def preparar(self, *, telefono_e164: str | None, cuerpo: str) -> Resultado:
        if not telefono_e164:
            raise ErrorNegocio(
                CODIGO_CLIENTE_SIN_TELEFONO,
                "Ese cliente no tiene teléfono cargado.",
                campo="telefono_e164",
                sugerencia=(
                    "Cargalo en la ficha del cliente. Un recordatorio que no se puede "
                    "entregar es una tarea pendiente, no un mensaje enviado."
                ),
            )
        # wa.me quiere el numero sin '+'.
        numero = telefono_e164.lstrip("+")
        url = f"https://wa.me/{numero}?text={quote(cuerpo, safe='')}"
        return Resultado(
            accion=Accion(tipo="DEEP_LINK", url=url),
            estado="listo",
            proveedor=self.nombre,
            avisos=[
                "El envío lo hace una persona: al abrir el link, WhatsApp queda con el "
                "mensaje escrito y hay que apretar enviar."
            ],
        )


class ProveedorWhatsAppApi:
    """El punto de enchufe. Existe para que el cambio sea configuracion, no codigo nuevo."""

    nombre = "whatsapp_api"

    def capacidades(self) -> Capacidades:
        return Capacidades(
            envio_automatico=True, soporta_entrega=True, exige_plantilla_aprobada=True
        )

    def preparar(self, *, telefono_e164: str | None, cuerpo: str) -> Resultado:
        raise ErrorNegocio(
            "PROVEEDOR_NO_CONFIGURADO",
            "La integración con la API de WhatsApp todavía no está conectada.",
            sugerencia=(
                "Mientras tanto, dejá el proveedor en 'whatsapp_manual' en Ajustes: el "
                "sistema arma el mensaje y ustedes lo envían con un clic."
            ),
        )


PROVEEDORES: dict[str, type] = {
    ProveedorWhatsAppManual.nombre: ProveedorWhatsAppManual,
    ProveedorWhatsAppApi.nombre: ProveedorWhatsAppApi,
}


def obtener_proveedor(nombre: str | None) -> ProveedorNotificaciones:
    clase = PROVEEDORES.get(nombre or ProveedorWhatsAppManual.nombre)
    if clase is None:
        # Un nombre desconocido en configuracion no debe tumbar la cobranza.
        clase = ProveedorWhatsAppManual
    return clase()
