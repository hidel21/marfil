"""Exportaciones CSV y recibos PDF descargables."""

from __future__ import annotations

import csv
import io
from datetime import date

from fastapi import APIRouter
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import text

from app.api.deps import SesionDb, SoloAdmin, Usuario
from app.api.errors import NoEncontrado
from app.integrations.pdf.recibos import generar_recibo

router = APIRouter(prefix="/reportes", tags=["reportes"])

CONSULTAS = {
    "productos": """
        SELECT nombre, linea, stock, costo_usd, precio_divisa_usd, precio_bcv_usd
          FROM v_precio_vigente ORDER BY nombre
    """,
    "ventas": """
        SELECT v.codigo, v.fecha, c.nombre AS cliente, u.nombre AS vendedor,
               v.total_usd, v.saldo_usd, v.estado_cobro
          FROM ventas v JOIN clientes c ON c.id=v.cliente_id
          JOIN usuarios u ON u.id=v.vendedor_usuario_id
         ORDER BY v.fecha DESC, v.id DESC
    """,
    "pagos": """
        SELECT p.fecha, v.codigo AS venta, c.nombre AS cliente, p.moneda,
               p.monto_moneda, p.tasa_aplicada, p.monto_usd,
               p.canal, p.referencia
          FROM pagos p JOIN ventas v ON v.id=p.venta_id
          JOIN clientes c ON c.id=v.cliente_id ORDER BY p.fecha DESC, p.id DESC
    """,
    "clientes": """
        SELECT nombre, telefono_e164, email, nivel_precio, es_socio, notas
          FROM clientes WHERE estado='activo' ORDER BY nombre
    """,
    "compras": """
        SELECT codigo, fecha, proveedor, total_usd, pagado_usd, saldo_usd, diferencia_usd
          FROM v_cuentas_pagar ORDER BY fecha DESC NULLS LAST
    """,
    "gastos": """
        SELECT fecha, categoria, descripcion, monto_usd, monto_bs, tasa_aplicada, canal
          FROM gastos ORDER BY fecha DESC, id DESC
    """,
}


@router.get("/exportar/{entidad}")
def exportar(entidad: str, db: SesionDb, actual: SoloAdmin):
    del actual
    consulta = CONSULTAS.get(entidad)
    if consulta is None:
        raise NoEncontrado("ese tipo de reporte")
    filas = db.execute(text(consulta)).mappings().all()
    salida = io.StringIO()
    if filas:
        escritor = csv.DictWriter(salida, fieldnames=list(filas[0].keys()))
        escritor.writeheader()
        escritor.writerows(dict(f) for f in filas)
    contenido = "\ufeff" + salida.getvalue()
    nombre = f"marfil-{entidad}-{date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([contenido.encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.get("/recibos/{pago_id}.pdf")
def recibo(pago_id: int, db: SesionDb, actual: Usuario):
    fila = (
        db.execute(
            text(
                """
            SELECT p.id, p.fecha, p.moneda::text AS moneda, p.monto_moneda,
                   p.tasa_aplicada, p.monto_usd, p.canal::text AS canal,
                   p.referencia, v.codigo AS venta, v.saldo_usd,
                   c.nombre AS cliente
              FROM pagos p JOIN ventas v ON v.id = p.venta_id
              JOIN clientes c ON c.id = v.cliente_id WHERE p.id = :i
            """
            ),
            {"i": pago_id},
        )
        .mappings()
        .one_or_none()
    )
    if fila is None:
        raise NoEncontrado("ese pago")
    if (
        actual.rol.value == "afiliado"
        and actual.cliente_id
        != db.execute(
            text("SELECT cliente_id FROM ventas v JOIN pagos p ON p.venta_id=v.id WHERE p.id=:i"),
            {"i": pago_id},
        ).scalar()
    ):
        raise NoEncontrado("ese pago")
    pdf = generar_recibo(dict(fila))
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="recibo-{pago_id}.pdf"'},
    )
