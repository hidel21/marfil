# Auditoría — SISTEMA MARFIL

**Archivo auditado:** `excel/SISTEMA MARFIL  (2).xlsx` (195.656 bytes, sin modificar)
**Entregable:** `excel/SISTEMA_MARFIL_v2.xlsx`
**Fecha:** 17/08/2026

El original quedó intacto. Todo el trabajo se hizo sobre una reconstrucción. **No se alteró ni se inventó
ninguna cifra de negocio**: solo estructura, tipos de dato, formato y fórmulas. Las cifras que cambian de
valor lo hacen porque una fórmula rota antes las excluía — cada caso está justificado abajo.

---

## 1. Auditoría

### Resumen de gravedad

| # | Problema | Hoja | Impacto |
|---|---|---|---|
| 1 | Fórmulas apuntan a una hoja que no existe | VENTAS | 🔴 15 celdas en `#N/A`, "Total por Cobrar" inservible |
| 2 | 21 montos guardados como texto | CONTROL | 🔴 Bs 122.697,97 invisibles para el total |
| 3 | 66 precios escritos a mano en columnas calculadas | PRECIOS PERF ORIGINALES | 🔴 se desincronizan al cambiar un precio |
| 4 | La ganancia (+70 % / +120 % sobre costo) incrustada en 527 fórmulas como 1,7 y 2,2 | PRECIOS PERF TOP QUALITY | 🟠 cambiar la ganancia = editar 527 celdas |
| 5 | Hoja sin estructura tabular (texto libre) | GASTOS Y COMPRAS | 🟠 los gastos no son sumables |
| 6 | Rangos fijos en todos los totales | CONTROL, VENTAS | 🟠 las filas nuevas no entran en los totales |
| 7 | Fórmulas aplicadas solo a parte de las filas | VENTAS | 🟠 23 de 42 filas sin ganancia calculada |
| 8 | Encabezados duplicados | CONTROL | 🟡 `FECHA`×4, `MONTO Bs`×3, `REFERENCIA`×3 |
| 9 | Formatos de fecha y moneda mezclados | todas | 🟡 ilegible / no comparable |
| 10 | Filas y columnas fantasma declaradas | todas | 🟡 3.000+ filas vacías en el rango usado |

### Detalle por hoja

#### CONTROL — *declaraba `A1:O1038`, con datos solo hasta la fila 39*

- **Números guardados como texto (21 celdas).** `I6='15.679,22'`, `L7='8.307,00'`, `L9='5.910,00'`,
  `I12`, `I15`, `F18='18.183,00'`, `F21`, `I21`, `F23`, `F24`, `F25`, `I25`, `F35`, `F38`. Excel los ignora
  en `SUM`. El total `B64` mostraba **Bs 229.848,76** cuando la suma real de lo registrado es
  **Bs 352.546,73**: había **Bs 122.697,97 fuera del total**.
- **Rango fijo en el total.** `B64 = SUM(F4:F72, I4:I72, L4:L72)` — el `72` no corresponde a nada
  (los datos llegan a la 39) y a la vez limita el crecimiento.
- **`B67 = COUNTIF(O4:O18,"YA PAGO")`** solo mira hasta la fila 18 de las 39 con datos. Hoy devuelve 10,
  que es correcto por casualidad (no hay estatus más abajo de la fila 18); cualquier venta nueva quedaba
  sin contar.
- **`B65 = 306` escrito a mano** con la etiqueta "Total Divisas Pagadas ($)". No hay ninguna columna de
  abonos en dólares en la hoja, así que no es derivable.
- **`C64 = 260` y `D64 = 100`**: dos números sueltos dentro de la fila de totales, bajo los encabezados
  `VENDEDOR` y `PRODUCTO`, sin etiqueta ni fórmula.
- **Encabezados duplicados**: `FECHA` en A/G/J/M, `MONTO Bs` en F/I/L, `REFERENCIA` en H/K/N. Impide
  convertir la hoja en tabla y hace ambigua cualquier fórmula.
