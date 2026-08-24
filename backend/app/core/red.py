"""Utilidades de red.

`ip_valida` existe porque `request.client.host` no siempre es una IP: el TestClient
manda "testclient" y detras de algunos proxies puede llegar un hostname. La columna
`inet` lo rechaza, y eso hacia fallar el login entero.

Un dato de auditoria no puede tumbar una operacion: si no es una IP, se guarda NULL.
"""

from __future__ import annotations

import ipaddress


def ip_valida(valor: str | None) -> str | None:
    """Devuelve la IP si lo es, o None. Nunca levanta."""
    if not valor:
        return None
    candidato = valor.split(",")[0].strip()
    try:
        return str(ipaddress.ip_address(candidato))
    except ValueError:
        return None
