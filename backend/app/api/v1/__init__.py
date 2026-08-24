"""Router de la version 1 de la API."""

from fastapi import APIRouter

from app.api.v1 import (
    ajustes,
    auditoria,
    auth,
    automatizaciones,
    clientes,
    cobranza,
    compras,
    dashboard,
    finanzas,
    gastos,
    pagos,
    productos,
    recordatorios,
    reportes,
    usuarios,
    ventas,
)

router = APIRouter(prefix="/api/v1")
for modulo in (
    auth,
    dashboard,
    usuarios,
    clientes,
    productos,
    ventas,
    pagos,
    compras,
    gastos,
    finanzas,
    cobranza,
    recordatorios,
    auditoria,
    ajustes,
    automatizaciones,
    reportes,
):
    router.include_router(modulo.router)

__all__ = ["router"]
