"""Linea de comandos del ETL.

    python -m app.etl plan    libro.xlsx [--md plan.md] [--json plan.json]
    python -m app.etl aplicar libro.xlsx --confirmar [--usuario-id 1] [--md resultado.md]

`plan` abre la transaccion, cruza y hace **rollback**: no escribe nada, ni siquiera
por accidente. `aplicar` vuelve a planificar dentro de la misma transaccion en la que
escribe, asi que aplica exactamente lo que el estado de la base permite en ese
momento, no lo que decia un plan de ayer.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.db.session import sesion_manual
from app.etl import carga, cruce, libro, reporte


def _escribir(ruta: str | None, contenido: str) -> None:
    if ruta:
        Path(ruta).write_text(contenido, encoding="utf-8")
        print(f"  escrito: {ruta}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.etl", description="ETL del Excel Marfil V2")
    sub = parser.add_subparsers(dest="comando", required=True)
    for nombre in ("plan", "aplicar"):
        p = sub.add_parser(nombre)
        p.add_argument("archivo")
        p.add_argument("--md", help="guardar el reporte en Markdown")
        p.add_argument("--json", help="guardar el plan completo en JSON")
        p.add_argument("--sin-costos", action="store_true",
                       help="no completar costos faltantes del catálogo")
        if nombre == "aplicar":
            p.add_argument("--confirmar", action="store_true",
                           help="obligatorio: sin esto no se escribe nada")
            p.add_argument("--usuario-id", type=int, required=True,
                           help="autor en la auditoría y vendedor por defecto")
    args = parser.parse_args(argv)

    datos = libro.leer(args.archivo)
    print(
        f"  libro: {len(datos.ventas)} ventas, {len(datos.pagos)} pagos, "
        f"{len(datos.egresos)} egresos, {len(datos.costos)} filas de catálogo"
    )

    if args.comando == "aplicar" and not args.confirmar:
        print("Falta --confirmar. Corré primero `plan` y revisá el reporte.", file=sys.stderr)
        return 2

    with sesion_manual() as sesion:
        plan = cruce.planificar(
            sesion, datos, mapeo=libro.MAPEO_VERSION, con_costos=not args.sin_costos
        )
        if args.comando == "plan":
            sesion.rollback()
            print(reporte.a_markdown(plan))
            _escribir(args.md, reporte.a_markdown(plan))
            _escribir(args.json, reporte.a_json(plan))
            return 0
        try:
            resultado = carga.aplicar(sesion, plan, usuario_id=args.usuario_id)
        except carga.PlanYaAplicado as exc:
            sesion.rollback()
            print(str(exc), file=sys.stderr)
            return 3
        # `sesion_manual` hace commit al salir sin excepcion.
    texto = reporte.a_markdown(plan, titulo=f"Importación aplicada (#{resultado.importacion_id})")
    print(texto)
    print(f"  aplicado: {resultado.aplicadas}")
    _escribir(args.md, texto)
    _escribir(args.json, reporte.a_json(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
