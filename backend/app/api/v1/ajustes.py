"""Ajustes: datos de pago, parametros de precio y tasas."""

from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from app.api.deps import PuedeEscribir, SesionDb, SoloAdmin, Usuario
from app.models.parametro import CLAVE_DATOS_PAGO
from app.services.parametros import parametros_vigentes
from app.services.plantillas import leer_datos_pago

router = APIRouter(prefix="/ajustes", tags=["ajustes"])

#: Bancos venezolanos por codigo. Se elige de una lista, no se teclea: el codigo mal
#: puesto es un pago que no llega.
BANCOS = {
    "0102": "Banco de Venezuela",
    "0104": "Venezolano de Crédito",
    "0105": "Mercantil",
    "0108": "Provincial",
    "0114": "Bancaribe",
    "0115": "Exterior",
    "0128": "Banco Caroní",
    "0134": "Banesco",
    "0137": "Sofitasa",
    "0138": "Banco Plaza",
    "0151": "BFC Banco Fondo Común",
    "0156": "100% Banco",
    "0163": "Banco del Tesoro",
    "0166": "Banco Agrícola",
    "0168": "Bancrecer",
    "0169": "Mi Banco",
    "0171": "Banco Activo",
    "0172": "Bancamiga",
    "0174": "Banplus",
    "0175": "Banco Bicentenario",
    "0177": "Banfanb",
    "0191": "BNC Banco Nacional de Crédito",
}


class DatosPagoEntrada(BaseModel):
    titular: str = Field(min_length=3, max_length=120)
    codigo_banco: str = Field(pattern=r"^\d{4}$")
    documento: str = Field(min_length=7, max_length=20)
    telefono: str = Field(min_length=10, max_length=20)

    @field_validator("documento")
    @classmethod
    def _documento(cls, v: str) -> str:
        limpio = v.strip().upper().replace(" ", "")
        if not re.fullmatch(r"[VEJPG]-?\d{6,9}", limpio.replace(".", "")):
            raise ValueError(
                "El documento tiene que ser tipo V-12345678 (V, E, J, P o G y 6 a 9 dígitos)."
            )
        if re.search(r"X{2,}", limpio):
            raise ValueError("Ese documento tiene marcadores de relleno.")
        return limpio

    @field_validator("telefono")
    @classmethod
    def _telefono(cls, v: str) -> str:
        digitos = re.sub(r"\D", "", v)
        if not re.fullmatch(r"0(412|414|416|424|426)\d{7}", digitos):
            raise ValueError(
                "Tiene que ser un móvil venezolano: 0412, 0414, 0416, 0424 o 0426."
            )
        return f"{digitos[:4]}-{digitos[4:]}"

    @field_validator("codigo_banco")
    @classmethod
    def _banco(cls, v: str) -> str:
        if v not in BANCOS:
            raise ValueError(f"No conozco el código de banco {v}.")
        return v


@router.get("/pagos")
def obtener_datos_pago(db: SesionDb, actual: Usuario):
    """`completo` es lo que bloquea todos los botones de enviar recordatorio."""
    del actual
    dp = leer_datos_pago(db)
    return {
        "campos": dp.campos,
        "faltantes": dp.faltantes,
        "completo": dp.completo,
        "bloquea_recordatorios": not dp.completo,
        "vista_previa": dp.como_bloque() if dp.completo else None,
        "bancos": [{"codigo": c, "nombre": n} for c, n in sorted(BANCOS.items())],
    }


@router.put("/pagos")
def guardar_datos_pago(
    datos: DatosPagoEntrada, db: SesionDb, actual: SoloAdmin, _: PuedeEscribir
):
    """Guardarlos acá es lo que desbloquea la cobranza por WhatsApp."""
    valor = {
        "titular": datos.titular.strip(),
        "banco": BANCOS[datos.codigo_banco],
        "codigo_banco": datos.codigo_banco,
        "documento": datos.documento,
        "telefono": datos.telefono,
    }
    db.execute(
        text(
            "INSERT INTO configuracion (clave, valor, actualizado_por_usuario_id) "
            "VALUES (:k, CAST(:v AS jsonb), :u) "
            "ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor, "
            "actualizado_por_usuario_id = EXCLUDED.actualizado_por_usuario_id, "
            "updated_at = now()"
        ),
        {"k": CLAVE_DATOS_PAGO, "v": json.dumps(valor), "u": actual.id},
    )
    db.commit()
    dp = leer_datos_pago(db)
    return {"completo": dp.completo, "vista_previa": dp.como_bloque()}


@router.get("/politica")
def politica(db: SesionDb, actual: SoloAdmin, en_fecha: date | None = None):
    """Los parámetros vigentes, con lo que significan en plata."""
    del actual
    p = parametros_vigentes(db, en_fecha)
    ejemplo = Decimal("12.00")
    return {
        "parametros": [
            {"clave": k, "valor": v} for k, v in sorted(p.items())
        ],
        "ejemplo": {
            "costo_usd": str(ejemplo),
            "precio_divisa_usd": str(round(ejemplo * (1 + p["GANANCIA_DIVISA"]), 2)),
            "precio_bcv_usd": str(round(ejemplo * (1 + p["GANANCIA_BCV"]), 2)),
            "explicacion": (
                "La ganancia se mide sobre el COSTO, no sobre el precio de venta. "
                "Es como el negocio la define."
            ),
        },
    }


class ParametroEntrada(BaseModel):
    clave: str = Field(min_length=3, max_length=48)
    valor: Decimal
    desde: date
    motivo: str = Field(min_length=5)


@router.post("/politica", status_code=201)
def cambiar_parametro(
    datos: ParametroEntrada, db: SesionDb, actual: SoloAdmin, _: PuedeEscribir
):
    """Cierra la vigencia anterior y abre una nueva. El historial queda entero.

    Por eso cambiar la ganancia deja de ser irreversible: el margen de una venta de
    hace un mes se sigue calculando con el parámetro que regía ese día.
    """
    db.execute(
        text(
            "UPDATE parametros_precio SET vigencia = daterange(lower(vigencia), :desde) "
            "WHERE clave = :k AND upper_inf(vigencia)"
        ),
        {"k": datos.clave, "desde": datos.desde},
    )
    nuevo = db.execute(
        text(
            "INSERT INTO parametros_precio (clave, valor, vigencia, motivo, "
            "creado_por_usuario_id) VALUES (:k, :v, daterange(:desde, NULL), :m, :u) "
            "RETURNING id"
        ),
        {"k": datos.clave, "v": datos.valor, "desde": datos.desde, "m": datos.motivo,
         "u": actual.id},
    ).scalar_one()
    db.commit()
    return {"parametro_id": nuevo, "clave": datos.clave, "valor": datos.valor}


@router.get("/tasas")
def tasas(db: SesionDb, actual: Usuario, limite: int = 30):
    del actual
    filas = db.execute(
        text(
            "SELECT fecha, tipo::text AS tipo, valor, origen::text AS origen, "
            "confianza::text AS confianza, capturado_at FROM tasas_cambio "
            "ORDER BY fecha DESC, tipo LIMIT :l"
        ),
        {"l": limite},
    ).all()
    return [dict(f._mapping) for f in filas]
