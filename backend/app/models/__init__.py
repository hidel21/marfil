"""Modelos del dominio.

Importar este paquete deja `Base.metadata` completo, que es lo que Alembic usa
como objetivo. El orden importa poco (SQLAlchemy resuelve las relaciones por
nombre), pero se agrupa por agregado para que se lea.
"""

from app.models._comun import MarcasDeTiempo, enum_pg
from app.models.auditoria import Conciliacion, EventoAuditoria, JobEjecucion
from app.models.cliente import Cliente, ClienteAlias
from app.models.compra import Compra, Gasto, LoteCompra, PagoCompra, Proveedor
from app.models.enums import (
    AccionAuditoria,
    ActorAuditoria,
    CanalPago,
    ConfianzaDato,
    EstadoCobro,
    EstadoProducto,
    EstadoRecordatorio,
    EstadoRegistro,
    MetodoEnlace,
    ModeloPrecio,
    Moneda,
    MotivoOmision,
    NivelPrecio,
    OrigenTasa,
    RolUsuario,
    TipoLineaLote,
    TipoMovimientoPago,
    TipoMovimientoStock,
    TipoTasa,
)
from app.models.importacion import EnlaceImportacion, FilaImportada, Importacion
from app.models.pago import Pago
from app.models.parametro import Configuracion, ParametroPrecio
from app.models.producto import MovimientoStock, Producto, ProductoAlias
from app.models.recordatorio import PlantillaMensaje, PlantillaVersion, Recordatorio
from app.models.tasa import TasaCambio
from app.models.usuario import RefreshToken, Socio, Usuario
from app.models.venta import Cuota, Venta, VentaItem

__all__ = [
    "AccionAuditoria",
    "ActorAuditoria",
    "CanalPago",
    "Cliente",
    "ClienteAlias",
    "Compra",
    "Conciliacion",
    "ConfianzaDato",
    "Configuracion",
    "Cuota",
    "EnlaceImportacion",
    "EstadoCobro",
    "EstadoProducto",
    "EstadoRecordatorio",
    "EstadoRegistro",
    "EventoAuditoria",
    "FilaImportada",
    "Gasto",
    "Importacion",
    "JobEjecucion",
    "LoteCompra",
    "MarcasDeTiempo",
    "MetodoEnlace",
    "ModeloPrecio",
    "Moneda",
    "MotivoOmision",
    "MovimientoStock",
    "NivelPrecio",
    "OrigenTasa",
    "Pago",
    "PagoCompra",
    "ParametroPrecio",
    "PlantillaMensaje",
    "PlantillaVersion",
    "Producto",
    "ProductoAlias",
    "Proveedor",
    "Recordatorio",
    "RefreshToken",
    "RolUsuario",
    "Socio",
    "TasaCambio",
    "TipoLineaLote",
    "TipoMovimientoPago",
    "TipoMovimientoStock",
    "TipoTasa",
    "Usuario",
    "Venta",
    "VentaItem",
    "enum_pg",
]
