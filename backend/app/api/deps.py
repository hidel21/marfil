"""Dependencias de FastAPI: sesion, usuario actual y permisos.

El alcance de datos se resuelve aca y no en cada endpoint: `alcance` devuelve el
filtro que corresponde al rol, asi que agregar un endpoint no obliga a recordar la
regla de visibilidad.

Y el costo se oculta **en el esquema de respuesta**, no confiando en el cliente: un
campo que nunca entra al serializador no se puede filtrar. Ver `schemas/venta.py`.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, Header, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errors import NoAutenticado, SinPermiso, SoloLectura
from app.config import obtener_settings
from app.core.seguridad import decodificar_access_token
from app.db.session import fijar_contexto, obtener_sessionmaker
from app.models.enums import RolUsuario


@dataclass(frozen=True)
class UsuarioActual:
    id: int
    nombre: str
    email: str
    rol: RolUsuario
    cliente_id: int | None
    debe_cambiar_password: bool

    @property
    def es_admin(self) -> bool:
        return self.rol == RolUsuario.ADMIN

    @property
    def es_vendedor(self) -> bool:
        return self.rol == RolUsuario.VENDEDOR

    @property
    def es_afiliado(self) -> bool:
        return self.rol == RolUsuario.AFILIADO

    @property
    def ve_costos(self) -> bool:
        """Solo los socios ven costo y margen."""
        return self.es_admin


def sesion(request: Request) -> Iterator[Session]:
    """Sesion con el contexto de auditoria fijado de forma explicita.

    Se hace con `fijar_contexto()` y no con ContextVars a proposito: FastAPI corre las
    dependencias sincronicas en un threadpool, y la transaccion de la sesion puede
    empezar en un contexto distinto del que puso el valor. Con ContextVars el
    `SET LOCAL` se perdia en silencio, y con el se perdian dos cosas: la firma del
    usuario en la auditoria, y —peor— la senal de que escribe la API, sin la cual la
    capa de compatibilidad con Streamlit creaba una segunda linea para la misma venta.

    `escritor = 'api'` es esa senal: la API ya escribe el modelo canonico completo.
    """
    del request
    fabrica = obtener_sessionmaker()
    sesion_db = fabrica()
    try:
        fijar_contexto(sesion_db, request_id=str(uuid.uuid4()), escritor="api")
        yield sesion_db
    except Exception:
        sesion_db.rollback()
        raise
    finally:
        sesion_db.close()


SesionDb = Annotated[Session, Depends(sesion)]


def _token_del_pedido(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise NoAutenticado()
    return authorization.split(" ", 1)[1].strip()


def usuario_actual(
    db: SesionDb,
    authorization: Annotated[str | None, Header()] = None,
) -> UsuarioActual:
    token = _token_del_pedido(authorization)
    try:
        datos = decodificar_access_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise NoAutenticado("Tu sesión expiró. Volvé a entrar.") from exc
    except jwt.PyJWTError as exc:
        raise NoAutenticado("La sesión no es válida.") from exc

    fila = db.execute(
        text(
            "SELECT id, nombre, email, rol::text AS rol, cliente_id, debe_cambiar_password "
            "FROM usuarios WHERE id = :i AND activo"
        ),
        {"i": int(datos["sub"])},
    ).one_or_none()
    if fila is None:
        # Cuenta desactivada: el token puede seguir siendo criptograficamente valido.
        raise NoAutenticado("Tu usuario ya no está activo.")

    # Se publica a la sesion de Postgres para que los triggers de auditoria firmen
    # con el usuario y no con 'sistema'.
    fijar_contexto(db, usuario_id=fila.id)
    return UsuarioActual(
        id=fila.id,
        nombre=fila.nombre,
        email=fila.email,
        rol=RolUsuario(fila.rol),
        cliente_id=fila.cliente_id,
        debe_cambiar_password=fila.debe_cambiar_password,
    )


Usuario = Annotated[UsuarioActual, Depends(usuario_actual)]


def requiere_rol(*roles: RolUsuario):
    """Dependencia de router. `requiere_rol(RolUsuario.ADMIN)`."""

    permitidos = set(roles)

    def _verificar(actual: Usuario) -> UsuarioActual:
        if actual.rol not in permitidos:
            nombres = ", ".join(sorted(r.value for r in permitidos))
            raise SinPermiso(f"Esto es solo para: {nombres}.")
        return actual

    return _verificar


SoloAdmin = Annotated[UsuarioActual, Depends(requiere_rol(RolUsuario.ADMIN))]
AdminOVendedor = Annotated[
    UsuarioActual, Depends(requiere_rol(RolUsuario.ADMIN, RolUsuario.VENDEDOR))
]


def escritura_permitida() -> None:
    """El interruptor de emergencia de la migracion."""
    if obtener_settings().solo_lectura:
        raise SoloLectura()


PuedeEscribir = Annotated[None, Depends(escritura_permitida)]


@dataclass(frozen=True)
class Alcance:
    """Que filas ve este usuario. Se resuelve una vez, no en cada endpoint."""

    usuario: UsuarioActual

    @property
    def ventas_where(self) -> tuple[str, dict[str, object]]:
        if self.usuario.es_admin:
            return "TRUE", {}
        if self.usuario.es_vendedor:
            return "v.vendedor_usuario_id = :alcance_usuario", {"alcance_usuario": self.usuario.id}
        # Afiliado: solo lo suyo. Sin cliente_id no ve nada, que es lo correcto.
        return "v.cliente_id = :alcance_cliente", {"alcance_cliente": self.usuario.cliente_id or -1}

    @property
    def cobranza_where(self) -> tuple[str, dict[str, object]]:
        if self.usuario.es_admin:
            return "TRUE", {}
        if self.usuario.es_vendedor:
            return "cb.vendedor_usuario_id = :alcance_usuario", {"alcance_usuario": self.usuario.id}
        return "cb.cliente_id = :alcance_cliente", {
            "alcance_cliente": self.usuario.cliente_id or -1
        }


def alcance(actual: Usuario) -> Alcance:
    return Alcance(usuario=actual)


AlcanceDatos = Annotated[Alcance, Depends(alcance)]
