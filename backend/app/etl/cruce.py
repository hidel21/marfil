"""Cruzar: cada fila del libro contra lo que ya hay en la base.

El resultado es un **plan**: una lista de acciones, cada una con su motivo. Nada se
escribe aca; `plan` y `aplicar` corren exactamente este mismo codigo, y la unica
diferencia es que `aplicar` despues ejecuta lo que el plan dice.

Las reglas que deciden, en orden de precedencia:

1. **Linaje.** Si una fila con ese mismo ID (`V-031`) ya se importo antes, su destino
   es el registrado. Es determinista y es lo que hace repetible el proceso.
2. **Tratamiento.** `Revisar` y `Sin caja` no se cargan. El libro las marca asi
   justamente porque su curador no las pudo confirmar, y cargarlas convertiria una
   duda en un dato.
3. **Parecido.** Sin linaje, la venta se busca por cliente y producto, no por fecha.
   La migracion original **no tenia columna de fecha de venta**: las de la base se
   sintetizaron, asi que la misma venta aparece con fechas distintas en cada lado.
   Cruzar por fecha duplicaria casi todas.
4. **Nada se inventa.** Una venta sin precio, un pago sin monto o una venta cuya base
   (BCV o divisa) no consta se omiten con el motivo escrito, en vez de completarse
   con un valor supuesto.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from difflib import SequenceMatcher

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.normalizacion import clave_nombre
from app.etl.libro import EgresoFila, Libro, PagoFila, VentaFila

#: Por debajo de esto, dos ventas no se consideran la misma.
UMBRAL_VENTA = Decimal("0.85")
#: Un producto se reutiliza por parecido solo si es casi identico: equivocarse aca
#: le pega el costo de un perfume a otro.
UMBRAL_PRODUCTO = 0.92
#: Diferencia a partir de la cual el equivalente de un pago se considera distinto.
CENTAVO = Decimal("0.01")

MONEDA_POR_BASE = {"BCV": "VES", "USDT": "USDT", "DIVISA": "USD"}
CANAL_POR_METODO = {
    "PAGO MOVIL": "pago_movil",
    "TRANSFERENCIA": "transferencia",
    "BINANCE": "binance",
    "ZELLE": "zelle",
    "USDT": "usdt",
}


@dataclass
class Accion:
    etapa: str
    #: crear | actualizar | corregir | igual | omitir
    tipo: str
    ref: str
    hoja: str
    fila: int
    motivo: str
    destino_id: int | None = None
    #: exacto | fuzzy | heuristica | manual — el enum `metodo_enlace` de la base.
    metodo: str | None = None
    score: float | None = None
    confianza: str = "alta"
    #: campo -> [antes, despues], para el reporte.
    cambios: dict = field(default_factory=dict)
    #: Lo que la carga necesita para ejecutar la accion.
    datos: dict = field(default_factory=dict)
    crudo: dict = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)

    def como_dict(self) -> dict:
        return asdict(self)


@dataclass
class Plan:
    archivo: str
    hash: str
    acciones: list[Accion] = field(default_factory=list)
    #: Registros que estan en la base y no en el libro. No se tocan: se informan.
    solo_en_base: list[dict] = field(default_factory=list)
    ya_aplicado: bool = False

    def de(self, etapa: str) -> list[Accion]:
        return [a for a in self.acciones if a.etapa == etapa]

    def resumen(self) -> dict[str, dict[str, int]]:
        salida: dict[str, dict[str, int]] = {}
        for a in self.acciones:
            salida.setdefault(a.etapa, {}).setdefault(a.tipo, 0)
            salida[a.etapa][a.tipo] += 1
        return salida


#: Palabras que un nombre de catalogo puede agregar sin cambiar de que perfume se
#: habla: "Club de Nuit Intense" y "Club de Nuit **Man** Intense" son el mismo.
#: "Elixir", "Rebel", "Night" o "Parfum" no estan aca: esos si son otro perfume
#: (Invictus Parfum es un lanzamiento distinto de Invictus).
PALABRAS_NEUTRAS = {"man", "men", "hombre", "homme", "pour", "de"}
#: "Invictus Clasico" es la version base de Invictus, no un producto distinto.
CALIFICADORES = {"clasico", "clasica", "original"}


# --------------------------------------------------------------------- utiles
def _palabras(nombre: str | None, *, sin_marca: bool = False) -> set[str]:
    """Palabras sin acentos ni mayusculas. `sin_marca` quita el "Marca, " inicial."""
    texto = nombre or ""
    if sin_marca and "," in texto:
        texto = texto.split(",", 1)[1]
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch)).lower()
    return set(re.findall(r"[a-z0-9]+", texto))


def _parecido(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, clave_nombre(a), clave_nombre(b)).ratio()


def _ref_limpia(ref: object) -> str | None:
    """'0542', '542' y '542.0' son la misma referencia bancaria."""
    if ref is None:
        return None
    texto = str(ref).strip()
    if texto.endswith(".0"):
        texto = texto[:-2]
    digitos = texto.lstrip("0")
    return digitos or (texto or None)


def _canal(metodo: str | None, base: str | None, hay_bs: bool) -> tuple[str, bool | None]:
    """(canal, en_bolivares declarado). El segundo solo importa para `otro`."""
    clave = clave_nombre(metodo or "").upper()
    for nombre, canal in CANAL_POR_METODO.items():
        if clave_nombre(nombre).upper() == clave:
            return canal, None
    if clave == "EFECTIVO":
        return ("efectivo_bs", None) if hay_bs else ("efectivo_usd", None)
    # "Sin confirmar" o un metodo que no conocemos: `otro`, declarando la moneda
    # por lo que si consta, que es si hay monto en bolivares.
    return "otro", hay_bs


def _base(base: str | None) -> str | None:
    return MONEDA_POR_BASE.get((base or "").strip().upper())


# ---------------------------------------------------------- estado de la base
class Estado:
    """Lo que hay hoy en la base, cargado una sola vez para cruzar en memoria."""

    def __init__(self, sesion: Session, mapeo: str) -> None:
        self.sesion = sesion
        q = lambda sql, **p: sesion.execute(text(sql), p).mappings().all()  # noqa: E731

        self.clientes = q(
            "SELECT id, nombre, nivel_precio::text AS nivel, plazo_credito_dias AS plazo "
            "FROM clientes WHERE estado <> 'fusionado'"
        )
        self.cliente_por_clave: dict[str, int] = {}
        for c in self.clientes:
            self.cliente_por_clave.setdefault(clave_nombre(c["nombre"]), c["id"])
        for a in q("SELECT cliente_id, alias_normalizado FROM clientes_alias"):
            self.cliente_por_clave.setdefault(a["alias_normalizado"], a["cliente_id"])
        self.cliente = {c["id"]: c for c in self.clientes}

        self.productos = q(
            "SELECT id, nombre, costo_usd, precio_original_usd, es_original, "
            "estado::text AS estado FROM productos WHERE estado <> 'fusionado'"
        )
        self.producto_por_clave: dict[str, int] = {}
        for p in self.productos:
            self.producto_por_clave.setdefault(clave_nombre(p["nombre"]), p["id"])
        for a in q("SELECT producto_id, alias_normalizado FROM productos_alias"):
            self.producto_por_clave.setdefault(a["alias_normalizado"], a["producto_id"])
        self.producto = {p["id"]: p for p in self.productos}

        usuarios = q("SELECT id, nombre FROM usuarios WHERE activo ORDER BY id DESC")
        self.usuario_por_clave = {clave_nombre(u["nombre"]): u["id"] for u in usuarios}
        self.nombre_usuario = {u["id"]: u["nombre"] for u in usuarios}

        self.ventas = q(
            """
            SELECT v.id, v.codigo, v.fecha, v.cliente_id, c.nombre AS cliente,
                   v.total_usd, v.plazo_dias, v.vendedor_usuario_id, v.producto AS legacy,
                   (SELECT string_agg(coalesce(p.nombre, i.descripcion_libre), ' + ')
                      FROM venta_items i LEFT JOIN productos p ON p.id = i.producto_id
                     WHERE i.venta_id = v.id) AS producto
              FROM ventas v JOIN clientes c ON c.id = v.cliente_id
             WHERE v.anulada_at IS NULL
            """
        )
        self.venta = {v["id"]: v for v in self.ventas}

        # Solo los abonos vivos: uno ya reversado no es un cobro que haya que cruzar.
        self.pagos = q(
            """
            SELECT p.id, p.venta_id, p.fecha, p.canal::text AS canal, p.monto_moneda,
                   p.monto_usd, p.moneda::text AS moneda, p.referencia
              FROM pagos p
             WHERE p.tipo = 'abono'
               AND NOT EXISTS (SELECT 1 FROM pagos r WHERE r.anula_pago_id = p.id)
            """
        )
        self.lotes = q("SELECT id, codigo, fecha FROM lotes_compra WHERE anulada_at IS NULL")
        self.gastos = q("SELECT id, fecha, monto_usd, descripcion FROM gastos")

        # Linaje de importaciones anteriores con este mismo mapeo: ID de hoja → destino.
        self.linaje: dict[tuple[str, str], int] = {}
        for e in q(
            """
            SELECT f.hoja, f.datos, e.tabla_destino, e.registro_id
              FROM enlaces_importacion e
              JOIN filas_importadas f ON f.id = e.fila_id
              JOIN importaciones i ON i.id = f.importacion_id
             WHERE i.mapeo_version LIKE :m AND i.estado = 'aplicado'
            """,
            m=mapeo.split(".")[0] + "%",
        ):
            ref = (e["datos"] or {}).get("_ref")
            if ref:
                self.linaje[(e["tabla_destino"], ref)] = e["registro_id"]

    def resolver_cliente(self, nombre: str) -> tuple[int | None, str | None]:
        """(cliente, metodo). Exacto por nombre o alias; si no, contencion unica.

        La contencion cubre el caso que de hecho aparece: el libro abrevia
        ("Landaeta") y alguien ya dio de alta al cliente completo ("landaeta juan").
        Solo vale si hay **un** cliente que contenga todas las palabras; con dos,
        adivinar pegaria la deuda de uno al otro.
        """
        exacto = self.cliente_por_clave.get(clave_nombre(nombre))
        if exacto is not None:
            return exacto, "exacto"
        buscado = _palabras(nombre)
        candidatos = [
            c["id"] for c in self.clientes if buscado and buscado <= _palabras(c["nombre"])
        ]
        if len(candidatos) == 1:
            return candidatos[0], "heuristica"
        return None, None

    def resolver_producto(self, nombre: str) -> tuple[int | None, str | None, float]:
        clave = clave_nombre(nombre)
        if clave in self.producto_por_clave:
            return self.producto_por_clave[clave], "exacto", 1.0
        # Contencion acotada: el catalogo puede agregar palabras neutras o anteponer la
        # marca ("Armaf, ..."), pero el original y el Top Quality no se mezclan.
        quiere_original = "original" in _palabras(nombre)
        buscado = _palabras(nombre) - CALIFICADORES
        candidatos = []
        for p in self.productos:
            if bool(p["es_original"]) != quiere_original:
                continue
            catalogo = _palabras(p["nombre"], sin_marca=True)
            if buscado and buscado <= catalogo and not (catalogo - buscado - PALABRAS_NEUTRAS):
                candidatos.append(p["id"])
        if len(candidatos) == 1:
            return candidatos[0], "heuristica", 0.9
        mejores = sorted(
            ((_parecido(nombre, p["nombre"]), p["id"]) for p in self.productos), reverse=True
        )
        if mejores and mejores[0][0] >= UMBRAL_PRODUCTO and (
            len(mejores) == 1 or mejores[1][0] < mejores[0][0]
        ):
            return mejores[0][1], "fuzzy", mejores[0][0]
        return None, None, mejores[0][0] if mejores else 0.0


# -------------------------------------------------------------------- etapas
def _cruzar_ventas(estado: Estado, libro: Libro, plan: Plan) -> dict[str, Accion]:
    """Devuelve el plan de cada venta por su ID de hoja, para que los pagos lo usen."""
    por_ref: dict[str, Accion] = {}

    # 1. Candidatos por parecido, resueltos de mayor a menor puntaje. Emparejar en
    #    orden de hoja haria que una venta temprana se quede con la pareja de otra.
    reclamadas: dict[int, str] = {}
    destino: dict[str, tuple[int, str, float]] = {}
    anuladas: dict[str, int] = {}
    for fila in libro.ventas:
        if ("ventas", fila.ref) in estado.linaje:
            vid = estado.linaje[("ventas", fila.ref)]
            if vid in estado.venta:
                destino[fila.ref] = (vid, "manual", 1.0)
                reclamadas[vid] = fila.ref
            else:
                # Se importo y despues un socio la anulo. Volver a crearla desharia esa
                # decision: queda omitida, y sus pagos con ella.
                anuladas[fila.ref] = vid
    pares = []
    resueltos = {f.ref: estado.resolver_cliente(f.cliente) for f in libro.ventas}
    cliente_de = {ref: cid for ref, (cid, _m) in resueltos.items()}
    for fila in libro.ventas:
        if fila.ref in destino:
            continue
        for v in estado.ventas:
            mismo = cliente_de[fila.ref] == v["cliente_id"]
            c = 1.0 if mismo else _parecido(fila.cliente, v["cliente"])
            p = max(_parecido(fila.producto, v["producto"]), _parecido(fila.producto, v["legacy"]))
            puntaje = Decimal(str(round(0.5 * c + 0.5 * p, 4)))
            if puntaje >= UMBRAL_VENTA:
                mismo_precio = fila.precio_usd is not None and abs(
                    fila.precio_usd - v["total_usd"]
                ) < CENTAVO
                dias = abs((fila.fecha - v["fecha"]).days) if fila.fecha else 9999
                pares.append((puntaje, mismo_precio, -dias, fila.ref, v["id"]))
    # Un cliente que compra dos veces el mismo perfume empata en puntaje contra ambas
    # ventas; el ID de hoja no sirve para desempatar. Decide el precio y, despues, la
    # cercania de la fecha, que son los datos que distinguen una compra de la otra.
    for puntaje, _precio, _dias, ref, vid in sorted(pares, reverse=True):
        if ref in destino or vid in reclamadas:
            continue
        destino[ref] = (vid, "exacto" if puntaje == 1 else "fuzzy", float(puntaje))
        reclamadas[vid] = ref

    # 2. Una accion por fila.
    for fila in libro.ventas:
        comun = {"etapa": "ventas", "ref": fila.ref, "hoja": fila.hoja, "fila": fila.numero}
        crudo = {**fila.crudo, "_ref": fila.ref}
        if fila.ref in anuladas:
            por_ref[fila.ref] = Accion(
                **comun, tipo="omitir", crudo=crudo,
                motivo=f"Se importó y después se anuló en la base (venta #{anuladas[fila.ref]}): "
                "no se vuelve a crear.",
            )
            continue
        # El libro da algunas ventas por pagadas con una diferencia que su curador no
        # pudo ubicar ("sin crear efectivo"). No se inventa un cobro para cerrarlas: se
        # avisa, porque en la base van a quedar con ese saldo hasta que se concilien.
        diferencia = fila.crudo.get("Diferencia al cierre $")
        aviso_cierre = (
            f"El libro la da por pagada con ${diferencia} por conciliar, sin cobro que lo "
            "respalde: en la base queda ese saldo hasta que se decida qué pasó."
            if fila.crudo.get("Estado") == "Pagado" and diferencia and float(diferencia) > 0
            else None
        )
        if fila.ref in destino:
            vid, metodo, puntaje = destino[fila.ref]
            actual = estado.venta[vid]
            base = {
                **comun,
                "destino_id": vid,
                "metodo": metodo,
                "score": puntaje,
                "confianza": "alta" if puntaje >= 0.95 else "media",
                "crudo": crudo,
            }
            if fila.tratamiento != "Incluir":
                por_ref[fila.ref] = Accion(
                    **base,
                    tipo="omitir",
                    motivo=f"Ya está en la base como {actual['codigo']}; el libro la marca "
                    f"'{fila.tratamiento}', así que no se actualiza.",
                )
                continue
            cambios, datos = {}, {}
            if fila.fecha and fila.fecha != actual["fecha"]:
                cambios["fecha"] = [str(actual["fecha"]), str(fila.fecha)]
                datos["fecha"] = fila.fecha
            if fila.plazo_dias and fila.plazo_dias != actual["plazo_dias"]:
                cambios["plazo_dias"] = [actual["plazo_dias"], fila.plazo_dias]
                datos["plazo_dias"] = fila.plazo_dias
            vendedor = estado.usuario_por_clave.get(clave_nombre(fila.vendedor or ""))
            if vendedor and vendedor != actual["vendedor_usuario_id"]:
                antes = estado.nombre_usuario.get(actual["vendedor_usuario_id"])
                cambios["vendedor"] = [antes, fila.vendedor]
                datos["vendedor_usuario_id"] = vendedor
            avisos = []
            precio = fila.precio_usd
            if precio is not None and abs(precio - actual["total_usd"]) >= CENTAVO:
                # El total no se cambia desde el ETL: moveria el saldo de una venta con
                # abonos sin que nadie lo revise. Se informa.
                avisos.append(
                    f"El libro dice ${fila.precio_usd} y la base ${actual['total_usd']}: "
                    "no se cambia el total, revisar a mano."
                )
            if datos:
                datos["codigo"] = actual["codigo"]
                por_ref[fila.ref] = Accion(
                    **base, tipo="actualizar", motivo=f"Es {actual['codigo']}.",
                    cambios=cambios, datos=datos, avisos=avisos,
                )
            else:
                por_ref[fila.ref] = Accion(
                    **base, tipo="igual", motivo=f"Es {actual['codigo']}, sin cambios.",
                    avisos=avisos,
                )
            continue

        # Venta nueva.
        motivo_omision = None
        if fila.tratamiento != "Incluir":
            motivo_omision = f"El libro la marca '{fila.tratamiento}'."
        elif fila.precio_usd is None or fila.precio_usd <= 0:
            motivo_omision = "Precio sin confirmar en el libro."
        elif fila.fecha is None:
            motivo_omision = "Sin fecha de venta."
        elif _base(fila.base) is None:
            motivo_omision = (
                f"Base del precio '{fila.base}': BCV o divisa cambian lo que se cobra, "
                "no se adivina."
            )
        if motivo_omision:
            por_ref[fila.ref] = Accion(**comun, tipo="omitir", motivo=motivo_omision, crudo=crudo)
            continue

        avisos = [aviso_cierre] if aviso_cierre else []
        cliente_id = cliente_de[fila.ref]
        if resueltos[fila.ref][1] == "heuristica":
            avisos.append(
                f"Cliente '{fila.cliente}' asociado a "
                f"'{estado.cliente[cliente_id]['nombre']}' por contener su nombre: confirmar."
            )
        if cliente_id is None:
            parecidos = sorted(
                ((_parecido(fila.cliente, c["nombre"]), c["nombre"]) for c in estado.clientes),
                reverse=True,
            )[:2]
            parecidos = [n for s, n in parecidos if s >= 0.6]
            avisos.append(
                f"Cliente nuevo '{fila.cliente}'"
                + (
                    f", parecido a {', '.join(parecidos)}: si es la misma persona, fusionar."
                    if parecidos
                    else "."
                )
            )
        producto_id, metodo_producto, puntaje_producto = estado.resolver_producto(fila.producto)
        if producto_id is None:
            avisos.append(f"Producto nuevo '{fila.producto}': queda en la cola de Revisión.")
        elif metodo_producto == "heuristica":
            avisos.append(
                f"Producto '{fila.producto}' asociado a "
                f"'{estado.producto[producto_id]['nombre']}' (mismo nombre con palabras "
                "neutras o marca antepuesta)."
            )
        elif metodo_producto == "fuzzy":
            avisos.append(
                f"Producto '{fila.producto}' asociado a "
                f"'{estado.producto[producto_id]['nombre']}' por parecido ({puntaje_producto:.2f})."
            )
        vendedor_id = estado.usuario_por_clave.get(clave_nombre(fila.vendedor or ""))
        if vendedor_id is None:
            avisos.append(
                f"Vendedor '{fila.vendedor or 'sin dato'}' no identificado: la venta queda a "
                "nombre de quien ejecuta la importación."
            )
        cliente = estado.cliente.get(cliente_id) if cliente_id else None
        plazo = fila.plazo_dias or (cliente["plazo"] if cliente and cliente["plazo"] else 30)
        heuristico = resueltos[fila.ref][1] == "heuristica" or metodo_producto in (
            "heuristica", "fuzzy"
        )
        por_ref[fila.ref] = Accion(
            **comun,
            tipo="crear",
            motivo="No está en la base.",
            metodo="heuristica" if heuristico else "exacto",
            confianza="media" if heuristico else "alta",
            crudo=crudo,
            avisos=avisos,
            datos={
                "fecha": fila.fecha,
                "cliente_id": cliente_id,
                "cliente_nombre": fila.cliente,
                "producto_id": producto_id,
                "producto_nombre": fila.producto,
                "precio_usd": fila.precio_usd,
                "costo_usd": fila.costo_usd or Decimal("0"),
                "moneda": _base(fila.base),
                "nivel": cliente["nivel"] if cliente else "publico",
                "plazo_dias": plazo,
                "vence": fila.fecha + timedelta(days=plazo),
                "vendedor_usuario_id": vendedor_id,
                "notas": f"Importada del Excel V2 ({fila.ref}). {fila.observaciones}".strip(),
            },
        )

    plan.acciones.extend(por_ref.values())
    plan.solo_en_base.extend(
        {"tipo": "venta", "id": v["id"], "codigo": v["codigo"], "cliente": v["cliente"],
         "producto": v["producto"], "total_usd": str(v["total_usd"])}
        for v in estado.ventas
        if v["id"] not in reclamadas
    )
    return por_ref


#: Mas vieja que esto, una tasa no se usa. El BCV no publica fines de semana ni
#: feriados, asi que un pago del lunes con la del viernes es normal; uno de hoy con
#: la de hace tres semanas es un job de captura que no esta corriendo.
TASA_MAX_DIAS = 4


def _tasa_para(estado: Estado, fecha: date) -> tuple[Decimal, int] | None:
    """La tasa BCV que regia ese dia, o None si no hay una reciente."""
    fila = estado.sesion.execute(
        text(
            "SELECT id, valor, fecha FROM tasas_cambio WHERE tipo = 'bcv' AND fecha <= :f "
            "ORDER BY fecha DESC LIMIT 1"
        ),
        {"f": fecha},
    ).one_or_none()
    if fila is None or (fecha - fila.fecha).days > TASA_MAX_DIAS:
        return None
    return fila.valor, fila.id


def _cruzar_pagos(estado: Estado, libro: Libro, plan: Plan, ventas: dict[str, Accion]) -> None:
    usados: set[int] = set()
    saldo_nuevo: dict[str, Decimal] = {}

    def comparable(p: PagoFila, existente) -> bool:
        if existente["id"] in usados:
            return False
        ref_a, ref_b = _ref_limpia(p.referencia), _ref_limpia(existente["referencia"])
        if ref_a and ref_b and ref_a == ref_b:
            return True
        if existente["fecha"] != p.fecha:
            return False
        if p.monto_bs is not None and existente["moneda"] == "VES":
            return abs(existente["monto_moneda"] - p.monto_bs) < CENTAVO
        if p.monto_bs is None and p.equivalente_usd is not None:
            return abs(existente["monto_usd"] - p.equivalente_usd) < CENTAVO
        return False

    # Primera pasada: clasificar cada fila y resolver su pareja en la base. Las
    # correcciones se emiten antes que los pagos nuevos porque cambian el saldo contra
    # el que esos pagos se validan; en orden de fecha, un pago nuevo podria parecer
    # excesivo solo porque la correccion de un abono anterior todavia no se aplico.
    pendientes = []
    for fila in sorted(libro.pagos, key=lambda p: (p.fecha, p.ref)):
        comun = {"etapa": "pagos", "ref": fila.ref, "hoja": fila.hoja, "fila": fila.numero,
                 "crudo": {**fila.crudo, "_ref": fila.ref}}
        venta = ventas.get(fila.venta_ref or "")
        if fila.tratamiento != "Incluir":
            plan.acciones.append(Accion(**comun, tipo="omitir",
                                        motivo=f"El libro lo marca '{fila.tratamiento}'."))
            continue
        if venta is None:
            plan.acciones.append(Accion(**comun, tipo="omitir",
                                        motivo=f"La venta {fila.venta_ref} no está en el libro."))
            continue
        if venta.tipo == "omitir" and venta.destino_id is None:
            plan.acciones.append(Accion(
                **comun, tipo="omitir",
                motivo=f"Su venta {fila.venta_ref} no se carga ({venta.motivo.rstrip('.')}).",
            ))
            continue
        if fila.monto_bs is None and fila.equivalente_usd is None:
            plan.acciones.append(Accion(**comun, tipo="omitir", motivo="Sin monto."))
            continue
        canal, en_bs = _canal(fila.metodo, fila.base, fila.monto_bs is not None)
        nuevo = _datos_pago(estado, fila, canal, en_bs)
        if isinstance(nuevo, str):
            plan.acciones.append(Accion(**comun, tipo="omitir", motivo=nuevo))
            continue
        existente = None
        if ("pagos", fila.ref) in estado.linaje:
            pid = estado.linaje[("pagos", fila.ref)]
            existente = next((p for p in estado.pagos if p["id"] == pid), None)
        # El abono enlazado puede ya no estar vivo: si alguien lo corrigio despues de
        # importar, se reverso y en su lugar hay otro. Sin este segundo intento la fila
        # parece nueva, y con saldo disponible se registraria el pago dos veces.
        if existente is None and venta.destino_id is not None:
            existente = next(
                (p for p in estado.pagos
                 if p["venta_id"] == venta.destino_id and comparable(fila, p)),
                None,
            )
        if existente is not None:
            usados.add(existente["id"])
        pendientes.append((fila, comun, venta, existente, nuevo))

    for fila, comun, _venta, existente, nuevo in pendientes:
        if existente is None:
            continue
        base = {**comun, "destino_id": existente["id"], "metodo": "exacto", "score": 1.0}
        if (
            fila.equivalente_usd is not None
            and abs(existente["monto_usd"] - fila.equivalente_usd) >= CENTAVO
        ):
            plan.acciones.append(Accion(
                **base,
                tipo="corregir",
                motivo=(
                    f"El abono #{existente['id']} registró ${existente['monto_usd']} y lo "
                    f"acordado fue ${fila.equivalente_usd}. Se reversa con su fecha "
                    "original y se registra de nuevo."
                ),
                cambios={"monto_usd": [str(existente["monto_usd"]), str(fila.equivalente_usd)]},
                avisos=nuevo["avisos"],
                datos={
                    **{k: v for k, v in nuevo.items() if k != "avisos"},
                    # La referencia bancaria ya la tiene el abono original, que sigue
                    # existiendo (reversado, no borrado), y el indice unico impide que
                    # la misma transferencia figure dos veces. La correccion la cita.
                    "referencia": None,
                    "notas": (
                        f"{nuevo['notas']} Corrige el abono #{existente['id']}"
                        + (f", referencia bancaria {fila.referencia}." if fila.referencia else ".")
                    ),
                    "pago_original_id": existente["id"],
                    "venta_id": existente["venta_id"],
                },
            ))
        else:
            plan.acciones.append(Accion(**base, tipo="igual",
                                        motivo=f"Es el abono #{existente['id']}."))

    # Segunda pasada: los pagos nuevos, contra el saldo ya corregido. Se simula para no
    # intentar un abono que exceda la deuda: el servicio lo rechazaria y tiraria la
    # transaccion entera.
    for _fila, comun, venta, existente, nuevo in pendientes:
        if existente is not None:
            continue
        if venta.destino_id is not None:
            clave_venta = f"id:{venta.destino_id}"
            if clave_venta not in saldo_nuevo:
                saldo_nuevo[clave_venta] = _saldo_proyectado(estado, venta.destino_id, plan)
        else:
            clave_venta = f"ref:{venta.ref}"
            saldo_nuevo.setdefault(clave_venta, venta.datos["precio_usd"])
        monto = nuevo["monto_usd"]
        if monto - saldo_nuevo[clave_venta] > Decimal("0.005"):
            plan.acciones.append(Accion(
                **comun, tipo="omitir",
                motivo=(
                    f"Cobra ${monto} y a la venta le quedan ${saldo_nuevo[clave_venta]}: "
                    "excede la deuda. Revisar si pertenece a otra venta."
                ),
            ))
            continue
        saldo_nuevo[clave_venta] -= monto
        plan.acciones.append(Accion(
            **comun, tipo="crear", metodo="exacto",
            motivo="No está en la base.",
            confianza="media" if nuevo["origen"] == "bcv_del_dia" else "alta",
            avisos=nuevo["avisos"],
            datos={**{k: v for k, v in nuevo.items() if k != "avisos"},
                   "venta_ref": venta.ref, "venta_id": venta.destino_id},
        ))

    plan.solo_en_base.extend(
        {"tipo": "pago", "id": p["id"], "venta_id": p["venta_id"], "fecha": str(p["fecha"]),
         "monto_usd": str(p["monto_usd"])}
        for p in estado.pagos
        if p["id"] not in usados
    )


def _saldo_proyectado(estado: Estado, venta_id: int, plan: Plan) -> Decimal:
    """Saldo de una venta existente despues de las correcciones ya planificadas."""
    venta = estado.venta[venta_id]
    vivos = [p for p in estado.pagos if p["venta_id"] == venta_id]
    cobrado = sum((p["monto_usd"] for p in vivos), Decimal("0"))
    for a in plan.de("pagos"):
        if a.tipo == "corregir" and a.datos.get("venta_id") == venta_id:
            cobrado += a.datos["monto_usd"] - Decimal(a.cambios["monto_usd"][0])
    return venta["total_usd"] - cobrado


def _datos_pago(estado: Estado, fila: PagoFila, canal: str, en_bs: bool | None) -> dict | str:
    """Como se registra el pago, o el motivo por el que no se puede."""
    avisos: list[str] = []
    comun = {"fecha": fila.fecha, "canal": canal, "en_bolivares": en_bs,
             "referencia": _ref_limpia(fila.referencia) and fila.referencia,
             "notas": f"Importado del Excel V2 ({fila.ref}). {fila.observaciones}".strip()}
    if fila.monto_bs is not None and fila.equivalente_usd is not None:
        # Lo acordado manda: la tasa sale de dividir, no de la tabla de tasas.
        tasa = (fila.monto_bs / fila.equivalente_usd).quantize(Decimal("0.00000001"))
        return {**comun, "monto_moneda": fila.monto_bs, "tasa_manual": tasa, "tasa_id": None,
                "monto_usd": fila.equivalente_usd, "origen": "acordado", "avisos": avisos}
    if fila.monto_bs is not None:
        tasa = _tasa_para(estado, fila.fecha)
        if tasa is None:
            return (
                f"Pago en bolívares sin equivalente y sin tasa BCV de {fila.fecha} (la más "
                f"reciente tiene más de {TASA_MAX_DIAS} días). Poner al día las tasas y repetir."
            )
        valor, tasa_id = tasa
        usd = (fila.monto_bs / valor).quantize(Decimal("0.01"))
        avisos.append(
            f"El libro no trae el equivalente: se convierte con la tasa BCV vigente el "
            f"{fila.fecha} ({valor}), igual que lo haría la pantalla de abonos."
        )
        return {**comun, "monto_moneda": fila.monto_bs, "tasa_manual": None, "tasa_id": tasa_id,
                "monto_usd": usd, "origen": "bcv_del_dia", "avisos": avisos}
    # Solo equivalente en dólares.
    if canal in ("pago_movil", "transferencia", "efectivo_bs"):
        # Se pagó en bolívares pero el monto no consta. Registrarlo con un monto en Bs
        # supuesto seria inventarlo; se registra lo que si se sabe: el equivalente.
        avisos.append(
            f"Método '{fila.metodo}' sin monto en bolívares: se registra el equivalente "
            f"${fila.equivalente_usd} como 'otro (en divisa)'."
        )
        comun.update(canal="otro", en_bolivares=False)
    return {**comun, "monto_moneda": fila.equivalente_usd, "tasa_manual": None, "tasa_id": None,
            "monto_usd": fila.equivalente_usd, "origen": "divisa", "avisos": avisos}


def _categoria(concepto: str) -> str:
    clave = clave_nombre(concepto)
    if any(p in clave for p in ("envio", "transporte", "yummy", "delivery")):
        return "Envíos y transporte"
    if "publicidad" in clave:
        return "Publicidad"
    return "General"


def _cruzar_egresos(estado: Estado, libro: Libro, plan: Plan) -> None:
    for fila in libro.egresos:
        comun = {"etapa": "egresos", "ref": fila.ref, "hoja": fila.hoja, "fila": fila.numero,
                 "crudo": {**fila.crudo, "_ref": fila.ref}}
        es_compra = fila.tipo.strip().lower() == "compra"
        tabla = "lotes_compra" if es_compra else "gastos"
        if fila.tratamiento != "Incluir":
            motivo = (
                "Sin caja: consumo o publicidad en especie, no una salida de dinero."
                if fila.tratamiento == "Sin caja"
                else f"El libro lo marca '{fila.tratamiento}'."
            )
            plan.acciones.append(Accion(**comun, tipo="omitir", motivo=motivo))
            continue

        codigo = f"EXCEL-{fila.ref}"
        existente = estado.linaje.get((tabla, fila.ref))
        if existente is None and es_compra:
            existente = next((lo["id"] for lo in estado.lotes if lo["codigo"] == codigo), None)
        monto_usd, tasa, avisos = fila.monto_usd, None, []
        if monto_usd is None and fila.monto_bs is not None:
            resuelta = _tasa_para(estado, fila.fecha)
            if resuelta is None:
                plan.acciones.append(Accion(
                    **comun, tipo="omitir",
                    motivo=f"Monto solo en Bs y sin tasa BCV reciente para {fila.fecha}.",
                ))
                continue
            tasa = resuelta[0]
            monto_usd = (fila.monto_bs / tasa).quantize(Decimal("0.01"))
            avisos.append(f"Convertido con la tasa BCV del {fila.fecha} ({tasa}).")
        elif monto_usd is not None and fila.monto_bs:
            tasa = (fila.monto_bs / monto_usd).quantize(Decimal("0.00000001"))
        if monto_usd is None or monto_usd <= 0:
            plan.acciones.append(Accion(**comun, tipo="omitir", motivo="Sin monto."))
            continue
        if existente is None and not es_compra:
            existente = next(
                (g["id"] for g in estado.gastos
                 if g["fecha"] == fila.fecha and abs(g["monto_usd"] - monto_usd) < CENTAVO
                 and _parecido(g["descripcion"], fila.concepto) >= 0.8),
                None,
            )
        if existente is not None:
            plan.acciones.append(Accion(**comun, tipo="igual", destino_id=existente,
                                        metodo="exacto", score=1.0,
                                        motivo="Ya está en la base."))
            continue
        canal, _ = _canal(fila.metodo, fila.base, fila.monto_bs is not None)
        if canal == "otro":
            avisos.append(f"Método '{fila.metodo}': se registra sin canal.")
            canal = None
        plan.acciones.append(Accion(
            **comun, tipo="crear", metodo="exacto", motivo="No está en la base.", avisos=avisos,
            datos={
                "tabla": tabla,
                "codigo": codigo,
                "fecha": fila.fecha,
                "concepto": fila.concepto,
                "categoria": _categoria(fila.concepto),
                "monto_usd": monto_usd,
                "monto_bs": fila.monto_bs,
                "tasa": tasa,
                "canal": canal,
                "notas": f"Importado del Excel V2 ({fila.ref}). {fila.observaciones}".strip(),
            },
        ))


def _cruzar_costos(estado: Estado, libro: Libro, plan: Plan) -> None:
    """Completa costos faltantes. **Nunca pisa** un costo que ya este en la base.

    Solo con cruce exacto (nombre o alias): asociar por parecido aca le pondria el
    costo de un perfume a otro, y ese costo es la base del precio de venta.
    """
    for fila in libro.costos:
        if fila.costo_usd is None or fila.costo_usd <= 0:
            continue
        comun = {"etapa": "costos", "ref": fila.ref, "hoja": fila.hoja, "fila": fila.numero,
                 "crudo": {**fila.crudo, "_ref": fila.ref}}
        # Mismo nombre no alcanza: "Bharara King" existe como Top Quality y como
        # original ($119). El precio de lista del original no puede ir a parar al Top
        # Quality, asi que el cruce exige ademas que coincida si es original o no.
        clave = clave_nombre(fila.producto)
        candidatos = [
            p for p in estado.productos
            if bool(p["es_original"]) == fila.es_original
            and (clave_nombre(p["nombre"]) == clave
                 or clave_nombre(p["nombre"].split(",", 1)[-1]) == clave)
        ]
        if len(candidatos) != 1:
            continue
        producto = candidatos[0]
        pid = producto["id"]
        campo = "precio_original_usd" if fila.es_original else "costo_usd"
        if producto[campo] is not None:
            continue
        plan.acciones.append(Accion(
            **comun, tipo="actualizar", destino_id=pid, metodo="exacto", score=1.0,
            motivo=f"'{producto['nombre']}' no tiene {campo.replace('_usd', '')} cargado.",
            cambios={campo: [None, str(fila.costo_usd)]},
            datos={"campo": campo, "valor": fila.costo_usd, "linea": fila.linea,
                   "modelo": "lista" if fila.es_original else "costo"},
        ))


# --------------------------------------------------------------------- entrada
def planificar(sesion: Session, libro: Libro, *, mapeo: str, con_costos: bool = True) -> Plan:
    plan = Plan(archivo=libro.archivo, hash=libro.hash)
    plan.ya_aplicado = bool(
        sesion.execute(
            text("SELECT 1 FROM importaciones WHERE archivo_hash = :h AND estado = 'aplicado'"),
            {"h": libro.hash},
        ).scalar()
    )
    estado = Estado(sesion, mapeo)
    if con_costos:
        _cruzar_costos(estado, libro, plan)
    ventas = _cruzar_ventas(estado, libro, plan)
    _cruzar_pagos(estado, libro, plan, ventas)
    _cruzar_egresos(estado, libro, plan)
    return plan


# Alias usado por la carga para reconocer las etapas de venta y egreso.
__all__ = ["Accion", "Plan", "planificar", "EgresoFila", "VentaFila"]
