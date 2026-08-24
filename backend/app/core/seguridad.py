"""Hash de contraseñas y tokens.

`pwdlib[argon2]` y no `passlib`: passlib está sin mantenimiento y se rompe contra
`bcrypt >= 4.1`. pwdlib es su sucesor mantenido y trae argon2id por defecto.

Los refresh tokens se guardan **hasheados** con SHA-256 y agrupados por
`familia_id`. Eso da dos cosas que un JWT sin estado no puede: revocación real (un
vendedor que deja el equipo pierde el acceso en el momento) y detección de reuso
(si aparece un token ya rotado, se revoca la familia entera).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash

from app.config import obtener_settings

_hasher = PasswordHash.recommended()

#: Hash imposible de satisfacer. Se usa para sembrar usuarios sin contraseña:
#: la cuenta existe y aparece en la UI, pero no se puede entrar hasta que un socio
#: fije la primera contraseña. Mejor que sembrar una contraseña conocida.
HASH_BLOQUEADO = "!bloqueado"


def hashear_password(password: str) -> str:
    if not password or len(password) < 8:
        raise ValueError("La contraseña necesita al menos 8 caracteres.")
    return _hasher.hash(password)


def verificar_password(password: str, hash_guardado: str) -> bool:
    if not hash_guardado or hash_guardado == HASH_BLOQUEADO:
        return False
    try:
        return _hasher.verify(password, hash_guardado)
    except Exception:
        # Un hash corrupto es un fallo de autenticación, no un 500.
        return False


def verificar_y_actualizar(password: str, hash_guardado: str) -> tuple[bool, str | None]:
    """Verifica y devuelve un hash nuevo si el guardado usa parámetros viejos.

    Sirve para subir el costo de argon2 con el tiempo sin pedirle a nadie que cambie
    la contraseña: se rehashea en el login. El segundo valor es None cuando no hace
    falta actualizar nada.
    """
    if not hash_guardado or hash_guardado == HASH_BLOQUEADO:
        return False, None
    try:
        return _hasher.verify_and_update(password, hash_guardado)
    except Exception:
        return False, None


# ------------------------------------------------------------------ access token
def crear_access_token(usuario_id: int, rol: str, *, minutos: int | None = None) -> str:
    settings = obtener_settings()
    ahora = datetime.now(UTC)
    expira = ahora + timedelta(minutes=minutos or settings.access_token_minutos)
    payload = {
        "sub": str(usuario_id),
        "rol": rol,
        "iat": int(ahora.timestamp()),
        "exp": int(expira.timestamp()),
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algoritmo)


def decodificar_access_token(token: str) -> dict[str, Any]:
    """Levanta `jwt.PyJWTError` si el token no sirve. El caller lo traduce a 401."""
    settings = obtener_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algoritmo])


# ----------------------------------------------------------------- refresh token
def generar_refresh_token() -> tuple[str, str]:
    """Devuelve (token en claro, hash a guardar). El claro solo viaja a la cookie."""
    token = secrets.token_urlsafe(48)
    return token, hashear_refresh_token(token)


def hashear_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
