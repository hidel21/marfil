"""Reportar: el plan en Markdown (para leer) y JSON (para guardar o comparar).

El Markdown se ordena por lo que hay que mirar: primero el resumen, despues lo que
cambia datos existentes (actualizaciones y correcciones), despues lo nuevo, y al
final lo omitido con su motivo. Lo que queda igual solo se cuenta.
"""

from __future__ import annotations

import json

from app.etl.cruce import Plan

ETAPAS = [
    ("costos", "Costos de productos"),
    ("ventas", "Ventas"),
    ("pagos", "Pagos"),
    ("egresos", "Gastos y compras"),
]
TIPOS = ["crear", "actualizar", "corregir", "igual", "omitir"]


def a_json(plan: Plan) -> str:
    return json.dumps(
        {
            "archivo": plan.archivo,
            "hash": plan.hash,
            "ya_aplicado": plan.ya_aplicado,
            "resumen": plan.resumen(),
            "acciones": [a.como_dict() for a in plan.acciones],
            "solo_en_base": plan.solo_en_base,
        },
        ensure_ascii=False,
        indent=1,
        default=str,
    )


def a_markdown(plan: Plan, *, titulo: str = "Plan de importación") -> str:
    r = plan.resumen()
    lineas = [
        f"# {titulo}",
        "",
        f"Archivo `{plan.archivo}` · hash `{plan.hash[:12]}`",
        "",
    ]
    if plan.ya_aplicado:
        lineas += ["> **Este archivo ya se aplicó.** Aplicarlo de nuevo se rechaza.", ""]

    lineas += ["| Etapa | " + " | ".join(TIPOS) + " |", "|---|" + "---:|" * len(TIPOS)]
    for clave, nombre in ETAPAS:
        fila = r.get(clave, {})
        celdas = " | ".join(str(fila.get(t) or "") for t in TIPOS)
        lineas.append(f"| {nombre} | {celdas} |")
    lineas.append("")

    def seccion(titulo_seccion: str, tipos: tuple[str, ...]) -> None:
        acciones = [a for a in plan.acciones if a.tipo in tipos]
        if not acciones:
            return
        lineas.extend([f"## {titulo_seccion}", ""])
        for clave, nombre in ETAPAS:
            grupo = [a for a in acciones if a.etapa == clave]
            if not grupo:
                continue
            lineas.extend([f"### {nombre} ({len(grupo)})", ""])
            for a in grupo:
                cambios = "; ".join(f"{k}: {v[0]} → {v[1]}" for k, v in a.cambios.items())
                extra = f" — {cambios}" if cambios else ""
                confianza = "" if a.confianza == "alta" else f" _(confianza {a.confianza})_"
                lineas.append(f"- **{a.ref}** (fila {a.fila}): {a.motivo}{extra}{confianza}")
                lineas.extend(f"  - ⚠ {aviso}" for aviso in a.avisos)
            lineas.append("")

    seccion("Cambian datos que ya existen", ("actualizar", "corregir"))
    seccion("Registros nuevos", ("crear",))
    seccion("No se cargan", ("omitir",))

    avisos_igual = [a for a in plan.acciones if a.tipo == "igual" and a.avisos]
    if avisos_igual:
        lineas.extend(["## Coinciden, pero con observaciones", ""])
        lineas.extend(
            f"- **{a.ref}**: {a.motivo} " + " ".join(a.avisos) for a in avisos_igual
        )
        lineas.append("")

    if plan.solo_en_base:
        lineas.extend([
            "## Están en la base y no en el libro",
            "",
            "No se tocan. Se listan para confirmar que no falte nada del lado del libro.",
            "",
        ])
        for s in plan.solo_en_base:
            lineas.append("- " + ", ".join(f"{k}: {v}" for k, v in s.items()))
        lineas.append("")
    return "\n".join(lineas)