- **Formatos de fecha mezclados en la misma columna**: `d/m/yy`, `dd/mm/yyyy`, `dd-mm-yy`, `d/m/yyyy`.
- **Texto en columnas tipadas**: `M10='listo'` y `M11='listo'` en una columna de fecha;
  `F19='12 EFECTIVO'` y `F20='16 EFECTIVO'` en una columna de monto en Bs (son dólares en efectivo, no Bs);
  `E19='12 MY'`, `E20='16 MY'`, `E28='18 GM'`, `E29='12 GM'`, `E38='19 usdt P.M'` en la columna de precio.
- **Fila 19 desplazada**: `D19=360` (un producto numérico) y el precio y el pago corridos de columna.
- Sin paneles congelados, sin autofiltro, sin validación en `ESTATUS`.

#### GASTOS Y COMPRAS — *declaraba `A1:Z1000`; 89 líneas de texto libre en la columna A, 25 columnas vacías*

- **No es una hoja de cálculo, es una libreta.** Cada línea es una cadena como `'SCANDAL  9.10$'` o
  `'TOTAL 99$ BINANCE'`. Ningún monto es sumable, ninguna fecha es una fecha (salvo 5 celdas), no hay
  forma de cruzar un gasto con una venta.
- **Subtotales calculados a mano dentro del texto.** Al extraerlos y compararlos aparecen dos que no
  cuadran:

  | Lote | Suma de ítems | Subtotal declarado | Diferencia |
  |---|---|---|---|
  | 19/06/2026 | $99,00 | $99,00 | — |
  | **26/06/2026** | **$235,50** | **$236,00** | **+$0,50** |
  | 01/07/2026 | $30,00 | $30,00 | — |
  | 08/08/2026 | $176,00 | $176,00 | — |
  | 10/08/2026 | $109,00 | $109,00 | — |
  | 12/06/2026 | $15,00 | $15,00 | — |
  | **PEDIDO CARACAS LUKA STORE** | **$57,15** | **$59,00** | **+$1,85** |
  | 12/08/2026 | $50,00 | (sin subtotal) | — |

- **Fecha fuera de secuencia**: el bloque `12/06/2026` está escrito entre los de 10/08 y 12/08. Con casi
  seguridad es 12/08/2026 mal tecleado, pero no lo cambié (ver §5).
- **Nombres con dígitos**: al extraer la descripción hay que quitar *solo* el monto pegado al `$`, no
  cualquier número, o productos como `9PM REBEL ORIGINAL`, `212 VIP`, `360` y `LE LABO SANTAL 33` pierden
  parte del nombre.
- **Posible gasto duplicado**: `DECANST 1$` en el lote del 10/08 y
  `GASTO MUESTRA DE CLIENTE DECANST 1 $ COMPRADO EL 10/08/2026` en el del 12/08 parecen el mismo decant.

#### VENTAS — *declaraba `A1:AA997`, con datos hasta la fila 46 y 13 columnas de 27*

- 🔴 **Las 14 fórmulas de `Deuda ($)` apuntan a `'REGISTRO DE CUOTAS '!F:F` — esa hoja no existe en el
  archivo.** Resultado: `J5:J18` en `#N/A`, y el `#N/A` se propaga a `M8 'Total por Cobrar'`. Es el fallo
  más grave del libro: la cobranza no se puede leer.
- **Fórmulas aplicadas a medias**: `Ganancia` existe en las filas 5–19 y `Deuda` en las 5–18, de 42 filas
  con datos. Las 23–24 filas restantes están simplemente vacías, sin que nada lo indique.
- **Rangos fijos** en las cuatro métricas: `SUM(F5:F997)`, `SUM(G5:G997)`, `SUM(H5:H997)`, `SUM(J5:J997)`.
- **Bloque de métricas incrustado en la zona de datos** (`L4:M8`), dentro del autofiltro `C4:J46`: al
  filtrar o ordenar la tabla, las métricas se mueven con ella.
- **Columna A vacía** (con ancho asignado, engañando sobre su uso) y **columna K vacía** como separador.
- **Precios como texto**: `F29='18.GM'`, `F30='12.GM'`, `F39='19 usdt P.M'`, `F41='16 P.M'`.
- **Hipervínculos basura**: `F29` y `F30` tenían enlaces automáticos a `http://18.gm/` y `http://12.gm/`
  — Excel interpretó `18.GM` como un dominio.
