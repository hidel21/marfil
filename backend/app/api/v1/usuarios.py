"""Usuarios. Los crea el superadmin y cada uno cambia su contrasena al entrar.

Por que no se siembran las tres cuentas en la migracion: no conocemos las direcciones
reales de los otros dos socios, y sembrar `gregory@marfil.local` deja una cuenta que
nadie reclama y un email que ni siquiera pasa un validador de formato. Es mas simple y
mas honesto que el superadmin cree el perfil con la direccion de cada uno.

**Nadie recibe una contrasena por este endpoint.** Se crea con un hash bloqueado y se
devuelve un codigo de activacion de un solo uso; el usuario lo canjea eligiendo su
propia contrasena. Asi la contrasena nunca existe en un chat, ni en un log, ni en la
memoria de quien la creo.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from app.api.deps import PuedeEscribir, SesionDb, SoloAdmin
from app.api.errors import Conflicto, ErrorNegocio, NoEncontrado
from app.core.seguridad import (
    HASH_BLOQUEADO,
    hashear_password,
    hashear_refresh_token,
)
from app.models.enums import RolUsuario
from app.schemas.comun import Esquema

router = APIRouter(prefix="/usuarios", tags=["usuarios"])

#: Cuanto vive un codigo de activacion. Corto a proposito: es para usarlo hoy.
HORAS_ACTIVACION = 72


class UsuarioSalida(Esquema):
    id: int
    email: str
    nombre: str
    rol: str
    activo: bool
    debe_cambiar_password: bool
    sin_password: bool
    socio_id: int | None
    cliente_id: int | None
    ultimo_login_at: datetime | None


@router.get("", response_model=list[UsuarioSalida])
def listar(db: SesionDb, actual: SoloAdmin, incluir_inactivos: bool = False):
    del actual
    filtro = "" if incluir_inactivos else "WHERE u.activo"
    filas = db.execute(
        text(
            f"""
            SELECT u.id, u.email, u.nombre, u.rol::text AS rol, u.activo,
                   u.debe_cambiar_password, u.password_hash = :bloq AS sin_password,
                   s.id AS socio_id, u.cliente_id, u.ultimo_login_at
            FROM usuarios u LEFT JOIN socios s ON s.usuario_id = u.id
            {filtro} ORDER BY u.rol, u.nombre
            """
        ),
        {"bloq": HASH_BLOQUEADO},
    ).all()
    return [dict(f._mapping) for f in filas]


class UsuarioEntrada(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    nombre: str = Field(min_length=2, max_length=120)
    rol: RolUsuario
    #: Para un socio: lo liga a su fila de reparto de utilidad.
    socio_id: int | None = None
    #: Obligatorio para un afiliado: es un cliente con login.
    cliente_id: int | None = None

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        limpio = v.strip().lower()
        if "@" not in limpio or limpio.startswith("@") or limpio.endswith("@"):
            raise ValueError("Eso no parece un correo.")
        return limpio


class UsuarioCreado(Esquema):
    usuario_id: int
    email: str
    nombre: str
    rol: str
    #: El codigo que se le pasa a la persona. **No es una contrasena**: sirve una vez,
    #: para que ella elija la suya.
    codigo_activacion: str
    expira_at: datetime
    instrucciones: str


@router.post("", response_model=UsuarioCreado, status_code=201)
def crear(datos: UsuarioEntrada, db: SesionDb, actual: SoloAdmin, _: PuedeEscribir):
    """Crea el perfil y devuelve un codigo de activacion de un solo uso."""
    if datos.rol == RolUsuario.AFILIADO and datos.cliente_id is None:
        raise ErrorNegocio(
            "AFILIADO_SIN_CLIENTE",
            "Un afiliado es un cliente con acceso: hay que indicar de qué cliente.",
            campo="cliente_id",
            sugerencia="Buscá el cliente en la lista y volvé a intentar.",
        )
    if db.execute(
        text("SELECT 1 FROM usuarios WHERE email = :e"), {"e": datos.email}
    ).scalar():
        raise Conflicto(
            "EMAIL_YA_USADO",
            f"Ya hay un usuario con el correo {datos.email}.",
            campo="email",
        )

    usuario_id = db.execute(
        text(
            "INSERT INTO usuarios (email, nombre, password_hash, rol, cliente_id, "
            "debe_cambiar_password) VALUES (:e, :n, :h, :r, :c, TRUE) RETURNING id"
        ),
        {
            "e": datos.email,
            "n": datos.nombre.strip(),
            "h": HASH_BLOQUEADO,
            "r": datos.rol.value,
            "c": datos.cliente_id,
        },
    ).scalar_one()

    if datos.socio_id is not None:
        db.execute(
            text("UPDATE socios SET usuario_id = :u WHERE id = :s AND usuario_id IS NULL"),
            {"u": usuario_id, "s": datos.socio_id},
        )

    codigo = secrets.token_urlsafe(24)
    expira = datetime.now(UTC) + timedelta(hours=HORAS_ACTIVACION)
    # Se reutiliza `refresh_tokens` para guardar el codigo hasheado: misma necesidad
    # (un secreto de un solo uso, con vencimiento y revocable) y misma disciplina de
    # no guardarlo en claro. La familia se marca para distinguirlo de una sesion.
    db.execute(
        text(
            "INSERT INTO refresh_tokens (usuario_id, token_hash, familia_id, expira_at, "
            "user_agent) VALUES (:u, :h, gen_random_uuid(), :e, 'activacion')"
        ),
        {"u": usuario_id, "h": hashear_refresh_token(codigo), "e": expira},
    )
    db.commit()

    return UsuarioCreado(
        usuario_id=usuario_id,
        email=datos.email,
        nombre=datos.nombre.strip(),
        rol=datos.rol.value,
        codigo_activacion=codigo,
        expira_at=expira,
        instrucciones=(
            f"Pasale este código a {datos.nombre.strip()}. Con él elige su propia "
            f"contraseña al entrar por primera vez, y vence en {HORAS_ACTIVACION} horas. "
            "No es una contraseña y sirve una sola vez: así la contraseña de esa "
            "persona nunca pasa por tus manos."
        ),
    )


class ActivacionEntrada(BaseModel):
    email: str = Field(min_length=5)
    codigo: str = Field(min_length=10)
    password_nueva: str = Field(min_length=8)


@router.post("/activar", status_code=204)
def activar(datos: ActivacionEntrada, db: SesionDb, _: PuedeEscribir):
    """Canjea el codigo por la contrasena que elige la persona. Sin autenticacion.

    Es el unico endpoint de escritura sin token, y tiene que serlo: quien lo usa
    todavia no puede entrar.
    """
    fila = db.execute(
        text(
            "SELECT t.id, t.usuario_id, t.expira_at, t.revocado_at "
            "FROM refresh_tokens t JOIN usuarios u ON u.id = t.usuario_id "
            "WHERE t.token_hash = :h AND u.email = :e AND t.user_agent = 'activacion'"
        ),
        {"h": hashear_refresh_token(datos.codigo), "e": datos.email.strip().lower()},
    ).one_or_none()

    if fila is None or fila.revocado_at is not None:
        raise ErrorNegocio(
            "CODIGO_INVALIDO",
            "Ese código no sirve o ya se usó.",
            sugerencia="Pedile al administrador que te genere uno nuevo.",
        )
    if fila.expira_at < datetime.now(UTC):
        raise ErrorNegocio(
            "CODIGO_VENCIDO",
            "Ese código venció.",
            sugerencia="Pedile al administrador que te genere uno nuevo.",
        )

    try:
        nuevo_hash = hashear_password(datos.password_nueva)
    except ValueError as exc:
        raise ErrorNegocio("PASSWORD_DEBIL", str(exc), campo="password_nueva") from exc

    db.execute(
        text(
            "UPDATE usuarios SET password_hash = :h, debe_cambiar_password = FALSE "
            "WHERE id = :i"
        ),
        {"h": nuevo_hash, "i": fila.usuario_id},
    )
    # El codigo se consume, y con el cualquier otro pendiente del mismo usuario.
    db.execute(
        text(
            "UPDATE refresh_tokens SET revocado_at = now() "
            "WHERE usuario_id = :u AND user_agent = 'activacion' AND revocado_at IS NULL"
        ),
        {"u": fila.usuario_id},
    )
    db.commit()


@router.post("/{usuario_id}/reactivar-codigo", response_model=UsuarioCreado)
def reactivar_codigo(
    usuario_id: int, db: SesionDb, actual: SoloAdmin, _: PuedeEscribir
):
    """Genera un codigo nuevo, por si el anterior vencio o se perdio."""
    del actual
    usuario = db.execute(
        text("SELECT id, email, nombre, rol::text AS rol FROM usuarios WHERE id = :i"),
        {"i": usuario_id},
    ).one_or_none()
    if usuario is None:
        raise NoEncontrado("ese usuario")

    db.execute(
        text(
            "UPDATE refresh_tokens SET revocado_at = now() "
            "WHERE usuario_id = :u AND user_agent = 'activacion' AND revocado_at IS NULL"
        ),
        {"u": usuario_id},
    )
    codigo = secrets.token_urlsafe(24)
    expira = datetime.now(UTC) + timedelta(hours=HORAS_ACTIVACION)
    db.execute(
        text(
            "INSERT INTO refresh_tokens (usuario_id, token_hash, familia_id, expira_at, "
            "user_agent) VALUES (:u, :h, gen_random_uuid(), :e, 'activacion')"
        ),
        {"u": usuario_id, "h": hashear_refresh_token(codigo), "e": expira},
    )
    db.commit()
    return UsuarioCreado(
        usuario_id=usuario.id,
        email=usuario.email,
        nombre=usuario.nombre,
        rol=usuario.rol,
        codigo_activacion=codigo,
        expira_at=expira,
        instrucciones=(
            f"Código nuevo para {usuario.nombre}. El anterior quedó anulado."
        ),
    )


class EstadoEntrada(BaseModel):
    activo: bool
    motivo: str | None = None


@router.put("/{usuario_id}/estado", status_code=204)
def cambiar_estado(
    usuario_id: int,
    datos: EstadoEntrada,
    db: SesionDb,
    actual: SoloAdmin,
    _: PuedeEscribir,
):
    """Activa o desactiva una cuenta. Desactivar cierra sus sesiones en el momento."""
    if usuario_id == actual.id and not datos.activo:
        raise Conflicto(
            "NO_TE_PUEDES_DESACTIVAR",
            "No podés desactivar tu propia cuenta.",
            sugerencia="Pedile a otro administrador que lo haga.",
        )
    afectadas = db.execute(
        text("UPDATE usuarios SET activo = :a WHERE id = :i"),
        {"a": datos.activo, "i": usuario_id},
    ).rowcount
    if not afectadas:
        raise NoEncontrado("ese usuario")

    if not datos.activo:
        # Sin esto, un token ya emitido seguiria valiendo hasta media hora.
        db.execute(
            text(
                "UPDATE refresh_tokens SET revocado_at = now() "
                "WHERE usuario_id = :u AND revocado_at IS NULL"
            ),
            {"u": usuario_id},
        )
    db.commit()


@router.get("/socios-sin-cuenta")
def socios_sin_cuenta(db: SesionDb, actual: SoloAdmin, limite: int = Query(default=20)):
    """Los socios que todavía no tienen perfil. Es la lista de trabajo del superadmin."""
    del actual
    filas = db.execute(
        text(
            "SELECT id, nombre, capital_invertido FROM socios "
            "WHERE usuario_id IS NULL ORDER BY nombre LIMIT :l"
        ),
        {"l": limite},
    ).all()
    return [dict(f._mapping) for f in filas]
