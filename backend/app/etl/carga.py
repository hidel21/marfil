"""Cargar: ejecutar el plan, en una sola transaccion.

Todo o nada. Si una accion falla a la mitad, no queda una base con la mitad de las
ventas nuevas y ninguno de sus pagos: el llamador hace rollback y el plan se puede
corregir y volver a correr.

Los pagos y sus reversos pasan por `app.services.pagos`, los mismos que usa la
pantalla de abonos: asi el saldo, las cuotas y la auditoria se mueven por los
triggers de siempre y no por un camino paralelo que habria que mantener igual.

Las ventas nuevas **no** pasan por el guardia de precio ni descuentan stock:

- el guardia controla precios que se estan cobrando ahora; una venta de agosto ya
  se cobro al precio que se cobro, y bloquearla no cambia el pasado;
- el stock actual se cargo despues de esas ventas, asi que descontarlas lo dejaria
  contado dos veces.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.normalizacion import clave_nombre
from app.db.session import fijar_contexto
from app.etl.cruce import Accion, Plan
from app.etl.libro import MAPEO_VERSION
from app.models.enums import CanalPago
from app.services import pagos as pagos_svc


class PlanYaAplicado(RuntimeError):
    """Ese mismo archivo, byte por byte, ya se aplico."""


@dataclass
class Resultado:
    importacion_id: int
    aplicadas: dict[str, dict[str, int]] = field(default_factory=dict)
    #: ref de hoja -> id creado, para el reporte final.
    creados: dict[str, int] = field(default_factory=dict)

    def contar(self, a: Accion) -> None:
        self.aplicadas.setdefault(a.etapa, {}).setdefault(a.tipo, 0)
        self.aplicadas[a.etapa][a.tipo] += 1


def _json(valor: object) -> str:
    return json.dumps(valor, ensure_ascii=False, default=str)


def _enlazar(sesion: Session, importacion_id: int, a: Accion, tabla: str, registro_id: int | None):
    """Guarda la fila tal cual y, si tiene destino, a que registro quedo ligada."""
    fila_id = sesion.execute(
        text(
            "INSERT INTO filas_importadas (importacion_id, hoja, numero_fila, datos) "
            "VALUES (:i, :h, :n, CAST(:d AS jsonb)) RETURNING id"
        ),
        {"i": importacion_id, "h": a.hoja, "n": a.fila, "d": _json(a.crudo)},
    ).scalar_one()
    if registro_id is not None:
        sesion.execute(
            text(
                "INSERT INTO enlaces_importacion (fila_id, tabla_destino, registro_id, metodo, "
                "score, confianza, notas) VALUES (:f, :t, :r, CAST(:m AS metodo_enlace), :s, "
                "CAST(:c AS confianza_dato), :n) ON CONFLICT DO NOTHING"
            ),
            {
                "f": fila_id,
                "t": tabla,
                "r": registro_id,
                "m": a.metodo or "exacto",
                "s": a.score,
                "c": a.confianza,
                "n": f"{a.tipo}: {a.motivo}"[:1000],
            },
        )


# ---------------------------------------------------------------------- etapas
def _costo(sesion: Session, a: Accion) -> None:
    d = a.datos
    # Lo mismo que hace "Aprobar" en Productos → Revisión: costo, linea y modelo.
    sesion.execute(
        text(
            f"UPDATE productos SET {d['campo']} = :v, "
            "linea = COALESCE(linea, :l), modelo_precio = CAST(:m AS modelo_precio), "
            "estado = CASE WHEN estado = 'borrador_por_revisar' THEN 'activo' ELSE estado END "
            f"WHERE id = :i AND {d['campo']} IS NULL"
        ),
        {"v": d["valor"], "l": d["linea"], "m": d["modelo"], "i": a.destino_id},
    )


def _producto(sesion: Session, nombre: str, usuario_id: int | None) -> int:
    """Alta en borrador, igual que el buscador de la venta cuando no encuentra nada."""
    return sesion.execute(
        text(
            "INSERT INTO productos (nombre, estado, origen_alta, creado_por_usuario_id, notas, "
            "costo, precio_divisa, precio_bcv, stock, precio_unitario, precio_original, "
            "precio_team, precio_revendedor) VALUES (:n, 'borrador_por_revisar', "
            "'importacion', :u, 'Creado al importar el Excel V2, sin costo. Cargalo para que "
            "salga de revisión.', 0,0,0,0,0,0,0,0) RETURNING id"
        ),
        {"n": nombre.strip(), "u": usuario_id},
    ).scalar_one()


def _cliente(sesion: Session, nombre: str, usuario_id: int | None) -> int:
    return sesion.execute(
        text(
            "INSERT INTO clientes (nombre, creado_por_usuario_id, notas) "
            "VALUES (:n, :u, 'Creado al importar el Excel V2.') RETURNING id"
        ),
        {"n": nombre.strip(), "u": usuario_id},
    ).scalar_one()


def _crear_venta(sesion: Session, a: Accion, usuario_id: int) -> int:
    """Misma forma que `services.ventas.crear`, sin guardia de precio ni stock."""
    d = a.datos
    provisional = sesion.execute(
        text(
            "SELECT 'V-' || to_char(CAST(:f AS date), 'YYYY') || '-tmp-' "
            "|| nextval('ventas_codigo_seq')"
        ),
        {"f": d["fecha"]},
    ).scalar_one()
    venta_id = sesion.execute(
        text(
            "INSERT INTO ventas (codigo, fecha, cliente_id, vendedor_usuario_id, "
            "moneda_cotizacion, nivel_precio_aplicado, plazo_dias, fecha_vencimiento, "
            "tiene_plan_cuotas, notas, creado_por_usuario_id, "
            "cliente, vendedor, producto, cantidad, precio_venta, costo, ganancia, "
            "moneda, deuda, estatus, total) "
            "VALUES (:codigo, :fecha, :cliente, :vendedor, CAST(:moneda AS moneda), "
            "CAST(:nivel AS nivel_precio), :plazo, :vence, FALSE, :notas, :usuario, "
            "(SELECT nombre FROM clientes WHERE id = :cliente), "
            "(SELECT nombre FROM usuarios WHERE id = :vendedor), :producto, 1, 0,0,0, "
            "'BCV', 0, 'PENDIENTE', 0) RETURNING id"
        ),
        {
            "codigo": provisional,
            "fecha": d["fecha"],
            "cliente": d["cliente_id"],
            "vendedor": d["vendedor_usuario_id"] or usuario_id,
            "moneda": d["moneda"],
            "nivel": d["nivel"],
            "plazo": d["plazo_dias"],
            "vence": d["vence"],
            "notas": d["notas"],
            "usuario": usuario_id,
            "producto": d["producto_nombre"],
        },
    ).scalar_one()
    sesion.execute(
        text(
            "UPDATE ventas SET codigo = 'V-' || to_char(fecha,'YYYY') || '-' || "
            "lpad(id::text, 4, '0') WHERE id = :i"
        ),
        {"i": venta_id},
    )
    sesion.execute(
        text(
            "INSERT INTO venta_items (venta_id, linea, producto_id, descripcion_libre, cantidad, "
            "precio_unitario_usd, costo_unitario_usd, precio_lista_usd, motivo_desviacion, "
            "aprobado_por_usuario_id, sobreventa) VALUES (:v, 1, :p, :desc, 1, :precio, :costo, "
            "NULL, :motivo, :u, FALSE)"
        ),
        {
            "v": venta_id,
            "p": d["producto_id"],
            "desc": d["producto_nombre"],
            "precio": d["precio_usd"],
            "costo": d["costo_usd"],
            "motivo": "Venta histórica importada del Excel V2",
            "u": usuario_id,
        },
    )
    return venta_id


def _actualizar_venta(sesion: Session, a: Accion) -> None:
    d = a.datos
    sesion.execute(
        text(
            "UPDATE ventas SET fecha = COALESCE(:fecha, fecha), "
            "plazo_dias = COALESCE(:plazo, plazo_dias), "
            "vendedor_usuario_id = COALESCE(:vendedor, vendedor_usuario_id) WHERE id = :i"
        ),
        {
            "fecha": d.get("fecha"),
            "plazo": d.get("plazo_dias"),
            "vendedor": d.get("vendedor_usuario_id"),
            "i": a.destino_id,
        },
    )
    if "fecha" in d or "plazo_dias" in d:
        # El vencimiento sale de la cuota implicita, no de la venta: si no se mueve la
        # cuota, la venta queda con fecha nueva y mora calculada con la vieja.
        sesion.execute(
            text(
                "UPDATE cuotas c SET fecha_vencimiento = v.fecha + v.plazo_dias "
                "FROM ventas v WHERE c.venta_id = v.id AND v.id = :i AND c.implicita"
            ),
            {"i": a.destino_id},
        )
        sesion.execute(
            text(
                "UPDATE ventas v SET fecha_vencimiento = COALESCE("
                "(SELECT min(fecha_vencimiento) FROM cuotas WHERE venta_id = v.id "
                "AND monto_abonado_usd < monto_usd), v.fecha + v.plazo_dias) WHERE v.id = :i"
            ),
            {"i": a.destino_id},
        )


def _registrar_pago(sesion: Session, a: Accion, venta_id: int, usuario_id: int | None) -> int:
    d = a.datos
    r = pagos_svc.registrar(
        sesion,
        venta_id=venta_id,
        fecha=d["fecha"],
        canal=CanalPago(d["canal"]),
        monto_moneda=Decimal(d["monto_moneda"]),
        tasa_manual=d["tasa_manual"],
        tasa_id=d["tasa_id"],
        en_bolivares_declarado=d["en_bolivares"],
        referencia=d["referencia"],
        notas=d["notas"],
        usuario_id=usuario_id,
    )
    if abs(Decimal(str(r["monto_usd"])) - d["monto_usd"]) >= Decimal("0.01"):
        # El plan y el servicio tienen que coincidir. Si no, algo del cruce esta mal
        # y es preferible abortar la carga entera a dejar un saldo distinto al revisado.
        raise RuntimeError(
            f"{a.ref}: el plan esperaba ${d['monto_usd']} y el servicio registró "
            f"${r['monto_usd']}."
        )
    return r["pago_id"]


def _crear_egreso(sesion: Session, a: Accion, usuario_id: int | None) -> tuple[str, int]:
    d = a.datos
    if d["tabla"] == "gastos":
        gid = sesion.execute(
            text(
                "INSERT INTO gastos (fecha, categoria, descripcion, monto_usd, monto_bs, "
                "tasa_aplicada, canal, texto_original, notas, creado_por_usuario_id) "
                "VALUES (:f, :cat, :desc, :usd, :bs, :tasa, CAST(:canal AS canal_pago), "
                ":orig, :notas, :u) RETURNING id"
            ),
            {
                "f": d["fecha"], "cat": d["categoria"], "desc": d["concepto"][:300],
                "usd": d["monto_usd"], "bs": d["monto_bs"], "tasa": d["tasa"],
                "canal": d["canal"], "orig": a.crudo.get("Observaciones"),
                "notas": d["notas"], "u": usuario_id,
            },
        ).scalar_one()
        return "gastos", gid

    # Compra: el libro trae el total del lote, no su detalle por producto. Va como
    # una sola linea de descripcion libre y sin producto, para que el lote sume lo
    # que costo (el total sale de sus lineas) sin tocar el stock de ningun perfume.
    lote = sesion.execute(
        text(
            "INSERT INTO lotes_compra (codigo, fecha, condicion, canal, subtotal_declarado_usd, "
            "texto_original, notas) VALUES (:c, :f, 'contado', CAST(:canal AS canal_pago), "
            ":usd, :orig, :notas) RETURNING id"
        ),
        {"c": d["codigo"], "f": d["fecha"], "canal": d["canal"], "usd": d["monto_usd"],
         "orig": a.crudo.get("Observaciones"), "notas": d["notas"]},
    ).scalar_one()
    sesion.execute(
        text(
            "INSERT INTO compras (lote_id, producto_id, descripcion_libre, cantidad, "
            "costo_unitario_usd, monto_bs, tasa_aplicada, texto_original) "
            "VALUES (:l, NULL, :desc, 1, :usd, :bs, :tasa, :orig)"
        ),
        {"l": lote, "desc": f"{d['concepto']} (sin detalle por producto)"[:200],
         "usd": d["monto_usd"], "bs": d["monto_bs"], "tasa": d["tasa"],
         "orig": a.crudo.get("Observaciones")},
    )
    # De contado: el pago al proveedor ya salio, con la fecha del lote.
    sesion.execute(
        text(
            "INSERT INTO pagos_compra (lote_id, fecha, monto_usd, monto_bs, tasa_aplicada, "
            "canal, registrado_por_usuario_id) VALUES (:l, :f, :usd, :bs, :tasa, "
            "CAST(:canal AS canal_pago), :u)"
        ),
        {"l": lote, "f": d["fecha"], "usd": d["monto_usd"], "bs": d["monto_bs"],
         "tasa": d["tasa"], "canal": d["canal"], "u": usuario_id},
    )
    return "lotes_compra", lote


# --------------------------------------------------------------------- entrada
def aplicar(sesion: Session, plan: Plan, *, usuario_id: int) -> Resultado:
    """Ejecuta el plan. **No hace commit**: eso le toca a quien llama.

    `usuario_id` es obligatorio: queda como autor en la auditoria y como vendedor de
    las ventas cuyo vendedor el libro no identifica (la columna no admite nulos).
    """
    if plan.ya_aplicado:
        raise PlanYaAplicado(
            f"El archivo {plan.archivo} ya se aplicó (mismo contenido, hash {plan.hash[:12]})."
        )
    # `escritor = 'api'` es lo que hacen los endpoints, y no es un detalle: sin esa
    # marca los triggers de compatibilidad asumen que escribe la app vieja de
    # Streamlit y "completan" la venta a su manera (le crean su propia linea, derivan
    # cliente y moneda del texto), que es exactamente lo que el ETL no quiere.
    fijar_contexto(sesion, usuario_id=usuario_id, escritor="api")
    # Autor en la auditoria: el usuario que ejecuta la carga, si se indico; si no,
    # `fn_auditar` cae a este actor_tipo y la registra como migracion.
    sesion.execute(text("SELECT set_config('app.actor_tipo', 'migracion', true)"))
    importacion_id = sesion.execute(
        text(
            "INSERT INTO importaciones (archivo, archivo_hash, mapeo_version, estado, "
            "importado_por_usuario_id) VALUES (:a, :h, :m, 'aplicado', :u) RETURNING id"
        ),
        {"a": plan.archivo, "h": plan.hash, "m": MAPEO_VERSION, "u": usuario_id},
    ).scalar_one()
    res = Resultado(importacion_id=importacion_id)

    for a in plan.de("costos"):
        _costo(sesion, a)
        _enlazar(sesion, importacion_id, a, "productos", a.destino_id)
        res.contar(a)

    ventas_creadas: dict[str, int] = {}
    # Un cliente o producto nuevo puede aparecer en varias ventas del libro: se crea
    # una vez y las demas lo reutilizan (el indice unico lo exige de todas formas).
    clientes_nuevos: dict[str, int] = {}
    productos_nuevos: dict[str, int] = {}
    for a in plan.de("ventas"):
        registro = a.destino_id
        if a.tipo == "crear":
            d = a.datos
            if d["cliente_id"] is None:
                clave = clave_nombre(d["cliente_nombre"])
                if clave not in clientes_nuevos:
                    clientes_nuevos[clave] = _cliente(sesion, d["cliente_nombre"], usuario_id)
                d["cliente_id"] = clientes_nuevos[clave]
            if d["producto_id"] is None:
                clave = clave_nombre(d["producto_nombre"])
                if clave not in productos_nuevos:
                    productos_nuevos[clave] = _producto(sesion, d["producto_nombre"], usuario_id)
                d["producto_id"] = productos_nuevos[clave]
            registro = _crear_venta(sesion, a, usuario_id)
            ventas_creadas[a.ref] = registro
            res.creados[a.ref] = registro
        elif a.tipo == "actualizar":
            _actualizar_venta(sesion, a)
        _enlazar(sesion, importacion_id, a, "ventas", registro)
        res.contar(a)

    # Tres fases, y el orden importa:
    #   1. se reversan **todos** los abonos mal convertidos;
    #   2. se registran sus versiones correctas;
    #   3. se registran los abonos nuevos.
    # Corregir de a uno no funciona: si una venta tiene tres abonos mal convertidos que
    # suman bien en total pero mal uno por uno, al corregir el primero los otros dos
    # todavia no bajaron y el abono correcto "excede" un saldo que en realidad alcanza.
    correcciones = sorted(
        (a for a in plan.de("pagos") if a.tipo == "corregir"), key=lambda x: str(x.datos["fecha"])
    )
    for a in correcciones:
        pagos_svc.reversar(
            sesion,
            pago_id=a.datos["pago_original_id"],
            motivo=f"Corrección desde el Excel V2 ({a.ref}): {a.motivo}"[:500],
            usuario_id=usuario_id,
            fecha=a.datos["fecha"],
        )
    for a in correcciones:
        registro = _registrar_pago(sesion, a, a.datos["venta_id"], usuario_id)
        res.creados[a.ref] = registro
        _enlazar(sesion, importacion_id, a, "pagos", registro)
        res.contar(a)
    resto = [a for a in plan.de("pagos") if a.tipo != "corregir"]
    for a in sorted(resto, key=lambda x: str(x.datos.get("fecha"))):
        registro = a.destino_id
        if a.tipo == "crear":
            venta_id = a.datos["venta_id"] or ventas_creadas[a.datos["venta_ref"]]
            registro = _registrar_pago(sesion, a, venta_id, usuario_id)
            res.creados[a.ref] = registro
        _enlazar(sesion, importacion_id, a, "pagos", registro)
        res.contar(a)

    for a in plan.de("egresos"):
        tabla = "lotes_compra" if (a.crudo.get("Tipo") or "").lower() == "compra" else "gastos"
        registro = a.destino_id
        if a.tipo == "crear":
            tabla, registro = _crear_egreso(sesion, a, usuario_id)
            res.creados[a.ref] = registro
        _enlazar(sesion, importacion_id, a, tabla, registro)
        res.contar(a)

    return res