- **`C20 = 360` numérico** en la columna de producto (el perfume "360").
- **Columna `B` (contador) inconsistente**: llega a 24 para 42 filas, con huecos en 14, 15, 17, 21–24, 27,
  29, 30, 32, 34, 37, 39–41, 43 y 46. En algunos casos el hueco parece marcar "segundo producto de la misma
  operación" (filas 21–24 bajo la 20), pero en otros no (filas 14, 15 y 17 son clientes distintos).
- **Rejilla desactivada** (`showGridLines=False`) sin bordes que la sustituyan.
- Sin referencias circulares y sin vínculos externos: eso está bien.

#### PRECIOS PERF ORIGINALES — *la hoja mejor construida, y aun así*

- 🔴 **66 valores escritos a mano donde debía haber fórmula.** Los encabezados dicen
  `Para el team (-25%)` y `Revendedores (-15%)`, y las 33 filas cuadran **exactamente** con
  `Precio × 0,75` y `Precio × 0,85` (lo verifiqué celda por celda, sin una sola excepción). Es decir: hoy
  funciona, pero al cambiar un precio original las otras dos columnas quedan mintiendo en silencio.
- **Validación de datos absurda** en `B2:D34`: una regla `custom` con
  `AND(ISNUMBER(B2),NOT(OR(NOT(ISERROR(DATEVALUE(B2))),...)))` que intenta rechazar fechas en columnas de
  precio. Es un resto de otro trabajo y no aporta nada.
- **Precios sin formato de moneda** (`General`): se leen como números pelados.

#### PRECIOS PERF TOP QUALITY — *declaraba `A1:Z998`, con datos hasta la 274 y 4 columnas de 26*

- 🟠 **527 fórmulas con la ganancia incrustada**: `=B4 * 1.7` (259 celdas) y `=B4 * 2.2` (268). Los
  factores 1,7 y 2,2 son la política de precios del negocio expresada como multiplicador:
  **+70 % de ganancia sobre el costo** si el cliente paga en divisa o USDT, y **+120 %** si paga a tasa
  BCV. Escrito como multiplicador, el número no dice cuál es la ganancia, y ajustarla significa
  reescribir 527 celdas a mano.
- 🔴 **237 de las 271 filas no tienen costo**, así que las fórmulas devuelven **$0,00**. La lista de precios
  muestra 237 productos "a cero" como si fuera un precio real.
- **55 filas fantasma** (220–274 y 108) con fórmulas pero sin producto ni costo, produciendo $0,00.
- **Filas-etiqueta mezcladas con los datos**: `A23='LINEA ARABE'` y `A109=' LINEA CLÁSICA  O DISENADOR'`
  son títulos de sección, pero ocupan una fila de producto y arrastran fórmulas.
- **10 nombres repetidos** en el catálogo (ver §5).
- **Formato de moneda incorrecto**: `D` usa `"Bs "#,##0.00` pero el valor es en dólares
  (`Cloud`: costo $12 → `D=26,40`, y en VENTAS ese Cloud se vende a $30). Como Bs no tendría sentido.
- **`A8 = 360` numérico** en la columna de producto.
- **Encabezados en la fila 3** bajo un título fusionado `A1:D2`: ninguna herramienta reconoce la tabla.

#### Transversal

- **No hay referencias circulares** en ninguna hoja.
- **No hay vínculos externos** ni `calcChain` (el libro viene de una exportación de Google Sheets).
- Los 5 `drawing*.xml` del paquete están **vacíos** (0 anclas, 0 imágenes, 0 gráficos): no se pierde nada
  al reconstruir el archivo.
- Dos nombres de hoja con **espacio final**: `'GASTOS Y COMPRAS '` y `'PRECIOS PERF TOP QUALITY '`. Es la
  clase de detalle que rompe fórmulas y scripts silenciosamente.

---

## 2. Limpieza de datos aplicada

- **Filas y columnas fantasma eliminadas**: CONTROL 999 filas, GASTOS 911 filas + 25 columnas,
  VENTAS 951 filas + 14 columnas, TOP QUALITY 724 filas + 22 columnas.
- **21 montos de CONTROL convertidos de texto a número** (`'15.679,22'` → `15679,22`). Es el arreglo con
  más efecto de toda la auditoría.
