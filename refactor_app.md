# Refactor de `app.py` — análisis y plan

**Fecha:** 17/08/2026
**Alcance:** [app.py](app.py) (1.696 líneas), [database.py](database.py) (1.792), [services/](services/), [tests/](tests/)
**Contexto:** cierra el trabajo de [auditoria.md](auditoria.md) y del informe en [reports/](reports/).

Este documento es **análisis y plan**, no cambios aplicados. Cada afirmación está verificada contra el
código o ejecutando las propias funciones de la app; donde hay una medición, está el número.

La app cumple las convenciones del proyecto en [`.agents/skills/developing-with-streamlit`](.agents/skills/developing-with-streamlit/SKILL.md),
que marqué como referencia porque el propio repo la declara obligatoria para todo trabajo de Streamlit.

---

## 0. El hallazgo central

**El libro `SISTEMA_MARFIL_v2.xlsx` y la app ya no se hablan.** Las tres importaciones CSV que ofrece
la app rechazan el libro que acabo de entregar. Lo verifiqué ejecutando `normalize_column_name` y
`COLUMN_FIELD_MAP` de [app.py:126](app.py#L126) contra los encabezados reales de cada hoja:

| Entidad de la app | Hoja del libro v2 | Columnas obligatorias que faltan | Resultado |
|---|---|---|---|
| 📦 Productos / Inventario | `PRECIOS PERF TOP QUALITY` | `precio_divisa`, `precio_bcv`, `stock` | ❌ rechaza |
| 🛍️ Ventas Históricas | `VENTAS` | `fecha`, `estatus` | ❌ rechaza |
| 💰 Historial de Pagos / Cuotas | `REGISTRO DE CUOTAS` | `venta_id`, `monto_bs`, `monto_usd`, `tasa_bcv`, `nro_cuota` | ❌ rechaza |

Hay **dos causas distintas**, y conviene no confundirlas porque se arreglan en lados opuestos:

**(a) Un bug de normalización, en la app.** `normalize_column_name` reemplaza `" "` por `"_"` *después*
de borrar `($)`, así que todo encabezado que termine en `($)` queda con un guión bajo colgando:

```
"COSTO ($)"                 -> "costo_"                  ✓ (está en el mapa por casualidad)
"PRECIO TASA BCV ($)"       -> "precio_tasa_bcv_"        ✗ el mapa solo tiene "precio_tasa_bcv"
"PRECIO DIVISA / USDT ($)"  -> "precio_divisa___usdt_"   ✗ tres guiones seguidos
```

`COLUMN_FIELD_MAP` ([app.py:151](app.py#L151)) compensa esto **enumerando variantes a mano**: tiene
`costo` *y* `costo_`, `deuda` *y* `deuda_`, `ganancia` *y* `ganancia_`, `precio_venta` *y*
`precio_venta_`. Es un parche que cubre las variantes que alguien encontró y falla con la siguiente.
Cada encabezado nuevo con `($)` es un bug esperando.

**(b) Datos que el libro genuinamente no tiene** — y esto **no** se arregla en la app:

- **`stock`**: el libro no tiene hoja de inventario. Ya lo reporté en el informe; la app exige `stock`
  como obligatorio y no hay de dónde sacarlo.
- **`fecha` en VENTAS**: la hoja VENTAS no tiene columna de fecha (las fechas están en CONTROL).
- **`venta_id` / `tasa_bcv` / `monto_bs` en cuotas**: la hoja `REGISTRO DE CUOTAS` que creé está en
  dólares y no tiene ni ID de venta ni tasa, porque el Excel nunca guardó la tasa de cambio.

### Y aquí está lo importante

Ese punto (b) **no es un defecto de la app: es la razón para migrar a ella.** El modelo de
`database.py` resuelve exactamente los tres problemas que el Excel no podía:

| Problema del Excel (del informe) | Cómo lo resuelve la app |
|---|---|
| No se guarda la tasa Bs/$ → la cobranza en $ era una *estimación* mía | `Pago.tasa_bcv` por abono ([database.py:291](database.py#L291)) → cobranza exacta |
| VENTAS sin fecha → evolución temporal sacada de otra hoja | `Venta.fecha` obligatoria |
| No hay stock ni rotación calculable | `Producto.stock`, descontado atómicamente en cada venta |
| Cuotas en una hoja que no existía | Tabla `Pago` con FK a `Venta` |

**La conclusión de negocio del refactor:** el objetivo no es que la app importe el libro tal cual, sino
**cargar el libro una vez y dejar de usar Excel**. Para eso la importación tiene que aceptar lo que el
libro sí tiene y pedir explícitamente lo que falta, en vez de rechazar el archivo entero.

---

## 1. Contrato de datos (prioridad máxima)

### 1.1 Arreglar la normalización en la raíz

```python
# app.py:126 — ANTES: deja guiones bajos colgando y duplicados
def normalize_column_name(column: str) -> str:
    normalized = str(column).strip().lower()
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    return normalized

# DESPUÉS: colapsar y recortar; el mapa queda solo con claves canónicas
import re, unicodedata

def normalize_column_name(column: str) -> str:
    text = unicodedata.normalize("NFKD", str(column).strip().lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")
```

Con esto `"PRECIO TASA BCV ($)"` → `precio_tasa_bcv`, `"PRECIO DIVISA / USDT ($)"` →
`precio_divisa_usdt`, `"N° OPERACIÓN"` → `n_operacion`. Y **se pueden borrar las 5 entradas duplicadas
del mapa** (`costo_`, `deuda_`, `ganancia_`, `precio_venta_`, `monto_pagado_`), que dejan de tener
sentido. Menos código y más cobertura.

Hace falta añadir al mapa los alias reales del libro v2: `precio_divisa_usdt`, `monto_abonado`,
`linea`, `metodo`, `n_operacion`.

### 1.2 Que la importación informe en vez de rechazar

Hoy, si falta una columna obligatoria, se muestra un error y no se importa nada
([app.py:690](app.py#L690)). Para un libro real eso significa "no puedo cargar mi historia".

Mejor: separar **obligatorio** de **derivable** y **rellenable**.

- `stock` ausente → importar con `stock = 0` y avisar: *"se cargaron 212 productos con stock 0; hacé un
  conteo físico y cargalo en Productos & Stock"*. Es exactamente la recomendación 4 del informe.
- `fecha` ausente en ventas → pedir una fecha por defecto en la UI (o cruzar con CONTROL), no abortar.
- `estatus` ausente → derivarlo de la deuda, que es lo que ya hace `register_sale`
  ([app.py:953](app.py#L953)).
- `monto_abonado` en $ sin `tasa_bcv` → guardar `monto_usd` y dejar `monto_bs`/`tasa_bcv` en nulo,
  marcando el pago como "sin tasa registrada".

### 1.3 Lo que sí está bien y no hay que tocar

`parse_numeric_value` ([app.py:187](app.py#L187)) es **sólida**. La probé contra los formatos reales
que encontré en el Excel:

| Entrada | Resultado |
|---|---|
| `'15.679,22'` | `15679.22` ✓ |
| `'8.307,00'` | `8307.0` ✓ |
| `'$1.234,56'` | `1234.56` ✓ |
| `'Bs. 15.932,00'` | `15932.0` ✓ |
| `'12 EFECTIVO'` | `None` → rechaza ✓ |
| `'18.GM'` | `None` → rechaza ✓ |
| `'19 usdt P.M'` | `None` → rechaza ✓ |

Maneja la convención venezolana correctamente y **rechaza** los casos mixtos en vez de inventar un
número — que es justo lo que hay que hacer. Es mejor que lo que el Excel hacía con esas celdas.

Un solo riesgo: `'1.700'` → `1700.0`, porque asume que 3 decimales son separador de miles. Correcto
para bolívares, equivocado si alguien escribe el factor `1.700` queriendo decir 1,7. Vale un comentario
en el código, no un cambio.

---

## 2. Reglas de negocio que el informe pidió y la app no aplica

### 2.1 No hay piso de ganancia — las dos ventas bajo costo pasarían igual hoy

`register_sale` ([database.py](database.py)) valida importes negativos, cantidad positiva, deuda ≤
precio y stock suficiente. **No valida que el precio cubra el costo.** Las dos ventas que el informe
marcó en rojo (212 Vip a $9,50 costando $22; Club de Nuit a $30 costando $51) se registrarían hoy sin
una sola advertencia.

Propuesta: en la UI, comparar contra el costo del producto **antes** de enviar el formulario y exigir
confirmación explícita si la ganancia queda bajo el mínimo. La app ya tiene el dato a mano en
`producto_info["costo"]` ([app.py:950](app.py#L950)) — solo no lo mira.

El umbral no hay que inventarlo: la política de precios del negocio ya lo define como **ganancia sobre
el costo**, +70 % si el cliente paga en divisa/USDT y +120 % si paga a tasa BCV (parámetros
`GANANCIA_DIVISA` y `GANANCIA_BCV` del libro). Como el formulario de venta ya tiene `precio_bcv` y
`precio_divisa` del producto, puede avisar cuál de los dos niveles se está cobrando — que es
exactamente el problema de $123,00 que el informe cuantificó.

### 2.2 El nombre de producto es texto libre en tres tablas

El informe encontró 21 productos escritos de varias formas. La app **reproduce el problema**:
`Venta.producto` y `Pago.producto` guardan el nombre como `VARCHAR` copiado, y `Producto.nombre` no
tiene restricción de unicidad. `register_sale` ya recibe `producto_id`, así que la relación existe;
lo que falta es dejar de duplicar el texto y no permitir dos productos con el mismo nombre normalizado.

Esto importa porque la cobranza y los márgenes se agrupan por ese texto: dos formas de escribir
"Aqua di Gio" son dos productos distintos en todos los reportes.

### 2.3 El estatus tiene dos valores donde el negocio usa tres

`estatus = "YA PAGO" if deuda_inicial == 0 else "PENDIENTE"` ([app.py:953](app.py#L953)). El Excel usa
además `PENDIENTE (SIN ABONOS)`, que es el estado que el informe señaló como más riesgoso (16
operaciones). Conviene un `Enum` compartido entre la app y la BD, no cadenas sueltas.

---

## 3. Rendimiento — el problema más caro y el más fácil de arreglar

### 3.1 Cero caché sobre 37 llamadas a la base de datos por rerun

`services/rates.py` cachea con `@st.cache_data(ttl=1800)`. **`database.py` no cachea nada.** En
Streamlit, *cada* click vuelve a ejecutar el script completo: cada botón, cada `selectbox`, cada
pestaña. Hay 37 llamadas `load_*` en [app.py](app.py), y varias se repiten en el mismo rerun:

| Loader | Veces por rerun |
|---|---|
| `load_inventory_dataframe` | 3 |
| `load_proveedores_dataframe` | 2 |
| `load_all_sales_dataframe` | 2 |

Cada una abre sesión, consulta Postgres y construye un DataFrame fila por fila con un bucle Python
([database.py:324](database.py#L324)). Contra una base remota tipo Neon, eso son decenas de
viajes de red por cada interacción.

El arreglo es pequeño y de efecto grande — envolver los lectores, no los escritores:

```python
# database.py
@st.cache_data(ttl="60s", max_entries=32)
def load_inventory_dataframe() -> pd.DataFrame:
    ...
```

Y tras cada escritura, invalidar solo lo afectado con `load_inventory_dataframe.clear()` en lugar del
`st.cache_data.clear()` global que hay hoy en [app.py:364](app.py#L364) — que además borra las tasas
de cambio recién consultadas.

Ojo con un detalle: `database.py` hoy importa `streamlit` de forma perezosa y defensiva dentro de
`get_database_url` ([database.py:203](database.py#L203)) para poder usarse fuera de Streamlit. Si se
decoran los loaders, ese aislamiento se pierde y `tests/test_database.py` deja de correr sin runtime.
La salida limpia es dejar `database.py` puro y poner la capa de caché en un módulo intermedio
(`utils/data.py`) que sí dependa de Streamlit. Así los tests siguen funcionando.

### 3.2 Las 7 pestañas se calculan siempre, incluso las ocultas

[app.py:793](app.py#L793) crea 7 pestañas y las llena todas en cada rerun. La guía del proyecto lo
prohíbe explícitamente ("Do not put expensive work unguarded inside tabs or expanders") y da el patrón:

```python
tabs = st.tabs([...], on_change="rerun")
if tabs[0].open:
    with tabs[0]:
        ...
```

Hoy, abrir la app para registrar una venta también calcula el dashboard completo, las comisiones, la
rentabilidad semanal, los márgenes por producto y las cuentas por pagar. Lo mismo con las sub-pestañas
anidadas de [app.py:1077](app.py#L1077).

### 3.3 Un PDF por cada pago, en cada rerun

[app.py:530](app.py#L530): `generar_recibo_pdf` se llama **dentro del bucle sobre todos los pagos**, y
dentro de un `st.expander` cerrado. El contenido de un expander cerrado se computa igual. Con 200 pagos
son 200 PDFs generados en cada interacción, para que el usuario descargue como máximo uno.

Arreglo: generar el PDF solo al desplegar (`expander.open`) o detrás de un botón.

---

## 4. Estructura y navegación

### 4.1 Un patrón frágil que va a romperse

```python
# app.py:784-806
else:
    (productos_tab, ventas_tab, ...) = st.tabs([...])   # solo se crean en el else

if selected_section != "Sistema Marfil":
    st.stop()                                          # lo único que evita el NameError

with productos_tab:                                    # si st.stop() se mueve, explota
```

Las 7 variables de pestaña **solo existen** en una rama del `if/elif`. Lo único que impide un
`NameError` es que `st.stop()` esté exactamente ahí. Cualquier reordenamiento rompe la app en
producción y el error que verá el dueño será `NameError: productos_tab`.

### 4.2 Navegación a mano en vez de `st.navigation`

La sección se elige con un `st.radio` en el sidebar ([app.py:403](app.py#L403)) y se despacha con una
cadena `if/elif/else` de ~370 líneas. La guía del proyecto pide `st.navigation` + `st.Page` con carpeta
`app_pages/`. Eso elimina de un golpe el problema 4.1, el `st.stop()` y el despacho manual.

### 4.3 1.696 líneas en un archivo

La guía marca el umbral en ~1.000 líneas. La estructura que propone:

```
streamlit_app.py          # st.navigation + sidebar
app_pages/
  productos.py            # Productos & Stock
  ventas.py               # Registrar venta
  cuotas.py               # Cuotas y abonos
  compras.py              # Compras & proveedores
  socios.py
  finanzas.py
  dashboard.py
  cobranza.py             # Cobranza & WhatsApp
  recibos.py
  importar.py             # Carga masiva CSV
utils/
  data.py                 # loaders con caché sobre database.py
  csv_import.py           # normalize_column_name, COLUMN_FIELD_MAP, parsers
  whatsapp.py             # build_whatsapp_message / _url
database.py               # sin cambios, puro SQLAlchemy
```

El beneficio inmediato no es estético: **hoy las funciones puras no se pueden testear**.
`parse_numeric_value`, `normalize_column_name`, `COLUMN_FIELD_MAP` y `build_whatsapp_message` viven en
el archivo de UI, así que importarlas ejecuta `st.set_page_config` y toda la app. Por eso los 12 tests
existentes cubren `database.py` y `services/` y **ninguno toca `app.py`** — no por descuido, sino
porque no se puede. Moverlas a `utils/` las vuelve testeables sin tocar nada más.

---

## 5. Detalles de la guía de Streamlit del proyecto

| # | Punto | Dónde | Qué pide la guía |
|---|---|---|---|
| 1 | `render_metric_card(_accent=...)` recibe un color que **nunca usa**; 30+ llamadas lo pasan | [app.py:59](app.py#L59) | La función solo envuelve `st.metric`: borrarla y llamar `st.metric` directo |
| 2 | `st.radio` para elegir modo | [app.py:375](app.py#L375), [454](app.py#L454) | `st.segmented_control` |
| 3 | Emojis en títulos, pestañas y botones | todo el archivo | Material Symbols (`:material/inventory:`) |
| 4 | Title casing (`"Registrar Venta"`, `"Guardar Cambios de Inventario"`) | todo | Sentence casing (`"Registrar venta"`) |
| 5 | No hay `.streamlit/config.toml` | — | Tema por config, antes que estilos manuales |
| 6 | `st.session_state` **nunca se usa** | — | Inicializar en un solo lugar; hoy todo el estado vive en widgets |
| 7 | 44 `except Exception` que muestran `str(exc)` crudo | todo | El dueño del negocio no debe leer trazas de SQLAlchemy |
| 8 | `f"...  \\"` para saltos de línea en markdown | [app.py:486](app.py#L486), [522](app.py#L522) | Frágil; usar líneas separadas o `st.metric` |

**Lo que ya está bien** y conviene no romper: no hay `use_container_width` (ya migrado a `width=`), no
hay CSS inyectado, `st.secrets` se usa correctamente y `secrets.toml` está en `.gitignore`, el engine
está cacheado con `lru_cache`, y `register_sale` descuenta stock de forma atómica con un `UPDATE ...
WHERE stock >= cantidad` en lugar de leer-y-escribir. Eso último es buen trabajo.

---

## 6. Un riesgo que no es de refactor pero hay que arreglar ya

[app.py:70-73](app.py#L70) — el mensaje de cobranza por WhatsApp lleva **datos de pago de relleno**:

```
- C.I.: V-XX.XXX.XXX
- Teléfono: 04XX-XXX-XXXX
```

Tal como está, cada recordatorio que se envíe a un cliente incluye esos marcadores literales. Debería
salir de configuración (`st.secrets` o una tabla de parámetros), y no debería poder enviarse un
recordatorio si los datos no están cargados.

---

## 7. Plan por fases

Ordenado por relación valor/riesgo. Las fases 1 y 2 no cambian estructura, así que se pueden aplicar y
verificar sin tocar la organización del archivo.

| Fase | Qué | Por qué primero | Tamaño |
|---|---|---|---|
| **1** | Datos de pago del WhatsApp a configuración | Se está enviando a clientes | S |
| **1** | Arreglar `normalize_column_name` + limpiar el mapa + alias del libro v2 | Desbloquea la migración del Excel | S |
| **1** | Importación tolerante: `stock=0`, fecha por defecto, estatus derivado, avisos | Sin esto no se puede dejar el Excel | M |
| **2** | `utils/data.py` con loaders cacheados + invalidación selectiva | Mayor ganancia de velocidad por línea escrita | M |
| **2** | Guardas `on_change="rerun"` + `tab.open` en las 4 llamadas a `st.tabs` | Deja de calcular 7 pestañas por click | S |
| **2** | PDF solo al desplegar el expander | O(n) PDFs por rerun → 0 | S |
| **3** | Piso de ganancia sobre costo (+70 % / +120 %) en el registro de venta | Recomendación 2 del informe | S |
| **3** | `Enum` de estatus compartido + tercer estado | Recomendación 1 del informe | S |
| **3** | Unicidad de producto por nombre normalizado + dejar de duplicar el texto | Recomendación 4 del informe | M |
| **4** | Migrar a `st.navigation` + `app_pages/` | Elimina el patrón frágil de 4.1 | L |
| **4** | Extraer funciones puras a `utils/` + tests | Hace testeable lo que hoy no lo es | M |
| **5** | Material Symbols, sentence casing, `config.toml`, `segmented_control` | Cosmético, sin riesgo funcional | M |

### Cómo verificar cada fase

- **Fase 1:** exportar cada hoja del libro v2 a CSV e importarla; hoy las tres fallan, después deben
  entrar las tres con sus avisos. Es una prueba objetiva y reproducible.
- **Fase 2:** contar consultas por rerun. `load_inventory_dataframe` debe pasar de 3 a 1.
- **Fase 3:** test que confirme que una venta con precio < costo exige confirmación, y otro que avise
  cuando una venta marcada BCV se cobra al nivel de divisa.
- **Fase 4:** `tests/` debe poder importar `utils/csv_import.py` sin levantar Streamlit.

---

## 8. Lo que no recomiendo hacer

- **No reescribir `database.py`.** Tiene 1.792 líneas pero está bien: transacciones atómicas,
  validaciones, y 10 tests que lo cubren. El problema no es su código, es que nadie cachea sus lecturas.
- **No añadir CSS.** La guía del proyecto lo desaconseja y hoy el archivo está limpio de eso.
- **No migrar a `st.navigation` antes de la fase 2.** Reordenar 1.700 líneas y cambiar el modelo de
  caché a la vez hace imposible saber qué rompió qué.
- **No intentar que la app importe el libro sin cambios.** El libro no tiene stock ni fechas de venta;
  eso se resuelve cargando lo que hay y completando en la app, no forzando el formato.
