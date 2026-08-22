"""Normalización de nombres, encabezados y teléfonos.

`normalizar_nombre` es la clave de deduplicación de clientes y productos: es lo que
hace que 'AQUA DI GIO', 'Aqua di Gio' y 'acqua  di   gio ' no sean tres productos
distintos en todos los reportes.

`normalizar_clave` es la versión arreglada de `normalize_column_name` de app.py, que
borraba '($)' *antes* de mapear espacios a '_' y dejaba guiones bajos colgando
('PRECIO TASA BCV ($)' -> 'precio_tasa_bcv_'). El mapa de alias compensaba eso
enumerando variantes a mano; con esto se puede quedar solo con las claves canónicas.
"""

from __future__ import annotations

import re
import unicodedata

_NO_ALFANUM = re.compile(r"[^a-z0-9]+")
_ESPACIOS = re.compile(r"\s+")

OPERADORAS_MOVILES_VE = ("412", "414", "416", "424", "426")
PREFIJO_PAIS_VE = "58"


def _sin_acentos(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def normalizar_nombre(texto: object) -> str:
    """'  ACQUA  di Gió ' -> 'acqua di gio'. Forma legible, para mostrar y buscar."""
    if texto is None:
        return ""
    base = _sin_acentos(str(texto).strip().lower())
    base = _NO_ALFANUM.sub(" ", base)
    return _ESPACIOS.sub(" ", base).strip()


def clave_nombre(texto: object) -> str:
    """Clave de unicidad: como `normalizar_nombre` pero **sin espacios**.

    Los espacios se van porque la auditoría documenta '212 Vip' / '212 vip' /
    '212Vip' como el mismo producto, y con espacios esas tres no colisionan. Es el
    valor que va en las columnas `nombre_normalizado` y en los índices únicos.

    Sigue distinguiendo lo que debe distinguirse: 'ricardo' != 'ricardopalacios',
    'verygoodgirl' != 'verygoodgrul' (esa segunda necesita un alias, no una fusión
    automática).
    """
    return normalizar_nombre(texto).replace(" ", "")


def normalizar_clave(texto: object) -> str:
    """'PRECIO DIVISA / USDT ($)' -> 'precio_divisa_usdt'. Sin guiones colgando."""
    if texto is None:
        return ""
    base = _sin_acentos(str(texto).strip().lower())
    return _NO_ALFANUM.sub("_", base).strip("_")


class TelefonoInvalido(ValueError):
    """El texto no es un móvil venezolano reconocible."""


def telefono_e164(texto: object) -> str:
    """Normaliza a E.164: '0412-1234567' -> '+584121234567'.

    Solo móviles venezolanos: un recordatorio de WhatsApp a un fijo no llega.
    """
    if texto is None:
        raise TelefonoInvalido("teléfono vacío")

    digitos = re.sub(r"\D", "", str(texto))
    if not digitos:
        raise TelefonoInvalido("teléfono vacío")

    if digitos.startswith(PREFIJO_PAIS_VE) and len(digitos) == 12:
        nacional = digitos[2:]
    elif digitos.startswith("0") and len(digitos) == 11:
        nacional = digitos[1:]
    elif len(digitos) == 10:
        nacional = digitos
    else:
        raise TelefonoInvalido(f"largo inesperado para un móvil venezolano: {texto!r}")

    if nacional[:3] not in OPERADORAS_MOVILES_VE:
        raise TelefonoInvalido(
            f"'{nacional[:3]}' no es una operadora móvil venezolana ({', '.join(OPERADORAS_MOVILES_VE)})"
        )
    return f"+{PREFIJO_PAIS_VE}{nacional}"


def telefono_e164_o_none(texto: object) -> str | None:
    try:
        return telefono_e164(texto)
    except TelefonoInvalido:
        return None