- **Textos que no eran montos ni fechas movidos a una columna `NOTAS`** en lugar de borrarlos:
  `'12 EFECTIVO'`, `'16 EFECTIVO'`, `'listo'`, `'18 GM'`, `'19 usdt P.M'`… La celda tipada queda vacía y la
  anotación original se conserva legible.
- **Precios mixtos separados en número + nota**: `'18.GM'` → precio `18` + nota `GM`. El número entra en los
  totales; la anotación no se pierde.
- **Encabezados estandarizados**: `MAYÚSCULAS`, con la unidad explícita y sin duplicados.
  `FECHA`×4 → `FECHA VENTA` / `FECHA P1` / `FECHA P2` / `FECHA P3`, y lo mismo con `MONTO Bs` y `REFERENCIA`.
- **Nombres de hoja sin espacios finales.**
- **Hipervínculos automáticos eliminados** (`http://18.gm/`, `http://12.gm/`).
- **Nombres de vendedor y cliente normalizados solo en capitalización y espacios** (`'gregory '` →
  `'Gregory'`). No se fusionó ningún nombre distinto (ver §5).
- **Productos numéricos convertidos a texto**: `360` → `"360"`, para que no se ordene como número.
- **Fechas unificadas a `dd/mm/yyyy`** en las cuatro hojas que las usan.
- **1 fila duplicada eliminada**: `LACOSTE ROUGE` aparecía dos veces seguidas en TOP QUALITY (filas 170 y
  173), ambas sin costo. Se eliminó una. Los otros 9 nombres repetidos **no** se tocaron (§5).
- **55 filas fantasma con solo fórmulas eliminadas** en TOP QUALITY.

---

## 3. Refactor de fórmulas

El changelog completo (40 entradas) está también **dentro del libro, en la hoja `CHANGELOG`**.

### Lo estructural

| Antes | Después |
|---|---|
| Rangos fijos `SUM(F5:F997)` | Referencias de columna completa `SUM(E:E)` — crecen solas |
| Constantes `1.7` / `2.2` / `0.75` / `0.85` en 593 celdas | 4 nombres definidos en una hoja `PARÁMETROS` |
| 5 hojas sin tabla | 6 tablas de Excel con nombre (`Control`, `Ventas`, `Gastos`, `PreciosOriginales`, `PreciosTopQuality`, `Changelog`) |
| Métricas mezcladas con los datos | Bloques `RESUMEN` fuera de cada tabla |

### Cambio por cambio

| Hoja | Antes | Después | Por qué |
|---|---|---|---|
| VENTAS | `J5 = ...SUMIFS('REGISTRO DE CUOTAS '!F:F...)` → `#N/A` | Se creó la hoja **`REGISTRO DE CUOTAS`** con la estructura exacta que la fórmula pedía (D=Cliente, E=Producto, F=Monto) | La fórmula estaba bien; faltaba la hoja |
| VENTAS | `M8 = SUM(J5:J997)` → `#N/A` | `=SUM(K:K)` sobre una columna que ya calcula | Se acabó la propagación del error |
| VENTAS | `Ganancia` solo en filas 5–19 | `=IF(COUNT(E:F)<2,"",E-F)` en las 42 filas | La guarda `IF` evita mostrar `$0,00` donde falta un dato |
| VENTAS | `Deuda` solo en filas 5–18 | Nueva columna `ABONADO ($)` explícita + `DEUDA = PRECIO − ABONADO` | La deuda pasa a ser auditable en vez de una caja negra |
| VENTAS | — | Nueva columna `MARGEN` = `GANANCIA / PRECIO` | Cálculo que se hacía mentalmente |
| CONTROL | `B64 = SUM(F4:F72,I4:I72,L4:L72)` | Columna `TOTAL ABONADO Bs` por fila + `=SUM(P:P)` | Se ve el abono de cada operación, no solo el gran total |
| CONTROL | `B67 = COUNTIF(O4:O18,"YA PAGO")` | `=COUNTIF(O:O,"YA PAGO")` | Ignoraba 21 de 39 filas |
| CONTROL | Totales en `A64:B69`, pegados a los datos | Bloque `RESUMEN` en `S3`, con 10 indicadores | Insertar una venta ya no rompe el total |
| GASTOS | Subtotales escritos dentro del texto | Bloque `CONTROL POR LOTE` con `SUMIFS`, que compara declarado vs. real y **marca la diferencia en rojo** | Ahí aparecieron las dos descuadres de $0,50 y $1,85 |
| PRECIOS ORIGINALES | 66 precios a mano | `=IF(B4="","",ROUND(B4*(1-DESC_TEAM),2))` | Verifiqué que las 33 filas cuadran exactamente antes de convertir |
| TOP QUALITY | `=B4 * 1.7` ×527 | `=IF($C4="","",ROUND($C4*(1+GANANCIA_DIVISA),2))` | Cambiar la ganancia = editar **una** celda |
| TOP QUALITY | 237 filas mostrando `$0,00` | Blanco + resaltado amarillo | Un precio en blanco se ve; un `$0,00` se cobra |

