"""Registro de ventas: el guardia de precio hecho obligatorio.

Lo que la app vieja hacia y aca no puede pasar:
 - fijar `moneda='BCV'` a mano mientras el precio venia de `max(precio_bcv,
   precio_divisa)`: el nivel declarado y el precio cobrado ahora son el mismo dato;
 - dejar `deuda` como un numero libre que podia contradecir el total: el saldo lo
   calcula el trigger desde el libro;
 - bloquear una venta porque el producto no esta en el catalogo o porque no hay stock.

El descuento de stock atomico se conserva textual de `register_sale`:
`UPDATE ... WHERE id = ? AND stock >= ?` mas `rowcount != 1`. Es correcto y libre de
carrera, y era lo mejor del codigo anterior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errors import ErrorNegocio, NoEncontrado
from app.core.dinero import cuantizar, repartir
from app.models.enums import Moneda, NivelPrecio
from app.services.parametros import entero
from app.services.precios import Evaluacion, evaluar_precio


@dataclass
class LineaEntrada:
    producto_id: int
    cantidad: int
    precio_unitario_usd: Decimal
    #: Lo que el vendedor tecleo. Se guarda textual y nunca se sobrescribe.
    descripcion_libre: str | None = None
    costo_unitario_usd: Decimal | None = None
    motivo_desviacion: str | None = None


@dataclass
class CuotaEntrada:
    numero: int
    fecha_vencimiento: date
    monto_usd: Decimal


@dataclass
class VentaEntrada:
    cliente_id: int
    vendedor_usuario_id: int
    fecha: date
    moneda_cotizacion: Moneda
    lineas: list[LineaEntrada]
    nivel_precio: NivelPrecio = NivelPrecio.PUBLICO
    plazo_dias: int | None = None
    plan_cuotas: list[CuotaEntrada] | None = None
    abono_inicial_usd: Decimal | None = None
    notas: str | None = None
    #: Excepciones autorizadas, por indice de linea: {0: "cliente frecuente"}.
    autorizaciones: dict[int, str] = field(default_factory=dict)
    permitir_sobreventa: bool = False


@dataclass
class Cotizacion:
    """El preview. Lo devuelve `POST /ventas/cotizar` en cada tecla."""

    total_usd: Decimal
    costo_usd: Decimal
    ganancia_usd: Decimal
    lineas: list[dict]
    bloqueada: bool
    exige_admin: bool
    fecha_vencimiento: date
    plazo_dias: int


def cotizar(sesion: Session, entrada: VentaEntrada, *, es_admin: bool) -> Cotizacion:
    """Evalua la venta sin escribir nada.

    La misma funcion la usa `crear`, asi que la UI no puede mostrar un numero que la
    API acepte distinto.
    """
    if not entrada.lineas:
        raise ErrorNegocio(
            "VENTA_SIN_LINEAS", "La venta necesita al menos un producto.", campo="lineas"
        )

    plazo = entrada.plazo_dias
    if plazo is None:
        plazo = sesion.execute(
            text("SELECT plazo_credito_dias FROM clientes WHERE id = :c"),
            {"c": entrada.cliente_id},
        ).scalar()
    if plazo is None:
        plazo = entero(sesion, "PLAZO_CREDITO_DIAS", entrada.fecha)

    total = Decimal(0)
    costo_total = Decimal(0)
    detalle: list[dict] = []
    bloqueada = False
    exige_admin = False

    for indice, linea in enumerate(entrada.lineas):
        if linea.cantidad < 1:
            raise ErrorNegocio(
                "CANTIDAD_INVALIDA",
                "La cantidad tiene que ser al menos 1.",
                campo=f"lineas.{indice}.cantidad",
            )

        ev: Evaluacion = evaluar_precio(
            sesion,
            producto_id=linea.producto_id,
            precio_unitario_usd=linea.precio_unitario_usd,
            costo_unitario_usd=linea.costo_unitario_usd,
            moneda_cotizacion=entrada.moneda_cotizacion,
            nivel=entrada.nivel_precio,
            en_fecha=entrada.fecha,
        )

        motivo = entrada.autorizaciones.get(indice) or linea.motivo_desviacion
        pendientes = []
        for aviso in ev.advertencias:
            if not aviso.bloqueante:
                continue
            if motivo and (not aviso.exige_admin or es_admin):
                continue  # autorizada
            pendientes.append(aviso)
            if aviso.exige_admin and not es_admin:
                exige_admin = True
        if pendientes:
            bloqueada = True

        producto = sesion.execute(
            text("SELECT nombre, stock FROM productos WHERE id = :i"),
            {"i": linea.producto_id},
        ).one_or_none()
        if producto is None:
            raise NoEncontrado(f"el producto {linea.producto_id}")

        costo_unitario = (
            linea.costo_unitario_usd
            if linea.costo_unitario_usd is not None
            else (ev.politica.costo_usd or Decimal(0))
        )
        subtotal = cuantizar(linea.precio_unitario_usd * linea.cantidad)
        total += subtotal
        costo_total += cuantizar(costo_unitario * linea.cantidad)

        detalle.append(
            {
                "indice": indice,
                "producto_id": linea.producto_id,
                "producto": producto.nombre,
                "descripcion_libre": linea.descripcion_libre or producto.nombre,
                "cantidad": linea.cantidad,
                "precio_unitario_usd": cuantizar(linea.precio_unitario_usd),
                "costo_unitario_usd": cuantizar(costo_unitario),
                "precio_politica_usd": ev.politica.precio_usd,
                "precio_otro_nivel_usd": ev.politica.precio_alternativo_usd,
                "subtotal_usd": subtotal,
                "desviacion_pct": ev.desviacion_pct,
                "stock_actual": producto.stock,
                # El stock no es un techo: una venta sobre pedido tiene que poder
                # registrarse. Antes era imposible.
                "stock_resultante": producto.stock - linea.cantidad,
                "sobreventa": producto.stock < linea.cantidad,
                "motivo": motivo,
                "advertencias": [
                    {
                        "codigo": a.codigo,
                        "mensaje": a.mensaje,
                        "bloqueante": (
                            a.bloqueante and not (motivo and (not a.exige_admin or es_admin))
                        ),
                        "exige_admin": a.exige_admin,
                        "sugerencia": a.sugerencia,
                        "detalles": a.detalles,
                    }
                    for a in ev.advertencias
                ],
            }
        )

    return Cotizacion(
        total_usd=cuantizar(total),
        costo_usd=cuantizar(costo_total),
        ganancia_usd=cuantizar(total - costo_total),
        lineas=detalle,
        bloqueada=bloqueada,
        exige_admin=exige_admin,
        fecha_vencimiento=entrada.fecha + timedelta(days=plazo),
        plazo_dias=plazo,
    )


def crear(sesion: Session, entrada: VentaEntrada, *, usuario_id: int, es_admin: bool) -> int:
    """Registra la venta. Devuelve su id.

    El total, el costo y el saldo los calculan los triggers desde las lineas y el
    libro: no se escriben aca. La cuota implicita tambien la crea el trigger.
    """
    cotizacion = cotizar(sesion, entrada, es_admin=es_admin)

    if cotizacion.bloqueada:
        bloqueos = [
            a for linea in cotizacion.lineas for a in linea["advertencias"] if a["bloqueante"]
        ]
        primero = bloqueos[0]
        raise ErrorNegocio(
            primero["codigo"],
            primero["mensaje"],
            sugerencia=primero["sugerencia"],
            detalles={"lineas": cotizacion.lineas, "bloqueos": bloqueos},
        )

    if any(linea["sobreventa"] for linea in cotizacion.lineas) and not entrada.permitir_sobreventa:
        sobrevendidas = [linea for linea in cotizacion.lineas if linea["sobreventa"]]
        faltantes = ", ".join(f"{x['producto']} (hay {x['stock_actual']})" for x in sobrevendidas)
        raise ErrorNegocio(
            "SOBREVENTA_SIN_CONFIRMAR",
            f"No hay stock suficiente para {faltantes}.",
            sugerencia=(
                "Si es una venta sobre pedido, confirmá y queda registrada como tal. "
                "El stock puede quedar en negativo: es más honesto que no poder vender."
            ),
            detalles={"lineas": sobrevendidas},
        )

    if entrada.plan_cuotas:
        suma = cuantizar(sum(c.monto_usd for c in entrada.plan_cuotas))
        if abs(suma - cotizacion.total_usd) > Decimal("0.005"):
            raise ErrorNegocio(
                "CUOTAS_NO_SUMAN",
                f"Las cuotas suman ${suma} y la venta es de ${cotizacion.total_usd}.",
                campo="plan_cuotas",
                detalles={"suma_cuotas": str(suma), "total": str(cotizacion.total_usd)},
            )

    # Codigo provisional unico: el definitivo necesita el id, que todavia no existe.
    codigo_provisional = sesion.execute(
        text(
            "SELECT 'V-' || to_char(CAST(:f AS date), 'YYYY') || '-tmp-' "
            "|| nextval('ventas_codigo_seq')"
        ),
        {"f": entrada.fecha},
    ).scalar_one()

    venta_id = sesion.execute(
        text(
            "INSERT INTO ventas (codigo, fecha, cliente_id, vendedor_usuario_id, "
            "moneda_cotizacion, nivel_precio_aplicado, plazo_dias, fecha_vencimiento, "
            "tiene_plan_cuotas, notas, creado_por_usuario_id, "
            "cliente, vendedor, producto, cantidad, precio_venta, costo, ganancia, "
            "moneda, deuda, estatus, total) "
            "VALUES (:codigo, :fecha, :cliente, :vendedor, :moneda, :nivel, :plazo, "
            ":vence, :con_plan, :notas, :usuario, "
            "(SELECT nombre FROM clientes WHERE id = :cliente), "
            "(SELECT nombre FROM usuarios WHERE id = :vendedor), :producto, :cantidad, 0,0,0, "
            "'BCV', 0, 'PENDIENTE', 0) RETURNING id"
        ),
        {
            "codigo": codigo_provisional,
            "fecha": entrada.fecha,
            "cliente": entrada.cliente_id,
            "vendedor": entrada.vendedor_usuario_id,
            "moneda": entrada.moneda_cotizacion.value,
            "nivel": entrada.nivel_precio.value,
            "plazo": cotizacion.plazo_dias,
            "vence": cotizacion.fecha_vencimiento,
            "con_plan": bool(entrada.plan_cuotas),
            "notas": entrada.notas,
            "usuario": usuario_id,
            "producto": cotizacion.lineas[0]["descripcion_libre"],
            "cantidad": sum(linea["cantidad"] for linea in cotizacion.lineas),
        },
    ).scalar_one()

    sesion.execute(
        text(
            "UPDATE ventas SET codigo = 'V-' || to_char(fecha,'YYYY') || '-' || "
            "lpad(id::text, 4, '0') WHERE id = :i"
        ),
        {"i": venta_id},
    )

    for linea in cotizacion.lineas:
        # Descuento de stock atomico. Se conserva textual de register_sale: la
        # condicion `stock >= cantidad` en el propio UPDATE evita la carrera entre
        # leer y escribir.
        if not entrada.permitir_sobreventa:
            actualizadas = sesion.execute(
                text("UPDATE productos SET stock = stock - :c WHERE id = :i AND stock >= :c"),
                {"c": linea["cantidad"], "i": linea["producto_id"]},
            ).rowcount
            if actualizadas != 1:
                raise ErrorNegocio(
                    "STOCK_INSUFICIENTE",
                    f"Alguien más vendió {linea['producto']} mientras cargabas esta venta.",
                    sugerencia="Refrescá y volvé a intentar, o marcala como venta sobre pedido.",
                )
        else:
            sesion.execute(
                text("UPDATE productos SET stock = stock - :c WHERE id = :i"),
                {"c": linea["cantidad"], "i": linea["producto_id"]},
            )

        sesion.execute(
            text(
                "INSERT INTO movimientos_stock (producto_id, tipo, cantidad, saldo_despues, "
                "referencia_tabla, referencia_id, usuario_id) "
                "VALUES (:p, 'venta', :c, "
                "(SELECT stock FROM productos WHERE id = :p), 'ventas', :v, :u)"
            ),
            {"p": linea["producto_id"], "c": -linea["cantidad"], "v": venta_id, "u": usuario_id},
        )

        sesion.execute(
            text(
                "INSERT INTO venta_items (venta_id, linea, producto_id, descripcion_libre, "
                "cantidad, precio_unitario_usd, costo_unitario_usd, precio_lista_usd, "
                "motivo_desviacion, aprobado_por_usuario_id, sobreventa) "
                "VALUES (:v, :n, :p, :desc, :cant, :precio, :costo, :lista, :motivo, "
                ":aprobado, :sobreventa)"
            ),
            {
                "v": venta_id,
                "n": linea["indice"] + 1,
                "p": linea["producto_id"],
                "desc": linea["descripcion_libre"],
                "cant": linea["cantidad"],
                "precio": linea["precio_unitario_usd"],
                "costo": linea["costo_unitario_usd"],
                "lista": linea["precio_politica_usd"],
                "motivo": linea["motivo"],
                "aprobado": usuario_id if linea["motivo"] else None,
                "sobreventa": linea["sobreventa"],
            },
        )

    if entrada.plan_cuotas:
        # Se borra la cuota implicita que creo el trigger y se pone el plan real.
        sesion.execute(
            text("DELETE FROM cuotas WHERE venta_id = :v AND implicita"), {"v": venta_id}
        )
        for cuota in entrada.plan_cuotas:
            sesion.execute(
                text(
                    "INSERT INTO cuotas (venta_id, numero, fecha_vencimiento, monto_usd, "
                    "implicita) VALUES (:v, :n, :f, :m, FALSE)"
                ),
                {
                    "v": venta_id,
                    "n": cuota.numero,
                    "f": cuota.fecha_vencimiento,
                    "m": cuota.monto_usd,
                },
            )

    return venta_id


def plan_sugerido(
    total_usd: Decimal, cuotas: int, primera: date, frecuencia_dias: int = 30
) -> list[CuotaEntrada]:
    """Reparte el total en cuotas exactas: el resto va a la ultima."""
    montos = repartir(total_usd, cuotas)
    return [
        CuotaEntrada(
            numero=i + 1,
            fecha_vencimiento=primera + timedelta(days=frecuencia_dias * i),
            monto_usd=monto,
        )
        for i, monto in enumerate(montos)
    ]
