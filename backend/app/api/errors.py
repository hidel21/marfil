"""Errores de negocio y su traduccion a HTTP.

Regla: el dueno del negocio nunca ve una traza de SQLAlchemy. La app vieja tenia 44
`except Exception` que mostraban `str(exc)` crudo; aca cada fallo esperable tiene un
codigo estable, un mensaje en espanol y, cuando corresponde, los numeros para que la
UI pueda ofrecer la salida en vez de solo decir que no.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request, status

from app.api.respuestas import RespuestaMarfil

#: 422. Se escribe el numero porque Starlette renombro la constante
#: (HTTP_422_UNPROCESSABLE_ENTITY -> HTTP_422_UNPROCESSABLE_CONTENT) y no conviene
#: atarse a un nombre que ya cambio una vez.
HTTP_422 = 422


class ErrorNegocio(Exception):
    """Una regla de negocio dijo que no. Nunca es un 500."""

    estado_http = HTTP_422

    def __init__(
        self,
        codigo: str,
        mensaje: str,
        *,
        campo: str | None = None,
        detalles: dict[str, Any] | None = None,
        sugerencia: str | None = None,
    ) -> None:
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje
        self.campo = campo
        self.detalles = detalles or {}
        self.sugerencia = sugerencia

    def como_dict(self) -> dict[str, Any]:
        cuerpo: dict[str, Any] = {"codigo": self.codigo, "mensaje": self.mensaje}
        if self.campo:
            cuerpo["campo"] = self.campo
        if self.sugerencia:
            cuerpo["sugerencia"] = self.sugerencia
        if self.detalles:
            cuerpo["detalles"] = self.detalles
        return cuerpo


class NoAutenticado(ErrorNegocio):
    estado_http = status.HTTP_401_UNAUTHORIZED

    def __init__(self, mensaje: str = "Necesitás iniciar sesión.") -> None:
        super().__init__("NO_AUTENTICADO", mensaje)


class SinPermiso(ErrorNegocio):
    estado_http = status.HTTP_403_FORBIDDEN

    def __init__(self, mensaje: str = "No tenés permiso para esto.") -> None:
        super().__init__("SIN_PERMISO", mensaje)


class NoEncontrado(ErrorNegocio):
    estado_http = status.HTTP_404_NOT_FOUND

    def __init__(self, que: str) -> None:
        super().__init__("NO_ENCONTRADO", f"No existe {que}.")


class Conflicto(ErrorNegocio):
    """409: la operacion es valida pero choca con el estado actual."""

    estado_http = status.HTTP_409_CONFLICT


class SoloLectura(ErrorNegocio):
    estado_http = status.HTTP_503_SERVICE_UNAVAILABLE

    def __init__(self) -> None:
        super().__init__(
            "SOLO_LECTURA",
            "El sistema está en modo solo lectura.",
            sugerencia="Es el interruptor de emergencia de la migración. Avisale a un socio.",
        )


# --------------------------------------------------------------- codigos conocidos
# Se listan para que el frontend pueda mapearlos a una pantalla y para que un cambio
# de nombre sea visible en el diff.
CODIGO_PRECIO_BAJO_COSTO = "PRECIO_BAJO_COSTO"
CODIGO_PRECIO_NIVEL_INCORRECTO = "PRECIO_NIVEL_INCORRECTO"
CODIGO_PRECIO_FUERA_DE_BANDA = "PRECIO_FUERA_DE_BANDA"
CODIGO_PRECIO_SOBRE_POLITICA = "PRECIO_SOBRE_POLITICA"
CODIGO_COSTO_DESCONOCIDO = "COSTO_DESCONOCIDO"
CODIGO_AJUSTES_PAGO_INCOMPLETOS = "AJUSTES_PAGO_INCOMPLETOS"
CODIGO_CLIENTE_SIN_TELEFONO = "CLIENTE_SIN_TELEFONO"
CODIGO_MONTO_USD_INCONSISTENTE = "MONTO_USD_INCONSISTENTE"
CODIGO_ABONO_SUPERA_SALDO = "ABONO_SUPERA_SALDO"
CODIGO_RECORDATORIO_EN_COOLDOWN = "RECORDATORIO_EN_COOLDOWN"
CODIGO_CUOTAS_NO_SUMAN = "CUOTAS_NO_SUMAN"
CODIGO_STOCK_INSUFICIENTE = "STOCK_INSUFICIENTE"
CODIGO_REFERENCIA_DUPLICADA = "REFERENCIA_DUPLICADA"


def registrar_manejadores(app) -> None:  # noqa: ANN001
    """Cuelga los manejadores de error en la app."""
    import logging

    from fastapi.exceptions import RequestValidationError
    from sqlalchemy.exc import IntegrityError, SQLAlchemyError

    log = logging.getLogger("marfil")

    @app.exception_handler(ErrorNegocio)
    async def _negocio(_: Request, exc: ErrorNegocio) -> RespuestaMarfil:
        return RespuestaMarfil(status_code=exc.estado_http, content=exc.como_dict())

    @app.exception_handler(IntegrityError)
    async def _integridad(_: Request, exc: IntegrityError) -> RespuestaMarfil:
        # Los guardias que viven en la base tienen mensajes escritos para leerse.
        # Se traducen a un 409 con el texto del RAISE, no con la traza.
        original = str(getattr(exc, "orig", exc)).strip().splitlines()
        detalle = original[0] if original else "Conflicto de integridad."
        log.warning("IntegrityError: %s", detalle)

        codigo, mensaje = "CONFLICTO_INTEGRIDAD", detalle
        if "uq_pagos_referencia" in detalle:
            codigo = CODIGO_REFERENCIA_DUPLICADA
            mensaje = (
                "Esa referencia, con ese monto y esa fecha, ya está registrada. "
                "¿Es el mismo pago?"
            )
        elif "uq_recordatorios_dia" in detalle:
            codigo = CODIGO_RECORDATORIO_EN_COOLDOWN
            mensaje = "Ya se generó un recordatorio para esa venta hoy."
        elif "append-only" in detalle or "inmutable" in detalle:
            codigo = "LIBRO_INMUTABLE"
        elif "cuotas de la venta" in detalle:
            codigo = CODIGO_CUOTAS_NO_SUMAN

        return RespuestaMarfil(
            status_code=status.HTTP_409_CONFLICT,
            content={"codigo": codigo, "mensaje": mensaje},
        )

    @app.exception_handler(RequestValidationError)
    async def _validacion(_: Request, exc: RequestValidationError) -> RespuestaMarfil:
        """Traduce los errores de Pydantic a la misma forma que el resto.

        Sin esto la API tiene dos formatos de error: `{codigo, mensaje}` para las
        reglas de negocio y `{detail: [...]}` para la validacion, y el frontend
        necesita dos caminos para mostrar lo mismo.
        """
        errores = exc.errors()
        primero = errores[0] if errores else {}
        # loc = ('body', 'campo', ...) -> 'campo'
        partes = [str(p) for p in primero.get("loc", ()) if p not in ("body", "query", "path")]
        campo = ".".join(partes) or None
        mensaje = primero.get("msg", "Los datos enviados no son válidos.")
        mensaje = mensaje.removeprefix("Value error, ")
        return RespuestaMarfil(
            status_code=HTTP_422,
            content={
                "codigo": "DATOS_INVALIDOS",
                "mensaje": mensaje,
                **({"campo": campo} if campo else {}),
                "detalles": {
                    "errores": [
                        {
                            "campo": ".".join(
                                str(p) for p in e.get("loc", ())
                                if p not in ("body", "query", "path")
                            ),
                            "mensaje": e.get("msg", "").removeprefix("Value error, "),
                        }
                        for e in errores
                    ]
                },
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def _sql(_: Request, exc: SQLAlchemyError) -> RespuestaMarfil:
        # Lo unico que no se le muestra al usuario: el detalle va al log.
        log.exception("Error de base de datos", exc_info=exc)
        return RespuestaMarfil(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "codigo": "ERROR_BASE_DE_DATOS",
                "mensaje": "Hubo un problema guardando los datos. No se registró nada.",
            },
        )