### Valores que cambian (y por qué)

| Indicador | Antes | Después | Motivo |
|---|---|---|---|
| CONTROL · Total en Bs | Bs 229.848,76 | **Bs 352.546,73** | 21 montos guardados como texto que `SUM` no veía |
| VENTAS · Total por Cobrar | `#N/A` | calcula | La hoja de cuotas ya existe |
| VENTAS · Ganancia Total | $194,50 (solo 15 filas) | cubre las 42 filas | La fórmula faltaba en 23 filas |
| CONTROL · Operaciones YA PAGO | 10 | 10 | Sin cambio hoy; el rango fijo era una bomba de tiempo |

Ningún otro número cambia. Lo verifiqué comparando celda por celda contra el original: precios, costos,
montos en Bs, fechas, referencias, nombres de cliente, producto y vendedor, y las 77 líneas de GASTOS
(conservadas literalmente en la columna `TEXTO ORIGINAL`).

---

## 4. Ajuste visual

- **Encabezados** teal oscuro (`#1F4E5F`), blanco en negrita, centrados, con alto fijo y texto ajustado.
- **Color por tipo de celda**, consistente en todo el libro:
  · blanco = captura manual · gris azulado = calculada por fórmula · amarillo = parámetro editable
  · rojo claro = requiere atención.
- **Bordes finos** en toda la zona de datos (la rejilla está desactivada, como en el original, pero ahora
  la estructura se ve).
- **Paneles congelados** en las 7 hojas de datos, cada uno en la columna que conviene
  (CONTROL en `E4`, para no perder de vista fecha/cliente/vendedor/producto al recorrer los 3 pagos).
- **Tablas de Excel** con filas alternadas y autofiltro en todas las hojas de datos.
- **Ancho de columna calculado** a partir del contenido real, con techo para que las notas largas no
  desborden la pantalla.
- **Semáforos (formato condicional)**:
  · CONTROL: verde `YA PAGO`, rojo `PENDIENTE*`, ámbar la fila sin ningún abono
  · VENTAS: rojo la ganancia negativa, ámbar la deuda pendiente
  · GASTOS: rojo la diferencia entre subtotal declarado y real
  · TOP QUALITY: amarillo el producto sin costo, rojo el nombre repetido
- **Validación por lista** en `ESTATUS` (CONTROL) y `MÉTODO` (REGISTRO DE CUOTAS): se elige, no se teclea.
- **Colores de pestaña** por función: operación, catálogo, configuración, documentación.

### Hojas del libro v2

| Hoja | Filas | Novedad |
|---|---|---|
| `PARÁMETROS` | 4 | **Nueva.** Las 4 constantes del sistema, en un solo lugar |
| `CONTROL` | 36 | Tabla `Control`, 17 columnas sin nombres duplicados, `RESUMEN` con 10 indicadores |
| `VENTAS` | 42 | Tabla `Ventas`, `MARGEN` y `ABONADO ($)` nuevas, `RESUMEN` con 8 indicadores |
| `REGISTRO DE CUOTAS` | 0 | **Nueva.** La hoja que las fórmulas buscaban. Vacía a propósito |
| `GASTOS Y COMPRAS` | 77 | De texto libre a tabla de 8 columnas + control de subtotales por lote |
| `PRECIOS PERF ORIGINALES` | 33 | Descuentos por fórmula contra `PARÁMETROS` |
| `PRECIOS PERF TOP QUALITY` | 212 | Columna `LÍNEA`, precios en blanco cuando no hay costo |
| `CHANGELOG` | 40 | **Nueva.** Los 40 cambios, dentro del propio libro |

