"""Esquemas de cobranza y calidad de datos."""

from __future__ import annotations

from datetime import date, datetime

from app.schemas.comun import Esquema, Metrica, Money


class Tramo(Esquema):
    clave: str
    etiqueta: str
    cantidad: int
    monto_usd: Money


class VentaEnCobranza(Esquema):
    venta_id: int
    codigo: str
    fecha: date
    producto: str | None = None
    total_usd: Money
    saldo_usd: Money
    fecha_vencimiento: date
    dias_mora: int
    semaforo: str
    cantidad_abonos: int


class ClienteEnCobranza(Esquema):
    cliente_id: int
    cliente: str
    telefono_e164: str | None
    puede_notificar: bool
    es_socio: bool
    vendedor: str | None = None
    ventas_abiertas: int
    deuda_usd: Money
    dias_mora_maximo: int
    vencimiento_mas_viejo: date | None
    ultimo_abono_fecha: date | None
    ultimo_recordatorio_at: datetime | None
    nunca_abono: bool
    semaforo: str
    etiqueta_semaforo: str
    ventas: list[VentaEnCobranza]


class ResumenCobranzaSalida(Esquema):
    metricas: list[Metrica]
    tramos: list[Tramo]
    semaforos: list[Tramo]
    calculado_at: datetime


class TarjetaCalidad(Esquema):
    """Una tarjeta del panel de calidad.

    `severidad` mapea al color: critica = roja, alta = ambar, media = neutra.
    `accion` y `ruta` son lo que la convierte en trabajo y no en una queja.
    """

    clave: str
    etiqueta: str
    severidad: str
    cantidad: int
    monto_usd: Money | None
    explicacion: str
    accion: str
    ruta: str
