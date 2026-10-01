"""Analisis de ventas y cobros, filtrable por periodo y por dimension.

Responde "cuanto se vende en una semana, en quince dias, en un mes" y deja cortar por
vendedor, cliente, producto, linea, moneda y metodo de cobro. Cuatro decisiones:

- **Todo sale del mismo recorte.** Indicadores, serie y desgloses filtran contra las
  mismas ventas (`vf`), asi que los numeros de la pantalla siempre suman entre si.
- **Vendido y cobrado son preguntas distintas.** Vendido cuenta ventas *hechas* en el
  periodo; cobrado cuenta plata *entrada* en el periodo, de ventas que cumplen los
  filtros aunque se hayan hecho antes. Mezclarlos daria un "cobrado" que depende de
  cuando se vendio, no de cuando entro el dinero.
- **El periodo anterior tiene el mismo largo.** Comparar 15 dias contra el mes
  anterior siempre "baja"; contra los 15 dias previos dice algo.
- **La ganancia avisa cuando miente.** Una venta de un producto sin costo cargado
  cuenta como ganancia todo el precio. Se informa cuantas ventas estan asi en vez de
  presentar un margen que parece mejor de lo que es.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errors import ErrorNegocio

AGRUPACIONES = ("dia", "semana", "quincena", "mes")
MAXIMO_DIAS = 3 * 366

#: Del dia a su periodo. La quincena va del 1 al 15 y del 16 a fin de mes, que es
#: como se paga y se cobra en la practica, no cada 15 dias corridos.
_BALDE = {
    "dia": "{c}",
    "semana": "date_trunc('week', {c})::date",
    "quincena": (
        "CASE WHEN extract(day FROM {c}) <= 15 THEN date_trunc('month', {c})::date "
        "ELSE (date_trunc('month', {c}) + interval '15 days')::date END"
    ),
    "mes": "date_trunc('month', {c})::date",
}


def _balde(agrupar: str, columna: str) -> str:
    return _BALDE[agrupar].format(c=columna)


@dataclass(frozen=True)
class Filtros:
    desde: date
    hasta: date
    agrupar: str = "dia"
    vendedor_id: int | None = None
    cliente_id: int | None = None
    producto_id: int | None = None
    linea: str | None = None
    moneda: str | None = None
    canal: str | None = None

    def validar(self) -> None:
        if self.hasta < self.desde:
            raise ErrorNegocio("PERIODO_INVALIDO", "La fecha final es anterior a la inicial.")
        if (self.hasta - self.desde).days > MAXIMO_DIAS:
            raise ErrorNegocio("PERIODO_DEMASIADO_LARGO", "El periodo no puede pasar de 3 años.")
        if self.agrupar not in AGRUPACIONES:
            raise ErrorNegocio("AGRUPACION_INVALIDA", f"Agrupación desconocida: {self.agrupar!r}.")

    def anterior(self) -> Filtros:
        largo = (self.hasta - self.desde).days + 1
        return Filtros(**{
            **self.__dict__,
            "desde": self.desde - timedelta(days=largo),
            "hasta": self.desde - timedelta(days=1),
        })

    def parametros(self) -> dict:
        return {
            "desde": self.desde,
            "hasta": self.hasta,
            "vendedor": self.vendedor_id,
            "cliente": self.cliente_id,
            "producto": self.producto_id,
            "linea": self.linea,
            "moneda": self.moneda,
            "canal": self.canal,
        }


#: Las ventas que cumplen los filtros de dimension, sin mirar la fecha: la fecha la
#: aplica cada consulta, porque "vendido" y "cobrado" la miran distinto.
_VF = """
vf AS (
    SELECT v.*
      FROM ventas v
     WHERE v.anulada_at IS NULL
       AND (CAST(:vendedor AS integer) IS NULL OR v.vendedor_usuario_id = :vendedor)
       AND (CAST(:cliente AS integer) IS NULL OR v.cliente_id = :cliente)
       AND (CAST(:moneda AS text) IS NULL OR v.moneda_cotizacion::text = :moneda)
       AND (CAST(:producto AS integer) IS NULL OR EXISTS (
             SELECT 1 FROM venta_items i WHERE i.venta_id = v.id AND i.producto_id = :producto))
       AND (CAST(:linea AS text) IS NULL OR EXISTS (
             SELECT 1 FROM venta_items i JOIN productos p ON p.id = i.producto_id
              WHERE i.venta_id = v.id AND p.linea = :linea))
)
"""
#: Los cobros (abonos menos reversos) de esas ventas. El reverso resta en su fecha.
_COBROS = """
cobros AS (
    SELECT p.* FROM pagos p JOIN vf ON vf.id = p.venta_id
     WHERE CAST(:canal AS text) IS NULL OR p.canal::text = :canal
)
"""


def _indicadores(sesion: Session, f: Filtros) -> dict:
    fila = sesion.execute(
        text(
            f"""
            WITH {_VF}, {_COBROS},
            periodo AS (SELECT * FROM vf WHERE fecha BETWEEN :desde AND :hasta)
            SELECT
              (SELECT count(*) FROM periodo) AS ventas,
              (SELECT COALESCE(sum(total_usd), 0) FROM periodo) AS vendido_usd,
              (SELECT COALESCE(sum(total_usd - costo_usd), 0) FROM periodo) AS ganancia_usd,
              (SELECT COALESCE(sum(saldo_usd), 0) FROM periodo) AS por_cobrar_usd,
              (SELECT count(DISTINCT cliente_id) FROM periodo) AS clientes,
              (SELECT COALESCE(sum(i.cantidad), 0) FROM venta_items i
                 JOIN periodo ON periodo.id = i.venta_id) AS unidades,
              (SELECT count(*) FROM periodo WHERE costo_usd = 0) AS ventas_sin_costo,
              (SELECT COALESCE(sum(monto_usd), 0) FROM cobros
                WHERE fecha BETWEEN :desde AND :hasta) AS cobrado_usd
            """
        ),
        f.parametros(),
    ).mappings().one()
    datos = dict(fila)
    ventas = datos["ventas"] or 0
    vendido = Decimal(datos["vendido_usd"])
    datos["ticket_promedio_usd"] = (vendido / ventas).quantize(Decimal("0.01")) if ventas else None
    datos["margen_pct"] = (
        (Decimal(datos["ganancia_usd"]) * 100 / vendido).quantize(Decimal("0.1"))
        if vendido
        else None
    )
    return datos


def _serie(sesion: Session, f: Filtros) -> list[dict]:
    filas = sesion.execute(
        text(
            f"""
            WITH {_VF}, {_COBROS},
            dias AS (
                SELECT d::date AS d FROM generate_series(CAST(:desde AS date),
                                                         CAST(:hasta AS date), '1 day') d
            ),
            -- Cada periodo con los dias que de verdad caen dentro del rango: la primera
            -- semana de un rango que arranca un jueves va de jueves a domingo.
            baldes AS (
                SELECT {_balde(f.agrupar, "d")} AS balde, min(d) AS desde, max(d) AS hasta,
                       count(*) AS dias
                  FROM dias GROUP BY 1
            ),
            v AS (
                SELECT {_balde(f.agrupar, "fecha")} AS balde,
                       count(*) AS ventas, sum(total_usd) AS vendido_usd,
                       sum(total_usd - costo_usd) AS ganancia_usd
                  FROM vf WHERE fecha BETWEEN :desde AND :hasta GROUP BY 1
            ),
            c AS (
                SELECT {_balde(f.agrupar, "fecha")} AS balde,
                       sum(monto_usd) AS cobrado_usd
                  FROM cobros WHERE fecha BETWEEN :desde AND :hasta GROUP BY 1
            )
            SELECT b.desde, b.hasta, b.dias,
                   COALESCE(v.ventas, 0) AS ventas,
                   COALESCE(v.vendido_usd, 0) AS vendido_usd,
                   COALESCE(v.ganancia_usd, 0) AS ganancia_usd,
                   COALESCE(c.cobrado_usd, 0) AS cobrado_usd
              FROM baldes b
              LEFT JOIN v ON v.balde = b.balde
              LEFT JOIN c ON c.balde = b.balde
             ORDER BY b.desde
            """
        ),
        f.parametros(),
    ).mappings().all()
    return [dict(x) for x in filas]


def _desgloses(sesion: Session, f: Filtros) -> dict:
    base = (
        f"WITH {_VF}, {_COBROS}, "
        "periodo AS (SELECT * FROM vf WHERE fecha BETWEEN :desde AND :hasta) "
    )

    def q(sql: str) -> list[dict]:
        return [dict(x) for x in sesion.execute(text(base + sql), f.parametros()).mappings().all()]

    return {
        "productos": q(
            """
            SELECT p.id, p.nombre, p.linea, sum(i.cantidad) AS unidades,
                   sum(i.subtotal_usd) AS vendido_usd, sum(i.ganancia_usd) AS ganancia_usd,
                   bool_or(p.costo_usd IS NULL AND p.precio_original_usd IS NULL) AS sin_costo
              FROM venta_items i JOIN periodo ON periodo.id = i.venta_id
              JOIN productos p ON p.id = i.producto_id
             GROUP BY p.id, p.nombre, p.linea ORDER BY vendido_usd DESC LIMIT 200
            """
        ),
        "vendedores": q(
            """
            SELECT u.id, u.nombre, count(*) AS ventas, sum(periodo.total_usd) AS vendido_usd,
                   sum(periodo.total_usd - periodo.costo_usd) AS ganancia_usd
              FROM periodo JOIN usuarios u ON u.id = periodo.vendedor_usuario_id
             GROUP BY u.id, u.nombre ORDER BY vendido_usd DESC
            """
        ),
        "clientes": q(
            """
            SELECT c.id, c.nombre, count(*) AS ventas, sum(periodo.total_usd) AS vendido_usd,
                   sum(periodo.saldo_usd) AS por_cobrar_usd
              FROM periodo JOIN clientes c ON c.id = periodo.cliente_id
             GROUP BY c.id, c.nombre ORDER BY vendido_usd DESC LIMIT 200
            """
        ),
        "lineas": q(
            """
            SELECT COALESCE(p.linea, 'Sin línea') AS linea, sum(i.subtotal_usd) AS vendido_usd,
                   sum(i.cantidad) AS unidades
              FROM venta_items i JOIN periodo ON periodo.id = i.venta_id
              JOIN productos p ON p.id = i.producto_id
             GROUP BY 1 ORDER BY vendido_usd DESC
            """
        ),
        "monedas": q(
            """
            SELECT moneda_cotizacion::text AS moneda, count(*) AS ventas,
                   sum(total_usd) AS vendido_usd
              FROM periodo GROUP BY 1 ORDER BY vendido_usd DESC
            """
        ),
        "metodos": q(
            """
            SELECT COALESCE(canal::text, 'sin_dato') AS canal,
                   count(*) FILTER (WHERE tipo = 'abono') AS cobros, sum(monto_usd) AS cobrado_usd
              FROM cobros WHERE fecha BETWEEN :desde AND :hasta
             GROUP BY 1 ORDER BY cobrado_usd DESC
            """
        ),
    }


def opciones(sesion: Session) -> dict:
    """Los valores posibles de cada filtro: solo los que tienen ventas, para no ofrecer
    un cliente o producto que daria una pantalla vacia."""

    def q(sql: str) -> list[dict]:
        return [dict(x) for x in sesion.execute(text(sql)).mappings().all()]

    return {
        "vendedores": q(
            "SELECT DISTINCT u.id, u.nombre FROM usuarios u JOIN ventas v "
            "ON v.vendedor_usuario_id = u.id ORDER BY u.nombre"
        ),
        "clientes": q(
            "SELECT DISTINCT c.id, c.nombre FROM clientes c JOIN ventas v "
            "ON v.cliente_id = c.id ORDER BY c.nombre"
        ),
        "productos": q(
            "SELECT DISTINCT p.id, p.nombre FROM productos p JOIN venta_items i "
            "ON i.producto_id = p.id ORDER BY p.nombre"
        ),
        "lineas": [
            r["linea"]
            for r in q(
                "SELECT DISTINCT p.linea FROM productos p JOIN venta_items i "
                "ON i.producto_id = p.id WHERE p.linea IS NOT NULL ORDER BY 1"
            )
        ],
        "primera_venta": sesion.execute(text("SELECT min(fecha) FROM ventas")).scalar(),
    }


def analizar(sesion: Session, f: Filtros) -> dict:
    f.validar()
    previo = f.anterior()
    return {
        "periodo": {"desde": f.desde, "hasta": f.hasta, "agrupar": f.agrupar,
                    "dias": (f.hasta - f.desde).days + 1},
        "anterior": {"desde": previo.desde, "hasta": previo.hasta},
        "indicadores": _indicadores(sesion, f),
        "indicadores_anterior": _indicadores(sesion, previo),
        "serie": _serie(sesion, f),
        "desgloses": _desgloses(sesion, f),
    }
