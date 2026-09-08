"""Proveedores, lotes de compra y cuentas por pagar."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.deps import PuedeEscribir, SesionDb, SoloAdmin
from app.api.errors import ErrorNegocio, NoEncontrado
from app.core.normalizacion import TelefonoInvalido, clave_nombre, telefono_e164
from app.models.enums import CanalPago

router = APIRouter(prefix="/compras", tags=["compras"])


class ProveedorEntrada(BaseModel):
    nombre: str = Field(min_length=2, max_length=200)
    contacto: str | None = Field(default=None, max_length=200)
    telefono: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=200)
    notas: str | None = Field(default=None, max_length=1000)


@router.get("/proveedores")
def proveedores(db: SesionDb, actual: SoloAdmin, q: str | None = None):
    del actual
    filtro, params = "", {}
    if q:
        filtro, params = "AND p.nombre_normalizado LIKE :q", {"q": f"%{clave_nombre(q)}%"}
    filas = (
        db.execute(
            text(
                f"""
            SELECT p.id, p.nombre, p.contacto, p.telefono, p.telefono_e164, p.email,
                   p.notas, count(DISTINCT l.id) AS lotes,
                   COALESCE(sum(cp.saldo_usd), 0) AS saldo_usd
              FROM proveedores p LEFT JOIN lotes_compra l ON l.proveedor_id = p.id
              LEFT JOIN v_cuentas_pagar cp ON cp.lote_id = l.id
             WHERE p.estado = 'activo' {filtro}
             GROUP BY p.id ORDER BY p.nombre
            """
            ),
            params,
        )
        .mappings()
        .all()
    )
    return [dict(f) for f in filas]


@router.post("/proveedores", status_code=201)
def crear_proveedor(datos: ProveedorEntrada, db: SesionDb, actual: SoloAdmin, _: PuedeEscribir):
    del actual
    try:
        telefono_normalizado = telefono_e164(datos.telefono) if datos.telefono else None
    except TelefonoInvalido as exc:
        raise ErrorNegocio("TELEFONO_INVALIDO", str(exc), campo="telefono") from exc
    nuevo = (
        db.execute(
            text(
                """
            INSERT INTO proveedores
              (nombre, nombre_normalizado, contacto, telefono, telefono_e164, email, notas)
            VALUES (:n, :k, :c, :t, :te, :e, :notas)
            RETURNING id, nombre
            """
            ),
            {
                "n": datos.nombre.strip(),
                "k": clave_nombre(datos.nombre),
                "c": datos.contacto,
                "t": datos.telefono,
                "te": telefono_normalizado,
                "e": datos.email,
                "notas": datos.notas,
            },
        )
        .mappings()
        .one()
    )
    db.commit()
    return dict(nuevo)


class LineaCompraEntrada(BaseModel):
    producto_id: int | None = None
    descripcion: str = Field(min_length=2, max_length=200)
    cantidad: int = Field(default=1, ge=1, le=10000)
    costo_unitario_usd: Decimal = Field(ge=0)
    actualizar_costo: bool = True


#: De la condicion depende si el monto sale del fondo hoy o entra a cuentas por
#: pagar. `consignacion` es el caso raro: la mercancia esta, pero no se debe hasta
#: venderla.
CONDICIONES = ("contado", "credito", "consignacion", "anticipo")


class LoteEntrada(BaseModel):
    codigo: str = Field(min_length=2, max_length=64)
    fecha: date = Field(default_factory=date.today)
    proveedor_id: int | None = None
    condicion: str | None = Field(default=None, pattern="^(contado|credito|consignacion|anticipo)$")
    canal: CanalPago | None = None
    subtotal_declarado_usd: Decimal | None = Field(default=None, ge=0)
    notas: str | None = Field(default=None, max_length=2000)
    lineas: list[LineaCompraEntrada] = Field(min_length=1, max_length=200)
    pago_inicial_usd: Decimal | None = Field(default=None, ge=0)
    referencia: str | None = Field(default=None, max_length=64)


@router.put("/proveedores/{proveedor_id}")
def editar_proveedor(
    proveedor_id: int,
    datos: ProveedorEntrada,
    db: SesionDb,
    actual: SoloAdmin,
    _: PuedeEscribir,
):
    """Corrige los datos de un proveedor. El nombre normalizado se recalcula.

    Se valida el telefono con el mismo camino que el alta: un numero que no pasa a
    E.164 no se guarda a medias.
    """
    del actual
    existe = db.execute(
        text("SELECT 1 FROM proveedores WHERE id = :i"), {"i": proveedor_id}
    ).scalar()
    if not existe:
        raise NoEncontrado("ese proveedor")

    e164 = None
    if datos.telefono:
        try:
            e164 = telefono_e164(datos.telefono)
        except TelefonoInvalido as exc:
            raise ErrorNegocio(
                "TELEFONO_INVALIDO", str(exc), campo="telefono"
            ) from exc

    db.execute(
        text(
            "UPDATE proveedores SET nombre = :n, nombre_normalizado = :k, "
            "contacto = :c, telefono = :t, telefono_e164 = :e, email = :m, "
            "notas = :o, updated_at = now() WHERE id = :i"
        ),
        {
            "n": datos.nombre.strip(),
            "k": clave_nombre(datos.nombre),
            "c": datos.contacto,
            "t": datos.telefono,
            "e": e164,
            "m": datos.email,
            "o": datos.notas,
            "i": proveedor_id,
        },
    )
    db.commit()
    return {"proveedor_id": proveedor_id, "nombre": datos.nombre.strip()}


@router.post("", status_code=201)
def registrar(datos: LoteEntrada, db: SesionDb, actual: SoloAdmin, _: PuedeEscribir):
    if (
        datos.proveedor_id is not None
        and not db.execute(
            text("SELECT 1 FROM proveedores WHERE id = :i AND estado = 'activo'"),
            {"i": datos.proveedor_id},
        ).scalar()
    ):
        raise NoEncontrado("ese proveedor")

    lote = db.execute(
        text(
            """
            INSERT INTO lotes_compra
              (codigo, fecha, proveedor_id, condicion, canal, subtotal_declarado_usd, notas)
            VALUES (:codigo, :fecha, :proveedor, CAST(:condicion AS condicion_compra),
                    :canal, :declarado, :notas) RETURNING id
            """
        ),
        {
            "codigo": datos.codigo.strip(),
            "fecha": datos.fecha,
            "proveedor": datos.proveedor_id,
            "condicion": datos.condicion,
            "canal": datos.canal.value if datos.canal else None,
            "declarado": datos.subtotal_declarado_usd,
            "notas": datos.notas,
        },
    ).scalar_one()

    for linea in datos.lineas:
        if linea.producto_id is not None:
            producto = db.execute(
                text(
                    "SELECT id, stock FROM productos WHERE id = :i "
                    "AND estado <> 'fusionado' FOR UPDATE"
                ),
                {"i": linea.producto_id},
            ).one_or_none()
            if producto is None:
                raise NoEncontrado(f"el producto {linea.producto_id}")
        compra_id = db.execute(
            text(
                """
                INSERT INTO compras
                  (lote_id, producto_id, descripcion_libre, cantidad, costo_unitario_usd)
                VALUES (:l, :p, :d, :c, :u) RETURNING id
                """
            ),
            {
                "l": lote,
                "p": linea.producto_id,
                "d": linea.descripcion.strip(),
                "c": linea.cantidad,
                "u": linea.costo_unitario_usd,
            },
        ).scalar_one()
        if linea.producto_id is not None:
            db.execute(
                text(
                    """
                    INSERT INTO movimientos_stock
                      (producto_id, tipo, cantidad, saldo_despues, referencia_tabla,
                       referencia_id, usuario_id, notas)
                    VALUES (:p, 'compra', :c,
                      (SELECT stock + :c FROM productos WHERE id = :p),
                      'compras', :r, :u, :n)
                    """
                ),
                {
                    "p": linea.producto_id,
                    "c": linea.cantidad,
                    "r": compra_id,
                    "u": actual.id,
                    "n": f"Lote {datos.codigo}",
                },
            )
            if linea.actualizar_costo:
                db.execute(
                    text(
                        "UPDATE productos SET costo_usd = :c, estado = 'activo', "
                        "revisado_at = now(), revisado_por_usuario_id = :u WHERE id = :p"
                    ),
                    {"c": linea.costo_unitario_usd, "u": actual.id, "p": linea.producto_id},
                )

    if datos.pago_inicial_usd and datos.pago_inicial_usd > 0:
        total = sum(x.cantidad * x.costo_unitario_usd for x in datos.lineas)
        if datos.pago_inicial_usd > total:
            raise ErrorNegocio("PAGO_COMPRA_EXCEDIDO", "El pago inicial supera el total del lote.")
        db.execute(
            text(
                """
                INSERT INTO pagos_compra
                  (lote_id, fecha, monto_usd, canal, referencia, registrado_por_usuario_id)
                VALUES (:l, :f, :m, :c, :r, :u)
                """
            ),
            {
                "l": lote,
                "f": datos.fecha,
                "m": datos.pago_inicial_usd,
                "c": datos.canal.value if datos.canal else None,
                "r": datos.referencia,
                "u": actual.id,
            },
        )
    db.commit()
    return {"lote_id": lote, "codigo": datos.codigo.strip()}


class AnulacionEntrada(BaseModel):
    motivo: str = Field(min_length=5, max_length=500)


@router.post("/{lote_id}/anular")
def anular_lote(
    lote_id: int,
    datos: AnulacionEntrada,
    db: SesionDb,
    actual: SoloAdmin,
    _: PuedeEscribir,
):
    """Anula una compra sacando del stock lo que habia ingresado.

    Misma disciplina que la anulacion de venta: no se borra la fila, queda con autor
    y motivo, y el stock se corrige por el libro para que siga siendo explicable.

    Con pagos al proveedor ya registrados no se anula: ese dinero salio de verdad.
    Hay que resolver primero que paso con el (una nota de credito, una devolucion),
    porque el sistema no puede adivinarlo.
    """
    lote = db.execute(
        text("SELECT id, codigo, anulada_at FROM lotes_compra WHERE id = :i FOR UPDATE"),
        {"i": lote_id},
    ).one_or_none()
    if lote is None:
        raise NoEncontrado("ese lote de compra")
    if lote.anulada_at is not None:
        raise ErrorNegocio(
            "COMPRA_YA_ANULADA", f"El lote {lote.codigo} ya estaba anulado."
        )

    pagados = db.execute(
        text("SELECT count(*) FROM pagos_compra WHERE lote_id = :i"), {"i": lote_id}
    ).scalar_one()
    if pagados:
        raise ErrorNegocio(
            "COMPRA_CON_PAGOS",
            f"El lote {lote.codigo} tiene {pagados} pago(s) al proveedor registrados.",
            sugerencia=(
                "Ese dinero salió de verdad. Resolvé primero qué pasa con él y "
                "registralo, en vez de hacer desaparecer la compra."
            ),
        )

    retirados = 0
    for item in db.execute(
        text("SELECT producto_id, cantidad FROM compras WHERE lote_id = :i"), {"i": lote_id}
    ).all():
        if item.producto_id is None or not item.cantidad:
            continue
        db.execute(
            text(
                "INSERT INTO movimientos_stock (producto_id, tipo, cantidad, saldo_despues, "
                "referencia_tabla, referencia_id, usuario_id, notas) "
                "VALUES (:p, 'ajuste', :c, (SELECT stock - :q FROM productos WHERE id = :p), "
                "'compras', :r, :u, :n)"
            ),
            {
                "p": item.producto_id,
                "c": -item.cantidad,
                "q": item.cantidad,
                "r": lote_id,
                "u": actual.id,
                "n": f"Anulación del lote {lote.codigo}: {datos.motivo}",
            },
        )
        retirados += item.cantidad

    db.execute(
        text(
            "UPDATE lotes_compra SET anulada_at = now(), anulada_por_usuario_id = :u, "
            "motivo_anulacion = :m WHERE id = :i"
        ),
        {"u": actual.id, "m": datos.motivo, "i": lote_id},
    )
    db.commit()
    return {
        "lote_id": lote_id,
        "codigo": lote.codigo,
        "anulada": True,
        "unidades_retiradas": retirados,
    }


@router.get("")
def listar(db: SesionDb, actual: SoloAdmin, limite: int = Query(default=100, le=500)):
    del actual
    filas = (
        db.execute(
            text(
                """
            SELECT cp.*, count(c.id) AS lineas, COALESCE(sum(c.cantidad), 0) AS unidades
              FROM v_cuentas_pagar cp LEFT JOIN compras c ON c.lote_id = cp.lote_id
             GROUP BY cp.lote_id, cp.codigo, cp.fecha, cp.proveedor, cp.total_usd,
                      cp.pagado_usd, cp.saldo_usd, cp.diferencia_usd
             ORDER BY cp.fecha DESC NULLS LAST, cp.lote_id DESC LIMIT :l
            """
            ),
            {"l": limite},
        )
        .mappings()
        .all()
    )
    return [dict(f) for f in filas]


class PagoCompraEntrada(BaseModel):
    fecha: date = Field(default_factory=date.today)
    monto_usd: Decimal = Field(gt=0)
    canal: CanalPago | None = None
    referencia: str | None = Field(default=None, max_length=64)


@router.post("/{lote_id}/pagos", status_code=201)
def pagar(
    lote_id: int, datos: PagoCompraEntrada, db: SesionDb, actual: SoloAdmin, _: PuedeEscribir
):
    existe = db.execute(
        text("SELECT 1 FROM lotes_compra WHERE id = :i FOR NO KEY UPDATE"), {"i": lote_id}
    ).scalar()
    if not existe:
        raise NoEncontrado("ese lote")
    cuenta = db.execute(
        text("SELECT saldo_usd FROM v_cuentas_pagar WHERE lote_id = :i"), {"i": lote_id}
    ).one_or_none()
    if cuenta is None:
        raise NoEncontrado("ese lote")
    if datos.monto_usd > cuenta.saldo_usd:
        raise ErrorNegocio(
            "PAGO_COMPRA_EXCEDIDO",
            "El pago supera el saldo de la compra.",
            detalles={"saldo_usd": str(cuenta.saldo_usd)},
        )
    pago = db.execute(
        text(
            """
            INSERT INTO pagos_compra
              (lote_id, fecha, monto_usd, canal, referencia, registrado_por_usuario_id)
            VALUES (:l, :f, :m, :c, :r, :u) RETURNING id
            """
        ),
        {
            "l": lote_id,
            "f": datos.fecha,
            "m": datos.monto_usd,
            "c": datos.canal.value if datos.canal else None,
            "r": datos.referencia,
            "u": actual.id,
        },
    ).scalar_one()
    db.commit()
    return {"pago_id": pago, "lote_id": lote_id}
