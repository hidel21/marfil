"""Router de la version 1 de la API."""

from fastapi import APIRouter

from app.api.v1 import (
    ajustes,
    auditoria,
    auth,
    clientes,
    cobranza,
    pagos,
    productos,
    recordatorios,
    usuarios,
    ventas,
)

router = APIRouter(prefix="/api/v1")
for modulo in (
    auth,
    usuarios,
    clientes,
    productos,
    ventas,
    pagos,
    cobranza,
    recordatorios,
    auditoria,
    ajustes,
):
    router.include_router(modulo.router)

__all__ = ["router"]
