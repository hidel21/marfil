"""Comandos de administracion.

    python -m app.cli usuarios
    python -m app.cli establecer-password hm@intelli-next.com
    python -m app.cli crear-usuario ana@marfil.test "Ana" vendedor
    python -m app.cli estado

Sin dependencias de CLI extra: argparse alcanza para cinco comandos y evita sumar
una libreria al despliegue.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from sqlalchemy import text

from app.config import obtener_settings
from app.core.seguridad import HASH_BLOQUEADO, hashear_password
from app.db.session import sesion_manual


def _listar_usuarios() -> int:
    with sesion_manual() as s:
        filas = s.execute(
            text(
                "SELECT u.id, u.email, u.nombre, u.rol::text, u.activo, "
                "u.password_hash = :bloq AS bloqueado, u.debe_cambiar_password, "
                "u.ultimo_login_at "
                "FROM usuarios u ORDER BY u.id"
            ),
            {"bloq": HASH_BLOQUEADO},
        ).all()

    if not filas:
        print("No hay usuarios. Corré las migraciones (alembic upgrade head).")
        return 1

    print(f"{'id':>3}  {'email':28} {'nombre':14} {'rol':9} estado")
    for f in filas:
        estado = []
        if not f.activo:
            estado.append("inactivo")
        if f.bloqueado:
            estado.append("SIN CONTRASEÑA")
        elif f.debe_cambiar_password:
            estado.append("debe cambiarla")
        if f.ultimo_login_at:
            estado.append(f"último login {f.ultimo_login_at:%Y-%m-%d}")
        print(f"{f.id:>3}  {f.email:28} {f.nombre:14} {f.rol:9} {', '.join(estado) or 'ok'}")

    bloqueados = sum(1 for f in filas if f.bloqueado)
    if bloqueados:
        print(
            f"\n{bloqueados} usuario(s) sin contraseña. Fijala con:\n"
            "  python -m app.cli establecer-password <email>"
        )
    return 0


def _establecer_password(email: str, password: str | None) -> int:
    with sesion_manual() as s:
        usuario = s.execute(
            text("SELECT id, nombre FROM usuarios WHERE email = :e"), {"e": email}
        ).one_or_none()
        if usuario is None:
            print(f"No existe un usuario con email {email!r}.", file=sys.stderr)
            return 1

        if password is None:
            password = getpass.getpass(f"Contraseña nueva para {usuario.nombre}: ")
            if password != getpass.getpass("Repetila: "):
                print("Las contraseñas no coinciden.", file=sys.stderr)
                return 1
        try:
            hash_nuevo = hashear_password(password)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        s.execute(
            text(
                "UPDATE usuarios SET password_hash = :h, debe_cambiar_password = FALSE "
                "WHERE id = :i"
            ),
            {"h": hash_nuevo, "i": usuario.id},
        )
        # Cambiar la contraseña invalida las sesiones abiertas: si se cambió porque
        # alguien más la tenía, dejar sus tokens vivos anula el punto.
        revocados = s.execute(
            text(
                "UPDATE refresh_tokens SET revocado_at = now() "
                "WHERE usuario_id = :i AND revocado_at IS NULL"
            ),
            {"i": usuario.id},
        ).rowcount
    print(f"Contraseña de {usuario.nombre} actualizada. Sesiones revocadas: {revocados}.")
    return 0


def _crear_usuario(email: str, nombre: str, rol: str, cliente_id: int | None) -> int:
    if rol not in {"admin", "vendedor", "afiliado"}:
        print(f"Rol inválido: {rol!r}. Usá admin, vendedor o afiliado.", file=sys.stderr)
        return 1
    if rol == "afiliado" and cliente_id is None:
        print(
            "Un afiliado es un cliente con login: pasá --cliente-id.\n"
            "Es una restricción de la base, no un capricho del CLI.",
            file=sys.stderr,
        )
        return 1

    with sesion_manual() as s:
        existe = s.execute(text("SELECT 1 FROM usuarios WHERE email = :e"), {"e": email}).scalar()
        if existe:
            print(f"Ya hay un usuario con email {email!r}.", file=sys.stderr)
            return 1
        nuevo = s.execute(
            text(
                "INSERT INTO usuarios (email, nombre, password_hash, rol, cliente_id, "
                "debe_cambiar_password) VALUES (:e, :n, :h, :r, :c, TRUE) RETURNING id"
            ),
            {"e": email, "n": nombre, "h": HASH_BLOQUEADO, "r": rol, "c": cliente_id},
        ).scalar_one()
    print(
        f"Usuario {nombre} creado (id={nuevo}, rol={rol}), sin contraseña.\n"
        f"  python -m app.cli establecer-password {email}"
    )
    return 0


def _estado() -> int:
    settings = obtener_settings()
    print(f"entorno : {settings.entorno}")
    url = settings.database_url
    print(f"base    : {url.rpartition('@')[2] if '@' in url else '(sin definir)'}")

    with sesion_manual() as s:
        rev = s.execute(
            text(
                "SELECT version_num FROM alembic_version_marfil"
                if s.execute(
                    text("SELECT to_regclass('public.alembic_version_marfil') IS NOT NULL")
                ).scalar()
                else "SELECT NULL"
            )
        ).scalar()
        print(f"revisión: {rev or '(sin migrar)'}")

        conteos = s.execute(
            text(
                "SELECT (SELECT count(*) FROM usuarios), (SELECT count(*) FROM clientes), "
                "(SELECT count(*) FROM productos), (SELECT count(*) FROM ventas), "
                "(SELECT count(*) FROM pagos)"
            )
        ).one()
        print(
            f"datos   : {conteos[0]} usuarios, {conteos[1]} clientes, "
            f"{conteos[2]} productos, {conteos[3]} ventas, {conteos[4]} pagos"
        )

        datos_pago = s.execute(
            text("SELECT valor FROM configuracion WHERE clave = 'datos_pago'")
        ).scalar()
        if datos_pago is None:
            print("datos de pago: sin configurar")
        else:
            faltan = [k for k in ("banco", "documento", "telefono") if not datos_pago.get(k)]
            if faltan:
                print(
                    f"datos de pago: INCOMPLETOS (faltan {', '.join(faltan)}) "
                    "-> no se pueden enviar recordatorios"
                )
            else:
                print("datos de pago: completos")
    return 0


def _inicializar_admin() -> int:
    """Activa una sola vez el admin sembrado, sin reescribir claves posteriores."""
    password = os.getenv("ADMIN_INITIAL_PASSWORD", "")
    if not password:
        print("ADMIN_INITIAL_PASSWORD no definido; inicialización omitida.")
        return 0
    try:
        password_hash = hashear_password(password)
    except ValueError as exc:
        print(f"ADMIN_INITIAL_PASSWORD inválido: {exc}", file=sys.stderr)
        return 1
    with sesion_manual() as s:
        actualizado = s.execute(
            text(
                "UPDATE usuarios SET password_hash=:h, debe_cambiar_password=FALSE "
                "WHERE email='hm@intelli-next.com' AND password_hash=:bloqueado"
            ),
            {"h": password_hash, "bloqueado": HASH_BLOQUEADO},
        ).rowcount
    print("Administrador inicial activado." if actualizado else "Administrador ya inicializado.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli", description="Administración de Marfil")
    sub = parser.add_subparsers(dest="comando", required=True)

    sub.add_parser("usuarios", help="listar usuarios y su estado")
    sub.add_parser("estado", help="revisión, conteos y si falta configuración")
    sub.add_parser("inicializar-admin", help="activa una vez el admin desde una variable segura")

    p_pass = sub.add_parser("establecer-password", help="fijar la contraseña de un usuario")
    p_pass.add_argument("email")
    p_pass.add_argument(
        "--password",
        help="para scripts. Sin esto se pide por consola, que es lo recomendado: "
        "así la contraseña no queda en el historial del shell.",
    )

    p_nuevo = sub.add_parser("crear-usuario", help="crear un usuario sin contraseña")
    p_nuevo.add_argument("email")
    p_nuevo.add_argument("nombre")
    p_nuevo.add_argument("rol", choices=["admin", "vendedor", "afiliado"])
    p_nuevo.add_argument("--cliente-id", type=int, help="obligatorio para un afiliado")

    args = parser.parse_args(argv)

    if args.comando == "usuarios":
        return _listar_usuarios()
    if args.comando == "estado":
        return _estado()
    if args.comando == "inicializar-admin":
        return _inicializar_admin()
    if args.comando == "establecer-password":
        return _establecer_password(args.email, args.password)
    if args.comando == "crear-usuario":
        return _crear_usuario(args.email, args.nombre, args.rol, args.cliente_id)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
