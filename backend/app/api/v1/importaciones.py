"""Importar el libro de Excel desde la app: subir, ver el plan, aplicar.

Es el mismo ETL de `python -m app.etl`, expuesto para quien no tiene una terminal ni
acceso directo a la base. Dos pasos a proposito:

    POST /importaciones/excel?modo=plan     → que haria, sin escribir nada
    POST /importaciones/excel?modo=aplicar  → lo hace, en una sola transaccion

`aplicar` no reutiliza un plan guardado: vuelve a cruzar el archivo contra la base
en la misma transaccion en la que escribe. Si entre el plan y la aplicacion alguien
cargo un abono a mano, el cruce lo ve y no lo duplica.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, File, Query, UploadFile
from sqlalchemy import text

from app.api.deps import PuedeEscribir, SesionDb, SoloAdmin
from app.api.errors import Conflicto, ErrorNegocio
from app.etl import carga, cruce, libro, reporte

router = APIRouter(prefix="/importaciones", tags=["importaciones"])

#: El libro real pesa ~250 KB; esto deja margen sin aceptar cualquier cosa.
TAMANO_MAXIMO = 10 * 1024 * 1024


@router.get("")
def historial(db: SesionDb, actual: SoloAdmin):
    """Las importaciones hechas, con cuantas filas quedaron ligadas a registros."""
    del actual
    filas = db.execute(
        text(
            """
            SELECT i.id, i.archivo, left(i.archivo_hash, 12) AS hash, i.mapeo_version,
                   i.estado, i.importado_at, u.nombre AS importado_por,
                   (SELECT count(*) FROM filas_importadas f WHERE f.importacion_id = i.id)
                       AS filas,
                   (SELECT count(*) FROM filas_importadas f
                      JOIN enlaces_importacion e ON e.fila_id = f.id
                     WHERE f.importacion_id = i.id) AS enlaces
              FROM importaciones i LEFT JOIN usuarios u ON u.id = i.importado_por_usuario_id
             ORDER BY i.id DESC
            """
        )
    ).all()
    return [dict(f._mapping) for f in filas]


@router.post("/excel")
def importar_excel(
    db: SesionDb,
    actual: SoloAdmin,
    _: PuedeEscribir,
    archivo: Annotated[UploadFile, File()],
    modo: Literal["plan", "aplicar"] = Query(default="plan"),
    con_costos: bool = Query(default=True),
):
    # Sincrono como el resto de la API: la sesion de base lo es, y en un endpoint
    # `async` cada consulta del cruce bloquearia el servidor entero.
    contenido = archivo.file.read(TAMANO_MAXIMO + 1)
    if len(contenido) > TAMANO_MAXIMO:
        raise ErrorNegocio("ARCHIVO_DEMASIADO_GRANDE", "El archivo supera los 10 MB.")
    if not contenido.startswith(b"PK"):
        # Un .xlsx es un zip; cualquier otra cosa no es el libro.
        raise ErrorNegocio(
            "ARCHIVO_INVALIDO",
            "Eso no parece un libro de Excel (.xlsx).",
            campo="archivo",
        )

    # openpyxl lee desde una ruta y el hash se calcula sobre los bytes exactos; con un
    # temporal se conserva el nombre original para el reporte y el linaje.
    with tempfile.TemporaryDirectory() as carpeta:
        ruta = Path(carpeta) / (Path(archivo.filename or "libro.xlsx").name)
        ruta.write_bytes(contenido)
        try:
            datos = libro.leer(ruta)
        except libro.LibroInvalido as exc:
            raise ErrorNegocio("LIBRO_INVALIDO", str(exc), campo="archivo") from exc

    plan = cruce.planificar(db, datos, mapeo=libro.MAPEO_VERSION, con_costos=con_costos)
    if modo == "plan":
        db.rollback()
        return {
            "modo": "plan",
            "ya_aplicado": plan.ya_aplicado,
            "resumen": plan.resumen(),
            "reporte_md": reporte.a_markdown(plan),
            "acciones": [a.como_dict() for a in plan.acciones],
            "solo_en_base": plan.solo_en_base,
        }

    try:
        resultado = carga.aplicar(db, plan, usuario_id=actual.id)
    except carga.PlanYaAplicado as exc:
        db.rollback()
        raise Conflicto("IMPORTACION_YA_APLICADA", str(exc)) from exc
    db.commit()
    return {
        "modo": "aplicar",
        "importacion_id": resultado.importacion_id,
        "aplicadas": resultado.aplicadas,
        "creados": resultado.creados,
        "reporte_md": reporte.a_markdown(
            plan, titulo=f"Importación aplicada (#{resultado.importacion_id})"
        ),
    }
