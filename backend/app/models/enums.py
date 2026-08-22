"""Enums del dominio, nativos de Postgres.

Nativos y no `VARCHAR` + CHECK a propósito: el vocabulario queda descubrible con
`SELECT unnest(enum_range(NULL::estado_cobro))` y no puede derivar. Hoy la base
tiene tres vocabularios distintos para la misma idea —`ventas.estatus ∈
{PENDIENTE, YA PAGO}`, `compras.estatus ∈ {PENDIENTE, PAGADO}` y
`cuotas.estado = 'pendiente'`— que es exactamente lo que esto cierra.
"""

from __future__ import annotations

from enum import StrEnum


class RolUsuario(StrEnum):
    ADMIN = "admin"
    VENDEDOR = "vendedor"
    AFILIADO = "afiliado"


class EstadoProducto(StrEnum):
    ACTIVO = "activo"
    BORRADOR_POR_REVISAR = "borrador_por_revisar"
    DESCATALOGADO = "descatalogado"
    FUSIONADO = "fusionado"


class ModeloPrecio(StrEnum):
    """Cómo se calcula el precio de este producto.

    COSTO: Top Quality -> precio = costo × (1 + ganancia)
    LISTA: Originales   -> precio dado; los descuentos se derivan de él
    """

    COSTO = "costo"
    LISTA = "lista"


class NivelPrecio(StrEnum):
    PUBLICO = "publico"
    TEAM = "team"
    REVENDEDOR = "revendedor"


class Moneda(StrEnum):
    USD = "USD"
    VES = "VES"
    USDT = "USDT"


class CanalPago(StrEnum):
    PAGO_MOVIL = "pago_movil"
    TRANSFERENCIA = "transferencia"
    EFECTIVO_USD = "efectivo_usd"
    EFECTIVO_BS = "efectivo_bs"
    BINANCE = "binance"
    USDT = "usdt"
    ZELLE = "zelle"
    OTRO = "otro"


class EstadoCobro(StrEnum):
    """El tercer estado, `PENDIENTE_SIN_ABONOS`, es el que el Excel usaba y la app perdió."""

    PAGADA = "pagada"
    PENDIENTE_SIN_ABONOS = "pendiente_sin_abonos"
    PENDIENTE_PARCIAL = "pendiente_parcial"
    ANULADA = "anulada"


class TipoMovimientoPago(StrEnum):
    ABONO = "abono"
    REVERSO = "reverso"
    AJUSTE = "ajuste"


class TipoTasa(StrEnum):
    BCV = "bcv"
    BINANCE = "binance"
    USDT_VE = "usdt_ve"
    PARALELO = "paralelo"


class OrigenTasa(StrEnum):
    """`SINTETIZADA_MIGRACION` marca las 29 tasas que `migrate_excel.py` despejó de
    una heurística en vez de registrar. No se borran: se etiquetan."""

    API_USDTVE = "api_usdtve"
    API_DOLARAPI = "api_dolarapi"
    MANUAL = "manual"
    SEED_HISTORICO = "seed_historico"
    SINTETIZADA_MIGRACION = "sintetizada_migracion"


class ConfianzaDato(StrEnum):
    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"


class TipoLineaLote(StrEnum):
    ENCABEZADO = "encabezado"
    ITEM = "item"
    SUBTOTAL = "subtotal"
    GASTO = "gasto"


class EstadoRecordatorio(StrEnum):
    """El ciclo completo desde el día uno, aunque el proveedor manual solo llegue
    a ENVIADO: enchufar la WhatsApp Cloud API no debe requerir una migración."""

    BORRADOR = "borrador"
    LISTO = "listo"
    ENVIANDO = "enviando"
    ENVIADO = "enviado"
    ENTREGADO = "entregado"
    LEIDO = "leido"
    FALLIDO = "fallido"
    OMITIDO = "omitido"


class MotivoOmision(StrEnum):
    COOLDOWN = "cooldown"
    SIN_TELEFONO = "sin_telefono"
    YA_PAGADO = "ya_pagado"
    LIMITE_MENSUAL = "limite_mensual"
    MANUAL = "manual"


class TipoMovimientoStock(StrEnum):
    COMPRA = "compra"
    VENTA = "venta"
    AJUSTE = "ajuste"
    DEVOLUCION = "devolucion"
    MUESTRA = "muestra"
    CARGA_INICIAL = "carga_inicial"


class AccionAuditoria(StrEnum):
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


class ActorAuditoria(StrEnum):
    USUARIO = "usuario"
    SISTEMA = "sistema"
    MIGRACION = "migracion"


class MetodoEnlace(StrEnum):
    EXACTO = "exacto"
    FUZZY = "fuzzy"
    MANUAL = "manual"
    HEURISTICA = "heuristica"


class EstadoRegistro(StrEnum):
    ACTIVO = "activo"
    INACTIVO = "inactivo"
    FUSIONADO = "fusionado"


# Nombres de los tipos en Postgres. Alembic los crea una sola vez con estos nombres.
NOMBRES_ENUM: dict[type[StrEnum], str] = {
    RolUsuario: "rol_usuario",
    EstadoProducto: "estado_producto",
    ModeloPrecio: "modelo_precio",
    NivelPrecio: "nivel_precio",
    Moneda: "moneda",
    CanalPago: "canal_pago",
    EstadoCobro: "estado_cobro",
    TipoMovimientoPago: "tipo_movimiento_pago",
    TipoTasa: "tipo_tasa",
    OrigenTasa: "origen_tasa",
    ConfianzaDato: "confianza_dato",
    TipoLineaLote: "tipo_linea_lote",
    EstadoRecordatorio: "estado_recordatorio",
    MotivoOmision: "motivo_omision",
    TipoMovimientoStock: "tipo_movimiento_stock",
    AccionAuditoria: "accion_auditoria",
    ActorAuditoria: "actor_auditoria",
    MetodoEnlace: "metodo_enlace",
    EstadoRegistro: "estado_registro",
}
