"""Autenticacion.

El refresh token va en una cookie HttpOnly y **nunca** viaja en el cuerpo de la
respuesta: asi no lo puede leer ningun script del navegador. El access token si, en
memoria del frontend, con 30 minutos de vida.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Request, Response

from app.api.deps import SesionDb, Usuario
from app.config import obtener_settings
from app.core.red import ip_valida
from app.schemas.auth import (
    CambiarPasswordEntrada,
    LoginEntrada,
    SesionSalida,
    YoSalida,
)
from app.services import auth as svc

router = APIRouter(prefix="/auth", tags=["auth"])

NOMBRE_COOKIE = "marfil_refresh"


def _poner_cookie(respuesta: Response, token: str) -> None:
    settings = obtener_settings()
    respuesta.set_cookie(
        NOMBRE_COOKIE,
        token,
        max_age=settings.refresh_token_dias * 24 * 3600,
        httponly=True,
        secure=settings.es_produccion,
        samesite="lax",
        path="/api/v1/auth",
    )


@router.post("/login", response_model=SesionSalida)
def login(datos: LoginEntrada, request: Request, respuesta: Response, db: SesionDb):
    sesion = svc.login(
        db,
        datos.email,
        datos.password,
        ip=ip_valida(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    _poner_cookie(respuesta, sesion.refresh_token)
    return SesionSalida(
        access_token=sesion.access_token,
        expira_en_segundos=sesion.expira_en_segundos,
        usuario_id=sesion.usuario_id,
        nombre=sesion.nombre,
        rol=sesion.rol,
        debe_cambiar_password=sesion.debe_cambiar_password,
    )


@router.post("/refresh", response_model=SesionSalida)
def refresh(
    request: Request,
    respuesta: Response,
    db: SesionDb,
    marfil_refresh: Annotated[str | None, Cookie()] = None,
):
    sesion = svc.refrescar(
        db,
        marfil_refresh or "",
        ip=ip_valida(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    _poner_cookie(respuesta, sesion.refresh_token)
    return SesionSalida(
        access_token=sesion.access_token,
        expira_en_segundos=sesion.expira_en_segundos,
        usuario_id=sesion.usuario_id,
        nombre=sesion.nombre,
        rol=sesion.rol,
        debe_cambiar_password=sesion.debe_cambiar_password,
    )


@router.post("/logout", status_code=204)
def logout(
    respuesta: Response,
    db: SesionDb,
    marfil_refresh: Annotated[str | None, Cookie()] = None,
):
    svc.cerrar_sesion(db, marfil_refresh)
    db.commit()
    respuesta.delete_cookie(NOMBRE_COOKIE, path="/api/v1/auth")


@router.get("/yo", response_model=YoSalida)
def yo(actual: Usuario):
    return YoSalida(
        id=actual.id,
        nombre=actual.nombre,
        email=actual.email,
        rol=actual.rol.value,
        cliente_id=actual.cliente_id,
        debe_cambiar_password=actual.debe_cambiar_password,
        ve_costos=actual.ve_costos,
    )


@router.post("/cambiar-password", status_code=204)
def cambiar_password(datos: CambiarPasswordEntrada, actual: Usuario, db: SesionDb):
    svc.cambiar_password(db, actual.id, datos.password_actual, datos.password_nueva)
    db.commit()