---

## 5. Supuestos y decisiones

### Supuestos que tomé

1. **`'15.679,22'` es Bs 15.679,22** — punto de miles, coma decimal (convención venezolana). Consistente en
   las 14 celdas afectadas.
2. **En `PRECIOS PERF ORIGINALES`, `-25%` y `-15%` son multiplicaciones por 0,75 y 0,85.** No lo asumí: lo
   comprobé en las 33 filas, sin una sola excepción, antes de reemplazar los valores por fórmulas.
3. **Los factores 1,7 y 2,2 son ganancia sobre el COSTO (+70 % y +120 %), no margen sobre la venta.**
   Confirmado por el dueño del negocio. El precio resultante es idéntico (`costo × 1,70` y
   `costo × 2,20`); lo que cambió en v2 es que el parámetro editable ahora se llama `GANANCIA_DIVISA`
   = 70 % y `GANANCIA_BCV` = 120 %, y la fórmula es `costo × (1 + ganancia)`. Medido sobre el precio de
   venta esos mismos precios equivalen a 41,2 % y 54,5 %, pero no es la forma en que el negocio los
   define.
4. **La columna `Precio tasa BCV` de TOP QUALITY está en dólares, no en bolívares.** El formato decía `Bs`,
   pero `Cloud` costo $12 → $26,40, y ese mismo Cloud se vende a $30 en VENTAS. Como Bs sería absurdo.
   **Cambié solo el formato, no el valor.**
5. **`'12 MY'`, `'18 GM'`, `'19 usdt P.M'` son monto + medio de pago.** Separé el número (que suma) de la
   anotación (que va a `NOTAS`). Si `MY`/`GM` significan otra cosa, avisá.
6. **`'12 EFECTIVO'` en la columna de Bs son dólares en efectivo, no bolívares.** Dejé la celda de Bs vacía
   y la anotación en `NOTAS`: meter 12 en una columna de bolívares habría contaminado el total.
7. **En GASTOS, `13.000` y `2.932,00` son bolívares, y `14.92` y `3.34` su equivalente en dólares.** Es la
   lectura natural de `'GASTO ENVIO PEDIDO DE CARACAS 13.000 14.92 BINANCE'`.
8. **Las 3 líneas que el texto rotula `GASTO ...` son gastos operativos, no compra de producto.** Las tipifiqué
   como `GASTO` para que no distorsionen la comparación de subtotales por lote.
9. **`'LINEA ARABE'` y `' LINEA CLÁSICA O DISENADOR'` son títulos de sección**, no productos. Pasaron a la
   columna `LÍNEA`. Los 19 productos que están antes del primer título quedaron como `SIN LÍNEA` — no les
   inventé una categoría.
10. **La hoja `REGISTRO DE CUOTAS` se entrega vacía.** Las fórmulas de VENTAS ya la esperaban; podría haberla
   rellenado con los pagos de CONTROL, pero **esos están en bolívares y VENTAS trabaja en dólares**, y no hay
   tasa de cambio en el libro. Inventar la conversión habría sido inventar cifras. Mientras esté vacía, la
   columna `ABONADO ($)` muestra `$0,00` y la `DEUDA` muestra el precio completo — con una nota en rojo al
   lado del `RESUMEN` para que nadie lo lea como cobranza real.

### Lo que NO toqué, a propósito

Son cifras o criterios de negocio. Los dejo señalados para tu decisión:

1. **8 fechas casi seguramente mal tecleadas.** Las filas 26–33 de CONTROL dicen **08/02/2026**, encajonadas
   entre filas del 02/08/2026 y del 10/08/2026. Es un clásico cambio de `dd/mm` por `mm/dd`: deberían ser
   **02/08/2026**. Igual el lote `12/06/2026` de GASTOS, entre los del 10/08 y 12/08. **No las cambié**:
   corregir fechas es corregir datos. Se arregla en un minuto si confirmás.
2. **2 ventas con precio por debajo del costo**:
   · fila 15, `212Vip` / Anderson — precio **$9,50** vs costo **$22,00**
   · fila 16, `Club de Nuit` / Polanco — precio **$30,00** vs costo **$51,00**
   El patrón sugiere valores invertidos (en CONTROL, ese 212 Vip figura a $22). Quedan **en rojo** en la hoja.
