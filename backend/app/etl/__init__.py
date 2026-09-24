"""ETL del libro "Sistema Marfil V2" hacia la base.

    python -m app.etl plan    <libro.xlsx>             # no escribe nada
    python -m app.etl aplicar <libro.xlsx> --confirmar  # una sola transaccion

Cuatro etapas, cada una en su modulo:

1. **Extraer** (`libro.py`): lee las hojas por *nombre de columna*, no por posicion,
   y descarta las filas de plantilla. El libro trae 250 IDs de venta ya generados y
   solo 75 tienen datos; importar los vacios crearia 175 ventas fantasma.

2. **Cruzar** (`cruce.py`): compara cada fila contra lo que ya hay en la base y
   decide que hacer con ella —crear, actualizar, corregir, dejar igual u omitir—
   con el motivo escrito. Es la etapa que evita los duplicados, y la mas delicada:
   la migracion original no tenia fecha de venta, asi que la misma venta tiene
   fechas distintas en cada lado y un cruce por igualdad duplicaria casi todo.

3. **Cargar** (`carga.py`): aplica el plan en **una** transaccion, pasando por los
   mismos servicios que usa la app (triggers de saldo, cuotas, auditoria), y deja el
   linaje en `importaciones` → `filas_importadas` → `enlaces_importacion`.

4. **Reportar** (`reporte.py`): el plan en Markdown y JSON, que es lo que se revisa
   antes de aplicar y lo que queda como evidencia despues.

El linaje es lo que hace **repetible** el proceso. La segunda vez que se carga una
version del libro, cada fila ya importada se reconoce por su ID de hoja (`V-031`,
`P-004`, `E-001`) en vez de por parecido, y solo se aplican las diferencias.
"""
