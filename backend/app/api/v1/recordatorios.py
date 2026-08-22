"""Recordatorios de WhatsApp.

No hay integracion con la API de WhatsApp, asi que el sistema genera el mensaje y un
link `wa.me` **con el numero del cliente** que un socio abre y envia. Cada
recordatorio viaja con una `accion` que dice como entregarlo, para que el dia que se
conecte un proveedor real el frontend no cambie: un solo componente decide entre
renderizar un `<a>` y disparar una mutacion.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.deps import AdminOVendedor, PuedeEscribir, SesionDb, SoloAdmin, Usuario
from app.schemas.comun import Esquema, Money
from app.services import recordatorios as svc
from app.services.plantillas import (
    VARIABLES_DISPONIBLES,
    leer_datos_pago,
    validar_cuerpo,
)

router = APIRouter(prefix="/recordatorios", tags=["recordatorios"])


class AccionSalida(Esquema):
    tipo: str
    url: str | None = None


class PreparadoSalida(Esquema):
    cliente_id: int
    cliente: str
    telefono_e164: str | None
    plantilla_clave: str
    cuerpo: str
    deuda_usd: Money
    dias_mora: int
    ventas: list[int]
    accion: AccionSalida
    avisos: list[str]


class OmitidoSalida(Esquema):
    cliente_id: int
    cliente: str
    motivo: str
    detalle: str
    forzable: bool


class LoteSalida(Esquema):
    resumen: str
    preparados: list[PreparadoSalida]
    omitidos: list[OmitidoSalida]


class LoteEntrada(BaseModel):
    cliente_ids: list[int] | None = Field(
        default=None, description="None = todos los que tienen deuda"
    )
    plantilla_clave: str | None = Field(
        default=None, description="None = la que corresponda al semáforo de cada uno"
    )
    incluir_socios: bool = False
    forzar: bool = Field(
        default=False, description="Ignora el cooldown. Solo admin, y queda registrado."
    )


@router.post("/previsualizar", response_model=LoteSalida)
def previsualizar(datos: LoteEntrada, db: SesionDb, actual: AdminOVendedor):
    """Arma los mensajes sin guardar nada. Es el preview del lote."""
    forzar = datos.forzar and actual.es_admin
    r = svc.preparar_lote(
        db,
        cliente_ids=datos.cliente_ids,
        plantilla_clave=datos.plantilla_clave,
        incluir_socios=datos.incluir_socios,
        forzar=forzar,
    )
    return LoteSalida(resumen=r.resumen, preparados=r.preparados, omitidos=r.omitidos)


@router.post("/lote", response_model=LoteSalida)
def generar_lote(
    datos: LoteEntrada, db: SesionDb, actual: AdminOVendedor, _: PuedeEscribir
):
    """Genera y guarda los recordatorios, con el cuerpo congelado.

    Los omitidos vuelven con su motivo en vez de hacer fallar el lote entero: 12
    seleccionados tienen que poder terminar en "9 listos, 2 en cooldown, 1 sin
    teléfono".
    """
    forzar = datos.forzar and actual.es_admin
    r = svc.preparar_lote(
        db,
        cliente_ids=datos.cliente_ids,
        plantilla_clave=datos.plantilla_clave,
        incluir_socios=datos.incluir_socios,
        forzar=forzar,
    )
    for preparado in r.preparados:
        svc.registrar(db, preparado, usuario_id=actual.id)
    db.commit()
    return LoteSalida(resumen=r.resumen, preparados=r.preparados, omitidos=r.omitidos)


@router.get("")
def listar(
    db: SesionDb,
    actual: AdminOVendedor,
    estado: str | None = None,
    cliente_id: int | None = None,
    limite: int = Query(default=100, le=500),
):
    del actual
    condiciones, params = ["TRUE"], {"limite": limite}
    if estado:
        condiciones.append("r.estado::text = :estado")
        params["estado"] = estado
    if cliente_id:
        condiciones.append("r.cliente_id = :cliente")
        params["cliente"] = cliente_id
    filas = db.execute(
        text(
            f"""
            SELECT r.id, r.cliente_id, c.nombre AS cliente, r.destino, r.venta_id,
                   r.plantilla_clave, r.plantilla_version, r.cuerpo_renderizado,
                   r.saldo_usd_al_generar, r.dias_mora_al_generar, r.estado::text AS estado,
                   r.generado_at, r.enviado_at, u.nombre AS generado_por
            FROM recordatorios r
            JOIN clientes c ON c.id = r.cliente_id
            LEFT JOIN usuarios u ON u.id = r.generado_por_usuario_id
            WHERE {" AND ".join(condiciones)}
            ORDER BY r.generado_at DESC LIMIT :limite
            """
        ),
        params,
    ).all()
    return [dict(f._mapping) for f in filas]


@router.post("/{recordatorio_id}/marcar-enviado", status_code=204)
def marcar_enviado(
    recordatorio_id: int, db: SesionDb, actual: AdminOVendedor, _: PuedeEscribir
):
    """Un deep link no confirma entrega: esto registra que un humano lo despachó."""
    svc.marcar_enviado(db, recordatorio_id, usuario_id=actual.id)
    db.commit()


@router.get("/plantillas")
def listar_plantillas(db: SesionDb, actual: Usuario):
    del actual
    filas = db.execute(
        text(
            "SELECT clave, nombre, canal, cuerpo, variables, version, activa, updated_at "
            "FROM plantillas_mensaje ORDER BY clave"
        )
    ).all()
    return {
        "variables_disponibles": [
            {"nombre": k, "descripcion": v} for k, v in sorted(VARIABLES_DISPONIBLES.items())
        ],
        "items": [dict(f._mapping) for f in filas],
    }


class PlantillaEntrada(BaseModel):
    cuerpo: str = Field(min_length=10)


@router.put("/plantillas/{clave}", status_code=204)
def guardar_plantilla(
    clave: str,
    datos: PlantillaEntrada,
    db: SesionDb,
    actual: SoloAdmin,
    _: PuedeEscribir,
):
    """Guarda una version nueva. Rechaza datos de pago escritos a mano.

    Es la segunda barrera del mismo bug: los datos van por `{{ datos_pago }}` desde la
    configuracion, y si alguien intenta escribirlos igual, no entra.
    """
    validar_cuerpo(datos.cuerpo)
    version = db.execute(
        text(
            "UPDATE plantillas_mensaje SET cuerpo = :c, version = version + 1, "
            "actualizado_por_usuario_id = :u WHERE clave = :k RETURNING version"
        ),
        {"c": datos.cuerpo, "u": actual.id, "k": clave},
    ).scalar_one()
    db.execute(
        text(
            "INSERT INTO plantillas_version (plantilla_clave, version, cuerpo, "
            "guardado_por_usuario_id) VALUES (:k, :v, :c, :u)"
        ),
        {"k": clave, "v": version, "c": datos.cuerpo, "u": actual.id},
    )
    db.commit()


@router.get("/datos-pago")
def datos_pago(db: SesionDb, actual: Usuario):
    """`completo` es lo que la UI usa para bloquear todos los botones de enviar."""
    del actual
    dp = leer_datos_pago(db)
    return {"campos": dp.campos, "faltantes": dp.faltantes, "completo": dp.completo}
