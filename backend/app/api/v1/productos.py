"""Catalogo, autocompletado y el alta rapida.

`GET /productos/sugerencias` es lo que hace posible el requerimiento de registrar una
venta sin que el producto este en el catalogo: devuelve las coincidencias por alias,
los similares para la guardia de "¿quisiste decir...?", y el precio de politica de
cada uno para el nivel elegido.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.deps import AdminOVendedor, PuedeEscribir, SesionDb, SoloAdmin, Usuario
from app.core.normalizacion import clave_nombre
from app.schemas.comun import Esquema, Money

router = APIRouter(prefix="/productos", tags=["productos"])


class Similar(Esquema):
    producto_id: int
    nombre: str
    puntaje: float
    ventas: int


class Sugerencia(Esquema):
    producto_id: int
    nombre: str
    linea: str | None
    estado: str
    stock: int
    costo_usd: Money | None
    precio_politica_usd: Money | None
    sin_base_de_precio: bool
    #: Cuando el nombre buscado llego por un alias y no por el nombre canonico.
    coincide_por_alias: str | None = None


class RespuestaSugerencias(Esquema):
    exactos: list[Sugerencia]
    similares: list[Similar]
    #: Lo que la UI muestra como "+ Crear «X»" cuando no hay exacto.
    puede_crear: bool
    nombre_propuesto: str | None


@router.get("/sugerencias", response_model=RespuestaSugerencias)
def sugerencias(
    db: SesionDb,
    actual: Usuario,
    q: str = Query(min_length=1),
    moneda: str = Query(default="VES", description="VES o USD: define el nivel de precio"),
    limite: int = Query(default=15, le=50),
):
    clave = clave_nombre(q)
    columna_precio = "precio_bcv_usd" if moneda == "VES" else "precio_divisa_usd"

    exactos = db.execute(
        text(
            f"""
            SELECT DISTINCT ON (p.producto_id)
                   p.producto_id, p.nombre, p.linea, p.estado::text AS estado, p.stock,
                   p.costo_usd, COALESCE(p.{columna_precio}, p.precio_publico_usd)
                       AS precio_politica_usd,
                   p.sin_base_de_precio,
                   CASE WHEN a.alias_normalizado <> p.nombre_normalizado THEN a.alias END
                       AS coincide_por_alias
            FROM productos_alias a
            JOIN v_precio_vigente p ON p.producto_id = a.producto_id
            WHERE a.alias_normalizado LIKE :prefijo
            ORDER BY p.producto_id, length(p.nombre)
            LIMIT :limite
            """
        ),
        {"prefijo": f"{clave}%", "limite": limite},
    ).all()

    # Similares por trigram: alimenta el aviso "¿quisiste decir ACQUA DI GIO?", que
    # ataca el problema de las 21 grafias en la tecla y no en una limpieza posterior.
    similares = db.execute(
        text(
            """
            SELECT p.id AS producto_id, p.nombre,
                   similarity(p.nombre_normalizado, :clave) AS puntaje,
                   (SELECT count(*) FROM venta_items i WHERE i.producto_id = p.id) AS ventas
            FROM productos p
            WHERE p.estado <> 'fusionado'
              AND p.nombre_normalizado % :clave
              AND p.nombre_normalizado NOT LIKE :prefijo
            ORDER BY puntaje DESC LIMIT 5
            """
        ),
        {"clave": clave, "prefijo": f"{clave}%"},
    ).all()

    return RespuestaSugerencias(
        exactos=[dict(f._mapping) for f in exactos],
        similares=[dict(f._mapping) for f in similares],
        puede_crear=not any(f.nombre_normalizado == clave for f in [])
        and not any(clave_nombre(f.nombre) == clave for f in exactos),
        nombre_propuesto=q.strip() or None,
    )


class AltaRapidaEntrada(BaseModel):
    nombre: str = Field(min_length=2, max_length=200)
    costo_usd: Decimal | None = Field(default=None, ge=0)


@router.post("/alta-rapida", status_code=201)
def alta_rapida(datos: AltaRapidaEntrada, db: SesionDb, actual: AdminOVendedor, _: PuedeEscribir):
    """Crea un producto en borrador desde el formulario de venta.

    **Nada bloquea.** Si el nombre normalizado ya existe se devuelve el que hay, asi
    el mismo tipeo dos veces no genera dos borradores. El costo es opcional: sin
    costo el producto queda en revision, que es trabajo visible, no un error.
    """
    clave = clave_nombre(datos.nombre)
    existente = db.execute(
        text(
            "SELECT id, nombre, estado::text AS estado FROM productos "
            "WHERE nombre_normalizado = :k AND estado <> 'fusionado' LIMIT 1"
        ),
        {"k": clave},
    ).one_or_none()
    if existente:
        return {
            "producto_id": existente.id,
            "nombre": existente.nombre,
            "estado": existente.estado,
            "ya_existia": True,
        }

    estado = "activo" if datos.costo_usd is not None else "borrador_por_revisar"
    nuevo = db.execute(
        text(
            "INSERT INTO productos (nombre, costo_usd, estado, origen_alta, "
            "creado_por_usuario_id, notas, costo, precio_divisa, precio_bcv, stock, "
            "precio_unitario, precio_original, precio_team, precio_revendedor) "
            "VALUES (:n, :c, :e, 'venta_rapida', :u, :notas, 0,0,0,0,0,0,0,0) RETURNING id"
        ),
        {
            "n": datos.nombre.strip(),
            "c": datos.costo_usd,
            "e": estado,
            "u": actual.id,
            "notas": (
                None
                if datos.costo_usd is not None
                else "Creado desde una venta, sin costo. Cargalo para que salga de revisión."
            ),
        },
    ).scalar_one()
    db.commit()
    return {
        "producto_id": nuevo,
        "nombre": datos.nombre.strip(),
        "estado": estado,
        "ya_existia": False,
    }


@router.get("")
def listar(
    db: SesionDb,
    actual: Usuario,
    q: str | None = None,
    sin_costo: bool = False,
    por_revisar: bool = False,
    incluir_descatalogados: bool = False,
    limite: int = Query(default=100, le=500),
):
    # Un producto descatalogado no se ofrece al vender: si siguiera apareciendo,
    # desactivarlo no serviria de nada. Se puede pedir explicitamente para poder
    # verlo y reactivarlo desde la pantalla de productos.
    condiciones, params = [
        "TRUE" if incluir_descatalogados else "estado <> 'descatalogado'"
    ], {"limite": limite}
    if q:
        condiciones.append("nombre_normalizado LIKE :q")
        params["q"] = f"%{clave_nombre(q)}%"
    if sin_costo:
        condiciones.append("sin_base_de_precio")
    if por_revisar:
        condiciones.append("estado = 'borrador_por_revisar'")

    filas = db.execute(
        text(
            f"SELECT * FROM v_precio_vigente WHERE {' AND '.join(condiciones)} "
            "ORDER BY nombre LIMIT :limite"
        ),
        params,
    ).all()
    items = [dict(f._mapping) for f in filas]
    if not actual.ve_costos:
        # El costo no se oculta con CSS: no entra en la respuesta.
        for i in items:
            i.pop("costo_usd", None)
            i.pop("precio_original_usd", None)
    return items


@router.get("/revision")
def por_revisar(db: SesionDb, actual: SoloAdmin, limite: int = Query(default=200, le=500)):
    """La cola de revisión: productos creados al vuelo o sin costo."""
    del actual
    filas = db.execute(
        text(
            "SELECT p.id, p.nombre, p.linea, p.costo_usd, p.origen_alta, p.notas, "
            "p.created_at, (SELECT count(*) FROM venta_items i WHERE i.producto_id = p.id) "
            "AS ventas FROM productos p WHERE p.estado = 'borrador_por_revisar' "
            "ORDER BY ventas DESC, p.created_at DESC LIMIT :l"
        ),
        {"l": limite},
    ).all()
    return [dict(f._mapping) for f in filas]


class FusionEntrada(BaseModel):
    destino_id: int
    motivo: str = Field(min_length=3)


@router.post("/{producto_id}/fusionar", status_code=204)
def fusionar(
    producto_id: int,
    datos: FusionEntrada,
    db: SesionDb,
    actual: SoloAdmin,
    _: PuedeEscribir,
):
    """Fusiona un producto en otro y repunta las lineas de venta.

    El nombre del perdedor queda como alias del sobreviviente, asi que el historico
    sigue resolviendo y `descripcion_libre` conserva lo que se tecleo.
    """
    from app.api.errors import Conflicto, NoEncontrado

    if producto_id == datos.destino_id:
        raise Conflicto("FUSION_A_SI_MISMO", "Un producto no se puede fusionar consigo mismo.")

    perdedor = db.execute(
        text("SELECT id, nombre, es_original FROM productos WHERE id = :i"), {"i": producto_id}
    ).one_or_none()
    if perdedor is None:
        raise NoEncontrado("ese producto")
    if (
        db.execute(
            text("SELECT 1 FROM productos WHERE id = :i AND estado <> 'fusionado'"),
            {"i": datos.destino_id},
        ).scalar()
        is None
    ):
        raise NoEncontrado("el producto destino")

    db.execute(
        text("UPDATE venta_items SET producto_id = :d WHERE producto_id = :p"),
        {"d": datos.destino_id, "p": producto_id},
    )
    db.execute(
        text("UPDATE productos_alias SET producto_id = :d WHERE producto_id = :p"),
        {"d": datos.destino_id, "p": producto_id},
    )
    db.execute(
        text(
            "UPDATE productos SET estado = 'fusionado', fusionado_en_producto_id = :d, "
            "notas = coalesce(notas || ' | ', '') || :motivo WHERE id = :p"
        ),
        {"d": datos.destino_id, "p": producto_id, "motivo": f"Fusionado: {datos.motivo}"},
    )
    db.commit()


class ProductoActualizar(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=200)
    linea: str | None = Field(default=None, max_length=80)
    categoria: str | None = Field(default=None, max_length=80)
    costo_usd: Decimal | None = Field(default=None, ge=0)
    precio_original_usd: Decimal | None = Field(default=None, ge=0)
    modelo_precio: str | None = Field(default=None, pattern="^(costo|lista)$")
    stock_minimo: int | None = Field(default=None, ge=0, le=100000)
    estado: str | None = Field(
        default=None, pattern="^(activo|borrador_por_revisar|descatalogado)$"
    )
    notas: str | None = Field(default=None, max_length=2000)


@router.put("/{producto_id}")
def actualizar(
    producto_id: int,
    datos: ProductoActualizar,
    db: SesionDb,
    actual: SoloAdmin,
    _: PuedeEscribir,
):
    """Edita la ficha y saca el producto de revisión cuando ya tiene base de precio."""
    from app.api.errors import ErrorNegocio, NoEncontrado

    existe = db.execute(
        text(
            "SELECT id, nombre, es_original FROM productos WHERE id = :i AND estado <> 'fusionado'"
        ),
        {"i": producto_id},
    ).one_or_none()
    if existe is None:
        raise NoEncontrado("ese producto")
    cambios = datos.model_dump(exclude_unset=True)
    if not cambios:
        return {"producto_id": producto_id}
    if cambios.get("modelo_precio") == "lista" and cambios.get("precio_original_usd") is None:
        actual_lista = db.execute(
            text("SELECT precio_original_usd FROM productos WHERE id=:i"),
            {"i": producto_id},
        ).scalar()
        if actual_lista is None:
            raise ErrorNegocio(
                "LISTA_SIN_PRECIO",
                "Un perfume original necesita su precio de lista.",
                campo="precio_original_usd",
            )
    permitidos = {
        "nombre",
        "linea",
        "categoria",
        "costo_usd",
        "precio_original_usd",
        "modelo_precio",
        "stock_minimo",
        "estado",
        "notas",
    }
    asignaciones, params = [], {"id": producto_id, "usuario": actual.id}
    for campo, valor in cambios.items():
        if campo in permitidos:
            asignaciones.append(f"{campo} = :{campo}")
            params[campo] = valor.strip() if isinstance(valor, str) and campo != "notas" else valor
    if "nombre" in cambios:
        asignaciones.append("nombre_normalizado = :nombre_normalizado")
        params["nombre_normalizado"] = clave_nombre(cambios["nombre"])
    tiene_base = (
        cambios.get("costo_usd") is not None or cambios.get("precio_original_usd") is not None
    )
    if tiene_base and "estado" not in cambios:
        asignaciones.append("estado = 'activo'")
    asignaciones.extend(["revisado_at = now()", "revisado_por_usuario_id = :usuario"])
    db.execute(text(f"UPDATE productos SET {', '.join(asignaciones)} WHERE id = :id"), params)
    if "nombre" in cambios:
        db.execute(
            text(
                """
                INSERT INTO productos_alias
                  (producto_id, alias, alias_normalizado, es_original, origen)
                VALUES (:p, :a, :k, :o, 'edicion_manual')
                ON CONFLICT (alias_normalizado, es_original)
                DO UPDATE SET producto_id = EXCLUDED.producto_id, alias = EXCLUDED.alias
                """
            ),
            {
                "p": producto_id,
                "a": cambios["nombre"],
                "k": clave_nombre(cambios["nombre"]),
                "o": existe.es_original,
            },
        )
    db.commit()
    return {"producto_id": producto_id, "actualizado": list(cambios)}


class AjusteStockEntrada(BaseModel):
    stock_nuevo: int = Field(ge=0, le=1_000_000)
    motivo: str = Field(min_length=3, max_length=300)


@router.post("/{producto_id}/ajustar-stock", status_code=201)
def ajustar_stock(
    producto_id: int,
    datos: AjusteStockEntrada,
    db: SesionDb,
    actual: SoloAdmin,
    _: PuedeEscribir,
):
    from app.api.errors import ErrorNegocio, NoEncontrado

    producto = db.execute(
        text("SELECT id, stock FROM productos WHERE id=:i AND estado <> 'fusionado' FOR UPDATE"),
        {"i": producto_id},
    ).one_or_none()
    if producto is None:
        raise NoEncontrado("ese producto")
    diferencia = datos.stock_nuevo - producto.stock
    if diferencia == 0:
        raise ErrorNegocio("STOCK_SIN_CAMBIO", "El conteo coincide con el stock actual.")
    movimiento = db.execute(
        text(
            """
            INSERT INTO movimientos_stock
              (producto_id, tipo, cantidad, saldo_despues, referencia_tabla,
               usuario_id, notas)
            VALUES (:p, 'ajuste', :d, :s, 'conteo_fisico', :u, :m) RETURNING id
            """
        ),
        {
            "p": producto_id,
            "d": diferencia,
            "s": datos.stock_nuevo,
            "u": actual.id,
            "m": datos.motivo,
        },
    ).scalar_one()
    db.commit()
    return {"movimiento_id": movimiento, "stock_nuevo": datos.stock_nuevo}
