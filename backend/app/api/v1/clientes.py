"""Clientes. Incluye la pantalla que desbloquea los recordatorios: cargar telefonos."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.deps import AdminOVendedor, PuedeEscribir, SesionDb, Usuario
from app.api.errors import Conflicto, ErrorNegocio, NoEncontrado
from app.core.normalizacion import TelefonoInvalido, clave_nombre, telefono_e164

router = APIRouter(prefix="/clientes", tags=["clientes"])


@router.get("")
def listar(
    db: SesionDb,
    actual: Usuario,
    q: str | None = None,
    sin_telefono: bool = False,
    con_deuda: bool = False,
    a_revisar: bool = False,
    limite: int = Query(default=100, le=500),
):
    """El filtro `sin_telefono=1&con_deuda=1` es la lista de trabajo inicial.

    Es la que la tarjeta roja del panel de calidad enlaza: 14 personas que deben
    plata y a las que todavia no se les puede escribir.
    """
    del actual
    condiciones, params = ["c.estado = 'activo'"], {"limite": limite}
    if q:
        condiciones.append(
            "(c.nombre_normalizado LIKE :q OR EXISTS (SELECT 1 FROM clientes_alias a "
            "WHERE a.cliente_id = c.id AND a.alias_normalizado LIKE :q))"
        )
        params["q"] = f"%{clave_nombre(q)}%"
    if sin_telefono:
        condiciones.append("c.telefono_e164 IS NULL")
    if a_revisar:
        condiciones.append("c.notas LIKE 'Revisar:%'")
    if con_deuda:
        condiciones.append("d.deuda_usd IS NOT NULL")

    filas = db.execute(
        text(
            f"""
            SELECT c.id, c.nombre, c.telefono_e164, c.telefono_verificado, c.email,
                   c.nivel_precio::text AS nivel_precio, c.es_socio, c.notas,
                   c.plazo_credito_dias,
                   COALESCE(d.deuda_usd, 0)        AS deuda_usd,
                   COALESCE(d.ventas_abiertas, 0)  AS ventas_abiertas,
                   COALESCE(d.dias_mora_maximo, 0) AS dias_mora_maximo,
                   (SELECT count(*) FROM ventas v WHERE v.cliente_id = c.id) AS compras,
                   (SELECT array_agg(a.alias ORDER BY a.alias) FROM clientes_alias a
                      WHERE a.cliente_id = c.id) AS alias
            FROM clientes c
            LEFT JOIN v_deuda_cliente d ON d.cliente_id = c.id
            WHERE {" AND ".join(condiciones)}
            ORDER BY COALESCE(d.dias_mora_maximo, -1) DESC, COALESCE(d.deuda_usd, 0) DESC,
                     c.nombre
            LIMIT :limite
            """
        ),
        params,
    ).all()
    return [dict(f._mapping) for f in filas]


class ClienteEntrada(BaseModel):
    nombre: str = Field(min_length=2, max_length=160)
    telefono: str | None = None
    email: str | None = None
    nivel_precio: str = Field(default="publico", pattern="^(publico|team|revendedor)$")
    plazo_credito_dias: int | None = Field(default=None, ge=0, le=365)
    notas: str | None = None


@router.post("", status_code=201)
def crear(datos: ClienteEntrada, db: SesionDb, actual: AdminOVendedor, _: PuedeEscribir):
    clave = clave_nombre(datos.nombre)
    if db.execute(
        text("SELECT 1 FROM clientes WHERE nombre_normalizado = :k AND estado <> 'fusionado'"),
        {"k": clave},
    ).scalar():
        raise Conflicto(
            "CLIENTE_DUPLICADO",
            f"Ya hay un cliente que se llama así ({datos.nombre}).",
            campo="nombre",
            sugerencia="Buscalo en la lista: quizá es el mismo.",
        )

    telefono = None
    if datos.telefono:
        try:
            telefono = telefono_e164(datos.telefono)
        except TelefonoInvalido as exc:
            raise ErrorNegocio(
                "TELEFONO_INVALIDO",
                str(exc),
                campo="telefono",
                sugerencia="Un móvil venezolano: 0412, 0414, 0416, 0424 o 0426.",
            ) from exc

    nuevo = db.execute(
        text(
            "INSERT INTO clientes (nombre, telefono_e164, email, nivel_precio, "
            "plazo_credito_dias, notas, creado_por_usuario_id) "
            "VALUES (:n, :t, :e, :nv, :p, :notas, :u) RETURNING id"
        ),
        {
            "n": datos.nombre.strip(),
            "t": telefono,
            "e": datos.email,
            "nv": datos.nivel_precio,
            "p": datos.plazo_credito_dias,
            "notas": datos.notas,
            "u": actual.id,
        },
    ).scalar_one()
    db.commit()
    return {"cliente_id": nuevo, "nombre": datos.nombre.strip(), "telefono_e164": telefono}


class TelefonoEntrada(BaseModel):
    telefono: str = Field(min_length=7)


@router.put("/{cliente_id}/telefono")
def guardar_telefono(
    cliente_id: int,
    datos: TelefonoEntrada,
    db: SesionDb,
    actual: AdminOVendedor,
    _: PuedeEscribir,
):
    """El endpoint que desbloquea la cobranza. Normaliza a E.164 antes de guardar."""
    del actual
    try:
        normalizado = telefono_e164(datos.telefono)
    except TelefonoInvalido as exc:
        raise ErrorNegocio(
            "TELEFONO_INVALIDO",
            str(exc),
            campo="telefono",
            sugerencia=(
                "Tiene que ser un móvil venezolano (0412, 0414, 0416, 0424 o 0426) "
                "para que WhatsApp lo reciba."
            ),
        ) from exc

    afectadas = db.execute(
        text("UPDATE clientes SET telefono_e164 = :t WHERE id = :i AND estado = 'activo'"),
        {"t": normalizado, "i": cliente_id},
    ).rowcount
    if not afectadas:
        raise NoEncontrado("ese cliente")
    db.commit()
    return {"cliente_id": cliente_id, "telefono_e164": normalizado}


@router.get("/{cliente_id}/timeline")
def timeline(cliente_id: int, db: SesionDb, actual: Usuario):
    """Ventas, pagos y recordatorios en una sola linea de tiempo.

    Es la pantalla que se abre cuando alguien discute un saldo.
    """
    del actual
    filas = db.execute(
        text(
            """
            SELECT * FROM (
                SELECT v.fecha::timestamptz AS cuando, 'venta' AS tipo, v.codigo AS referencia,
                       v.total_usd AS monto_usd, NULL::text AS moneda,
                       (SELECT string_agg(i.descripcion_libre, ', ') FROM venta_items i
                          WHERE i.venta_id = v.id) AS detalle,
                       v.estado_cobro::text AS estado
                FROM ventas v WHERE v.cliente_id = :c
                UNION ALL
                SELECT p.fecha::timestamptz, 'pago', COALESCE(p.referencia, p.canal::text),
                       p.monto_usd, p.moneda::text,
                       CASE WHEN p.moneda = 'VES'
                            THEN 'Bs. ' || p.monto_moneda || ' a ' || p.tasa_aplicada
                            ELSE p.moneda::text || ' ' || p.monto_moneda END,
                       p.tipo::text
                FROM pagos p JOIN ventas v ON v.id = p.venta_id WHERE v.cliente_id = :c
                UNION ALL
                SELECT r.generado_at, 'recordatorio', r.plantilla_clave,
                       r.saldo_usd_al_generar, NULL,
                       'Enviado a ' || COALESCE(r.destino, 'sin destino'), r.estado::text
                FROM recordatorios r WHERE r.cliente_id = :c
            ) t ORDER BY cuando DESC
            """
        ),
        {"c": cliente_id},
    ).all()
    return [dict(f._mapping) for f in filas]
