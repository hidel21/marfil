"""Esquemas de autenticacion."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.comun import Esquema


class LoginEntrada(BaseModel):
    """El email es una clave de busqueda, no un dato a validar.

    Deliberadamente `str` y no `EmailStr`: el validador de Pydantic rechaza los TLD
    reservados (.local, .test), y los tres socios se siembran con
    `gregory@marfil.local` porque no conocemos sus direcciones reales. Con `EmailStr`
    aca, **dos de los tres administradores no podrian entrar nunca**.

    Validar el formato al entrar tampoco aporta: un email mal escrito simplemente no
    coincide con ninguno, que es la misma respuesta. La validacion va donde se crea
    un usuario.
    """

    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1)


class SesionSalida(Esquema):
    access_token: str
    token_tipo: str = "bearer"
    expira_en_segundos: int
    usuario_id: int
    nombre: str
    rol: str
    debe_cambiar_password: bool


class YoSalida(Esquema):
    id: int
    nombre: str
    email: str
    rol: str
    cliente_id: int | None
    debe_cambiar_password: bool
    ve_costos: bool


class CambiarPasswordEntrada(BaseModel):
    password_actual: str = Field(default="")
    password_nueva: str = Field(min_length=8)