3. **`'Gregor'` y `'Gregory'` conviven** (10 y 29 registros en VENTAS; 7 y 26 en CONTROL). No los fusioné:
   podrían ser dos personas. Si es la misma, es un `Buscar y reemplazar`.
4. **21 productos escritos de varias formas.** `'212 Vip'` / `'212 vip'` / `'212Vip'`,
   `'La Bomba'` / `'la bomba'` / `'LA BOMBA'`, `'AQUA DI GIO'` / `'ACQUA DI GIO'` / `'AGUA DI DIO'`,
   `'Very Good Grul'` (VENTAS) vs `'Very Good Girl'` (CONTROL), `'Khamarah Qahwa'` vs `'Khamrah Qahwa'`…
   Solo normalicé espacios. **Esto importa**: la búsqueda de abonos en `REGISTRO DE CUOTAS` cruza por nombre
   exacto de producto y cliente, así que conviene unificar el catálogo antes de cargar cuotas.
5. **9 nombres repetidos en TOP QUALITY**, cada par con el costo en una fila y vacío en la otra:
   `CLOUD` (filas 4 y 113), `ULTRAMALE` (6, 111), `SWISS ARMY` (7, 186), `BAD BOY` (10, 160),
   `INVICTUS` (12, 200), `EROS MEN` (14, 175), `BHARARA KING` (17, 65), `ASAD BOURBON` (21, 30),
   `LA BOMBA` (22, 124). Fusionarlos exige decidir a qué línea pertenece cada uno. Quedan **en rojo**.
6. **`B65 = 306`, "Total Divisas Pagadas ($)"**, sigue siendo captura manual: no hay columna de abonos en
   dólares de la que derivarlo. Marcado en amarillo como celda de entrada.
7. **`C64 = 260` y `D64 = 100`**, los números sin etiqueta. Conservados en un bloque "para revisar" junto al
   `RESUMEN` de CONTROL, en vez de borrarlos.
8. **CONTROL tiene 36 operaciones y VENTAS 42 líneas.** No intenté reconciliarlas: sin una clave común
   (`CONTROL` no tiene número de operación) cualquier emparejamiento sería adivinado. Es la mejora
   estructural más valiosa que queda por hacer.
9. **La columna `N° OPERACIÓN` de VENTAS quedó tal cual**, con sus huecos. No la renumeré porque los huecos
   podrían significar "segundo producto de la misma operación" (filas 21–24) — aunque en las filas 14, 15 y
   17 esa lectura no se sostiene. Necesita tu criterio.
10. **Posible gasto duplicado**: el decant de $1 aparece el 10/08 y otra vez el 12/08 como
    "muestra de cliente comprado el 10/08/2026".

---

## 6. Cómo trabajar con el archivo nuevo

1. **Para cambiar tasas o descuentos**, editá solo las celdas amarillas de `PARÁMETROS`. Las dos listas de
   precios se recalculan completas.
2. **Para agregar una venta**, escribí en la primera fila libre de la tabla `Ventas`: ganancia, margen,
   abonado y deuda se calculan solos, y el `RESUMEN` se actualiza. Lo mismo en `Control` y `Gastos`.
3. **Para que la cobranza funcione**, cargá los abonos en `REGISTRO DE CUOTAS`. El `CLIENTE` y el `PRODUCTO`
   deben coincidir **exactamente** con los de `VENTAS` — de ahí la importancia del punto 4 de §5.
4. **Lo que esté en rojo o amarillo pide atención**, no es decoración: subtotal descuadrado, ganancia
   negativa, producto sin costo, nombre repetido.

### Nota sobre `migrate_excel.py`

El script del proyecto lee las hojas por nombre y aplica `.strip()`, así que sigue encontrando
`PRECIOS PERF TOP QUALITY`, `CONTROL` y `VENTAS`. Pero **lee por posición de columna**, y en v2 las columnas
se movieron (VENTAS ya no tiene la columna A vacía, CONTROL tiene `TOTAL ABONADO Bs` y `NOTAS` nuevas). Si
vas a migrar desde v2, hay que ajustar el mapeo. Contra el original sigue funcionando igual.
