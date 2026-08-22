"""El precio de politica y el guardia que lo hace cumplir.

**Este modulo es la razon de ser del proyecto.** El informe midio $123 perdidos en
56 dias —26 % de la ganancia del periodo— porque 14 ventas marcadas `BCV` (+120 %
sobre el costo) se cobraron al nivel divisa (+70 %). Sobre las 30 ventas ya migradas
la fuga medida es de $68,40 en 13 lineas.

La causa no era humana, era estructural: `register_sale` fijaba `moneda="BCV"` a mano
mientras el formulario sugeria `max(precio_bcv, precio_divisa)`. El nivel declarado y
el precio cobrado los calculaban dos expresiones que nunca se encontraban.

Aca hay una sola funcion, y la llaman tanto el preview (`POST /ventas/cotizar`) como
la escritura (`POST /ventas`). Por eso la UI no puede mostrar un numero que la API
acepte distinto.

Ninguna de las cuatro reglas prohibe cobrar menos. Lo que hacen es exigir que se diga
por que, y dejarlo firmado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errors import (
    CODIGO_COSTO_DESCONOCIDO,
    CODIGO_PRECIO_BAJO_COSTO,
    CODIGO_PRECIO_FUERA_DE_BANDA,
    CODIGO_PRECIO_NIVEL_INCORRECTO,
    CODIGO_PRECIO_SOBRE_POLITICA,
)
from app.core.dinero import cuantizar
from app.models.enums import Moneda, NivelPrecio
from app.models.parametro import (
    CLAVE_DESC_REVENDEDOR,
    CLAVE_DESC_TEAM,
    CLAVE_GANANCIA_BCV,
    CLAVE_GANANCIA_DIVISA,
    CLAVE_TOLERANCIA_PRECIO_PCT,
)
from app.services.parametros import parametros_vigentes

#: Hasta que distancia del nivel alternativo se sigue considerando "es ese nivel".
#:
#: La regla principal es COMPARATIVA —el precio esta mas cerca del otro nivel que del
#: declarado— y este numero solo evita que un precio disparatado se etiquete como
#: confusion de nivel: $5 sobre un costo de $12 no es "el nivel divisa", es un error.
#:
#: Una tolerancia fija y estrecha no servia: probada contra las 13 lineas reales con
#: fuga, un 3 % no detectaba ninguna, porque los precios cobrados ($22 donde el nivel
#: divisa es $20,40) estan al 7-8 % del alternativo, no al 3 %.
DISTANCIA_MAXIMA_AL_NIVEL = Decimal("0.25")


@dataclass(frozen=True)
class PrecioPolitica:
    """Lo que el negocio deberia cobrar por esta linea, y con que base."""

    precio_usd: Decimal | None
    #: El precio del OTRO nivel, para poder ofrecer "cambiá el nivel" como salida.
    precio_alternativo_usd: Decimal | None
    nivel_alternativo: str | None
    base: str
    factor: Decimal | None
    costo_usd: Decimal | None

    @property
    def calculable(self) -> bool:
        return self.precio_usd is not None


@dataclass
class Advertencia:
    codigo: str
    mensaje: str
    #: True cuando la venta no se puede guardar sin resolverla o autorizarla.
    bloqueante: bool
    detalles: dict[str, object] = field(default_factory=dict)
    sugerencia: str | None = None
    #: Solo un admin puede autorizar la excepcion.
    exige_admin: bool = False


@dataclass
class Evaluacion:
    """El resultado del guardia para una linea."""

    politica: PrecioPolitica
    cobrado_usd: Decimal
    desviacion_pct: Decimal | None
    advertencias: list[Advertencia] = field(default_factory=list)

    @property
    def bloqueada(self) -> bool:
        return any(a.bloqueante for a in self.advertencias)

    @property
    def codigos(self) -> list[str]:
        return [a.codigo for a in self.advertencias]


def _producto(sesion: Session, producto_id: int):
    fila = sesion.execute(
        text(
            "SELECT id, nombre, modelo_precio::text AS modelo_precio, costo_usd, "
            "precio_original_usd FROM productos WHERE id = :i"
        ),
        {"i": producto_id},
    ).one_or_none()
    return fila


def precio_politica(
    sesion: Session,
    producto_id: int,
    *,
    moneda_cotizacion: Moneda | str,
    nivel: NivelPrecio | str = NivelPrecio.PUBLICO,
    en_fecha: date | None = None,
) -> PrecioPolitica:
    """El precio que corresponde por politica, y el del nivel alternativo.

    `modelo_precio = 'costo'` (Top Quality): precio = costo x (1 + ganancia), donde la
    ganancia es +70 % en divisa/USDT y +120 % a tasa BCV. **Sobre el costo, no sobre
    el precio de venta**: es como el negocio lo define, confirmado por el dueno.

    `modelo_precio = 'lista'` (Originales): precio = precio original x (1 - descuento).
    """
    fila = _producto(sesion, producto_id)
    if fila is None:
        return PrecioPolitica(None, None, None, "producto_inexistente", None, None)

    p = parametros_vigentes(sesion, en_fecha)
    moneda = str(getattr(moneda_cotizacion, "value", moneda_cotizacion))
    nivel_txt = str(getattr(nivel, "value", nivel))

    if fila.modelo_precio == "costo":
        if fila.costo_usd is None:
            return PrecioPolitica(None, None, None, "sin_costo", None, None)
        es_bcv = moneda == Moneda.VES.value
        factor = p[CLAVE_GANANCIA_BCV] if es_bcv else p[CLAVE_GANANCIA_DIVISA]
        otro_factor = p[CLAVE_GANANCIA_DIVISA] if es_bcv else p[CLAVE_GANANCIA_BCV]
        return PrecioPolitica(
            precio_usd=cuantizar(fila.costo_usd * (1 + factor)),
            precio_alternativo_usd=cuantizar(fila.costo_usd * (1 + otro_factor)),
            nivel_alternativo=Moneda.USD.value if es_bcv else Moneda.VES.value,
            base="costo",
            factor=factor,
            costo_usd=fila.costo_usd,
        )

    # modelo 'lista'
    if fila.precio_original_usd is None:
        return PrecioPolitica(None, None, None, "sin_precio_de_lista", None, None)
    descuentos = {
        NivelPrecio.PUBLICO.value: Decimal(0),
        NivelPrecio.TEAM.value: p[CLAVE_DESC_TEAM],
        NivelPrecio.REVENDEDOR.value: p[CLAVE_DESC_REVENDEDOR],
    }
    descuento = descuentos.get(nivel_txt, Decimal(0))
    return PrecioPolitica(
        precio_usd=cuantizar(fila.precio_original_usd * (1 - descuento)),
        precio_alternativo_usd=None,
        nivel_alternativo=None,
        base="lista",
        factor=descuento,
        costo_usd=fila.costo_usd,
    )


def evaluar_precio(
    sesion: Session,
    *,
    producto_id: int,
    precio_unitario_usd: Decimal,
    costo_unitario_usd: Decimal | None = None,
    moneda_cotizacion: Moneda | str = Moneda.VES,
    nivel: NivelPrecio | str = NivelPrecio.PUBLICO,
    en_fecha: date | None = None,
) -> Evaluacion:
    """Las cuatro reglas del guardia, en orden de gravedad."""
    politica = precio_politica(
        sesion, producto_id, moneda_cotizacion=moneda_cotizacion, nivel=nivel, en_fecha=en_fecha
    )
    cobrado = cuantizar(precio_unitario_usd)
    costo = costo_unitario_usd if costo_unitario_usd is not None else politica.costo_usd
    p = parametros_vigentes(sesion, en_fecha)
    advertencias: list[Advertencia] = []

    desviacion = None
    if politica.calculable and politica.precio_usd:
        desviacion = (cobrado - politica.precio_usd) / politica.precio_usd

    # 1. Por debajo del costo. Siempre bloqueante, siempre con firma de admin.
    if costo is not None and cobrado < costo:
        perdida = cuantizar(costo - cobrado)
        advertencias.append(
            Advertencia(
                codigo=CODIGO_PRECIO_BAJO_COSTO,
                mensaje=(
                    f"Estás cobrando ${cobrado} y el producto cuesta ${cuantizar(costo)}: "
                    f"perdés ${perdida} por unidad."
                ),
                bloqueante=True,
                exige_admin=True,
                detalles={
                    "cobrado": str(cobrado),
                    "costo": str(cuantizar(costo)),
                    "perdida_por_unidad": str(perdida),
                },
                sugerencia="Si es a propósito, un socio tiene que autorizarlo con un motivo.",
            )
        )

    # 2. LA FUGA DE $123: se declara BCV pero se cobra el nivel divisa.
    if (
        politica.calculable
        and politica.precio_alternativo_usd
        and politica.precio_usd
        and cobrado < politica.precio_usd
    ):
        alternativo = politica.precio_alternativo_usd
        # El precio esta mas cerca del OTRO nivel que del declarado.
        #
        # Comparativo y no una tolerancia fija: es lo que de verdad distingue
        # "cobraste el nivel equivocado" de "diste un descuento". $22 sobre un costo
        # de $12 dista $1,60 del nivel divisa ($20,40) y $4,40 del BCV ($26,40): es
        # una venta divisa mal etiquetada. $24 dista $3,60 y $2,40: es un descuento
        # sobre BCV, y cae en la regla 3.
        mas_cerca_del_otro = (
            alternativo > 0
            and abs(cobrado - alternativo) < abs(cobrado - politica.precio_usd)
            and abs(cobrado - alternativo) / alternativo <= DISTANCIA_MAXIMA_AL_NIVEL
        )
        if mas_cerca_del_otro:
            diferencia = cuantizar(politica.precio_usd - cobrado)
            nombre_declarado = (
                "BCV"
                if str(getattr(moneda_cotizacion, "value", moneda_cotizacion)) == Moneda.VES.value
                else "divisa/USDT"
            )
            nombre_otro = "divisa/USDT" if nombre_declarado == "BCV" else "BCV"
            advertencias.append(
                Advertencia(
                    codigo=CODIGO_PRECIO_NIVEL_INCORRECTO,
                    mensaje=(
                        f"Declarás {nombre_declarado} pero el precio es el de "
                        f"{nombre_otro}: ${cobrado} en vez de ${politica.precio_usd}. "
                        f"Diferencia ${diferencia}."
                    ),
                    bloqueante=True,
                    detalles={
                        "cobrado": str(cobrado),
                        "precio_esperado": str(politica.precio_usd),
                        "precio_del_otro_nivel": str(alternativo),
                        "diferencia": str(diferencia),
                        "nivel_declarado": nombre_declarado,
                        "nivel_equivalente": nombre_otro,
                        "moneda_sugerida": politica.nivel_alternativo,
                    },
                    sugerencia=(
                        f"Lo más probable es que la venta sea {nombre_otro}: cambiá la "
                        f"moneda y el registro queda correcto. Si de verdad es "
                        f"{nombre_declarado} con descuento, poné el motivo."
                    ),
                )
            )

    # 3. Fuera de la banda de tolerancia, sin que sea el otro nivel.
    #
    # La regla es ASIMETRICA a proposito. Cobrar por debajo de la politica le cuesta
    # plata al negocio, asi que bloquea hasta que alguien nombre el motivo. Cobrar por
    # ARRIBA no le cuesta nada: solo se avisa, porque de vez en cuando es un tipeo
    # ($220 en vez de $22) y conviene que salte a la vista, pero no hay nada que
    # autorizar. Tratar los dos casos igual seria pedirle al vendedor que justifique
    # haber vendido bien.
    tolerancia = p[CLAVE_TOLERANCIA_PRECIO_PCT]
    ya_reportado = {a.codigo for a in advertencias}
    if (
        desviacion is not None
        and abs(desviacion) > tolerancia
        and CODIGO_PRECIO_NIVEL_INCORRECTO not in ya_reportado
        and CODIGO_PRECIO_BAJO_COSTO not in ya_reportado
    ):
        por_debajo = desviacion < 0
        detalles = {
            "cobrado": str(cobrado),
            "precio_politica": str(politica.precio_usd),
            "desviacion_pct": str(cuantizar(desviacion * 100)),
            "tolerancia_pct": str(cuantizar(tolerancia * 100)),
            "por_debajo": por_debajo,
        }
        if por_debajo:
            advertencias.append(
                Advertencia(
                    codigo=CODIGO_PRECIO_FUERA_DE_BANDA,
                    mensaje=(
                        f"El precio está {abs(desviacion) * 100:.1f} % por debajo de la "
                        f"política (${politica.precio_usd})."
                    ),
                    bloqueante=True,
                    detalles=detalles,
                    sugerencia="Los descuentos existen; solo hay que nombrarlos.",
                )
            )
        else:
            advertencias.append(
                Advertencia(
                    codigo=CODIGO_PRECIO_SOBRE_POLITICA,
                    mensaje=(
                        f"El precio está {desviacion * 100:.1f} % por encima de la "
                        f"política (${politica.precio_usd}). Revisá que no sea un tipeo."
                    ),
                    bloqueante=False,
                    detalles=detalles,
                )
            )

    # 4. Sin costo: se acepta, se marca. Es trabajo visible, no un bloqueo.
    if not politica.calculable:
        advertencias.append(
            Advertencia(
                codigo=CODIGO_COSTO_DESCONOCIDO,
                mensaje="Este producto no tiene costo cargado: no puedo validar el precio.",
                bloqueante=False,
                detalles={"base": politica.base},
                sugerencia="Cargá el costo cuando lo sepas y el producto sale de revisión.",
            )
        )

    return Evaluacion(
        politica=politica,
        cobrado_usd=cobrado,
        desviacion_pct=cuantizar(desviacion) if desviacion is not None else None,
        advertencias=advertencias,
    )
