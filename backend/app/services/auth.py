"""Login, refresh y rotacion de tokens.

El refresh token se guarda hasheado y agrupado por `familia_id`. Si aparece uno ya
rotado —senal de que alguien copio la cookie— se revoca la familia entera, no solo
ese token: con la sesion comprometida, cerrarla toda es lo unico util.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errors import ErrorNegocio, NoAutenticado
from app.config import obtener_settings
from app.core.seguridad import (
    HASH_BLOQUEADO,
    crear_access_token,
    generar_refresh_token,
    hashear_password,
    hashear_refresh_token,
    verificar_y_actualizar,
)


@dataclass
class Sesion:
    access_token: str
    refresh_token: str
    expira_en_segundos: int
    usuario_id: int
    nombre: str
    rol: str
    debe_cambiar_password: bool


def _emitir(sesion: Session, usuario, *, familia_id: uuid.UUID | None = None,
            ip: str | None = None, user_agent: str | None = None) -> Sesion:
    settings = obtener_settings()
    claro, hasheado = generar_refresh_token()
    familia = familia_id or uuid.uuid4()

    sesion.execute(
        text(
            "INSERT INTO refresh_tokens (usuario_id, token_hash, familia_id, expira_at, "
            "ip, user_agent) VALUES (:u, :h, :f, :e, :ip, :ua)"
        ),
        {
            "u": usuario.id,
            "h": hasheado,
            "f": str(familia),
            "e": datetime.now(UTC) + timedelta(days=settings.refresh_token_dias),
            "ip": ip,
            "ua": user_agent,
        },
    )
    return Sesion(
        access_token=crear_access_token(usuario.id, usuario.rol),
        refresh_token=claro,
        expira_en_segundos=settings.access_token_minutos * 60,
        usuario_id=usuario.id,
        nombre=usuario.nombre,
        rol=usuario.rol,
        debe_cambiar_password=usuario.debe_cambiar_password,
    )


def login(
    sesion: Session, email: str, password: str, *, ip: str | None = None,
    user_agent: str | None = None,
) -> Sesion:
    fila = sesion.execute(
        text(
            "SELECT id, nombre, email, password_hash, rol::text AS rol, activo, "
            "debe_cambiar_password FROM usuarios WHERE email = :e"
        ),
        {"e": email.strip()},
    ).one_or_none()

    # Mismo mensaje para usuario inexistente y clave incorrecta: decir cual de las dos
    # falla le regala al atacante la mitad del trabajo.
    generico = NoAutenticado("El correo o la contraseña no coinciden.")
    if fila is None or not fila.activo:
        raise generico
    if fila.password_hash == HASH_BLOQUEADO:
        raise ErrorNegocio(
            "USUARIO_SIN_PASSWORD",
            "Esa cuenta todavía no tiene contraseña.",
            sugerencia=(
                "Un socio la habilita con: python -m app.cli establecer-password "
                f"{fila.email}"
            ),
        )

    ok, hash_nuevo = verificar_y_actualizar(password, fila.password_hash)
    if not ok:
        raise generico
    if hash_nuevo:
        # Sube el costo de argon2 con el tiempo sin pedirle nada al usuario.
        sesion.execute(
            text("UPDATE usuarios SET password_hash = :h WHERE id = :i"),
            {"h": hash_nuevo, "i": fila.id},
        )

    sesion.execute(
        text("UPDATE usuarios SET ultimo_login_at = now() WHERE id = :i"), {"i": fila.id}
    )
    return _emitir(sesion, fila, ip=ip, user_agent=user_agent)


def refrescar(
    sesion: Session, token: str, *, ip: str | None = None, user_agent: str | None = None
) -> Sesion:
    hasheado = hashear_refresh_token(token)
    fila = sesion.execute(
        text(
            "SELECT t.id, t.usuario_id, t.familia_id, t.expira_at, t.revocado_at, "
            "u.nombre, u.rol::text AS rol, u.activo, u.debe_cambiar_password "
            "FROM refresh_tokens t JOIN usuarios u ON u.id = t.usuario_id "
            "WHERE t.token_hash = :h"
        ),
        {"h": hasheado},
    ).one_or_none()

    if fila is None:
        raise NoAutenticado("La sesión no es válida. Volvé a entrar.")

    if fila.revocado_at is not None:
        # Reuso de un token ya rotado: la cookie se filtro. Se cierra la familia.
        sesion.execute(
            text(
                "UPDATE refresh_tokens SET revocado_at = now() "
                "WHERE familia_id = :f AND revocado_at IS NULL"
            ),
            {"f": str(fila.familia_id)},
        )
        raise NoAutenticado(
            "Se detectó un uso repetido de la sesión y se cerraron todas por seguridad."
        )

    if fila.expira_at < datetime.now(UTC) or not fila.activo:
        raise NoAutenticado("La sesión expiró. Volvé a entrar.")

    # Rotacion: el token viejo queda revocado en el mismo movimiento.
    sesion.execute(
        text("UPDATE refresh_tokens SET revocado_at = now() WHERE id = :i"), {"i": fila.id}
    )

    class _U:
        id = fila.usuario_id
        nombre = fila.nombre
        rol = fila.rol
        debe_cambiar_password = fila.debe_cambiar_password

    return _emitir(sesion, _U(), familia_id=fila.familia_id, ip=ip, user_agent=user_agent)


def cerrar_sesion(sesion: Session, token: str | None) -> None:
    if not token:
        return
    sesion.execute(
        text(
            "UPDATE refresh_tokens SET revocado_at = now() "
            "WHERE token_hash = :h AND revocado_at IS NULL"
        ),
        {"h": hashear_refresh_token(token)},
    )


def cambiar_password(sesion: Session, usuario_id: int, actual: str, nueva: str) -> None:
    fila = sesion.execute(
        text("SELECT password_hash FROM usuarios WHERE id = :i"), {"i": usuario_id}
    ).one()
    if fila.password_hash != HASH_BLOQUEADO:
        ok, _ = verificar_y_actualizar(actual, fila.password_hash)
        if not ok:
            raise ErrorNegocio(
                "PASSWORD_ACTUAL_INCORRECTA",
                "La contraseña actual no coincide.",
                campo="password_actual",
            )
    try:
        nuevo_hash = hashear_password(nueva)
    except ValueError as exc:
        raise ErrorNegocio("PASSWORD_DEBIL", str(exc), campo="password_nueva") from exc

    sesion.execute(
        text(
            "UPDATE usuarios SET password_hash = :h, debe_cambiar_password = FALSE "
            "WHERE id = :i"
        ),
        {"h": nuevo_hash, "i": usuario_id},
    )
    # Cambiar la clave cierra las otras sesiones: si se cambio porque alguien mas la
    # tenia, dejar sus tokens vivos anula el punto.
    sesion.execute(
        text(
            "UPDATE refresh_tokens SET revocado_at = now() "
            "WHERE usuario_id = :i AND revocado_at IS NULL"
        ),
        {"i": usuario_id},
    )
