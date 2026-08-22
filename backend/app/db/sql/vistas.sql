-- Las vistas de lectura. Son la capa que reemplaza a las ~30 funciones
-- `load_*_dataframe` de database.py, que existian solo para alimentar st.dataframe.
--
-- Estan en SQL y no en Python por dos razones: el drill-down de la pantalla de
-- auditoria necesita que cada numero agregado se pueda abrir en las filas que lo
-- produjeron, y eso se hace con la misma vista; y agrupar por producto_id en vez de
-- por el texto del nombre es justamente lo que arregla los reportes.

-- =========================================================== precios de politica
-- Reemplaza las cuatro columnas de precio calculado que se borraron de `productos`.
-- Guardarlas era el mismo defecto de "66 valores a mano en columnas calculadas" que
-- encontro la auditoria, reproducido en SQL.
CREATE OR REPLACE VIEW v_precio_vigente AS
WITH parametros AS (
    SELECT
        max(valor) FILTER (WHERE clave = 'GANANCIA_DIVISA')  AS ganancia_divisa,
        max(valor) FILTER (WHERE clave = 'GANANCIA_BCV')     AS ganancia_bcv,
        max(valor) FILTER (WHERE clave = 'DESC_TEAM')        AS desc_team,
        max(valor) FILTER (WHERE clave = 'DESC_REVENDEDOR')  AS desc_revendedor
    FROM parametros_precio
    WHERE vigencia @> CURRENT_DATE
)
SELECT
    p.id                     AS producto_id,
    p.nombre,
    p.nombre_normalizado,
    p.es_original,
    p.modelo_precio,
    p.linea,
    p.estado,
    p.stock,
    p.stock_minimo,
    p.costo_usd,
    p.precio_original_usd,
    -- Top Quality: el precio sale del costo. Originales: de la lista.
    CASE WHEN p.modelo_precio = 'costo' AND p.costo_usd IS NOT NULL
         THEN round(p.costo_usd * (1 + par.ganancia_divisa), 2) END AS precio_divisa_usd,
    CASE WHEN p.modelo_precio = 'costo' AND p.costo_usd IS NOT NULL
         THEN round(p.costo_usd * (1 + par.ganancia_bcv), 2) END    AS precio_bcv_usd,
    CASE WHEN p.modelo_precio = 'lista' AND p.precio_original_usd IS NOT NULL
         THEN p.precio_original_usd END                             AS precio_publico_usd,
    CASE WHEN p.modelo_precio = 'lista' AND p.precio_original_usd IS NOT NULL
         THEN round(p.precio_original_usd * (1 - par.desc_team), 2) END AS precio_team_usd,
    CASE WHEN p.modelo_precio = 'lista' AND p.precio_original_usd IS NOT NULL
         THEN round(p.precio_original_usd * (1 - par.desc_revendedor), 2) END
                                                                    AS precio_revendedor_usd,
    -- Sin base de precio no hay precio: es trabajo pendiente, no un $0,00.
    (p.costo_usd IS NULL AND p.precio_original_usd IS NULL)         AS sin_base_de_precio
FROM productos p
CROSS JOIN parametros par
WHERE p.estado <> 'fusionado';

COMMENT ON VIEW v_precio_vigente IS
    'Precios derivados de costo/lista y de los parametros vigentes. Reemplaza las '
    'columnas precio_divisa, precio_bcv, precio_team y precio_revendedor.';


-- ============================================================== cobranza
-- Reemplaza load_pending_collections_dataframe(), que calculaba un semaforo de tres
-- colores SIN mirar ninguna fecha: "moroso" significaba "nunca abono" y la
-- antiguedad de la deuda era irrelevante.
--
-- La mora es una CONSULTA, no un estado guardado: una columna necesitaria un
-- escritor nocturno y estaria mal entre corridas.
CREATE OR REPLACE VIEW v_cobranza AS
WITH umbrales AS (
    SELECT
        COALESCE(max(valor) FILTER (WHERE clave = 'DIAS_POR_VENCER'), 3)::int       AS dias_por_vencer,
        COALESCE(max(valor) FILTER (WHERE clave = 'DIAS_MORA_PARA_MOROSO'), 15)::int AS dias_moroso
    FROM parametros_precio WHERE vigencia @> CURRENT_DATE
),
abonos AS (
    SELECT venta_id,
           count(*) FILTER (WHERE tipo = 'abono') AS cantidad_abonos,
           max(fecha) FILTER (WHERE tipo = 'abono') AS ultimo_abono_fecha,
           sum(monto_usd) AS abonado_usd
    FROM pagos GROUP BY venta_id
),
recordatorios_ultimos AS (
    SELECT venta_id, max(generado_at) AS ultimo_recordatorio_at, count(*) AS recordatorios
    FROM recordatorios WHERE estado <> 'omitido' GROUP BY venta_id
)
SELECT
    v.id                      AS venta_id,
    v.codigo,
    v.fecha,
    v.fecha_vencimiento,
    v.total_usd,
    v.saldo_usd,
    v.estado_cobro,
    v.plazo_dias,
    v.tiene_plan_cuotas,
    c.id                      AS cliente_id,
    c.nombre                  AS cliente,
    c.telefono_e164,
    c.telefono_e164 IS NOT NULL AS puede_notificar,
    c.es_socio                AS cliente_es_socio,
    u.id                      AS vendedor_usuario_id,
    u.nombre                  AS vendedor,
    COALESCE(a.cantidad_abonos, 0) AS cantidad_abonos,
    a.ultimo_abono_fecha,
    r.ultimo_recordatorio_at,
    COALESCE(r.recordatorios, 0)   AS recordatorios_enviados,
    GREATEST(0, CURRENT_DATE - v.fecha_vencimiento) AS dias_mora,
    -- El semaforo, ahora con fechas de verdad. 'por_vencer' es el estado nuevo y el
    -- mas valioso: es el unico momento en que un recordatorio EVITA la mora en vez
    -- de perseguirla.
    CASE
        WHEN v.anulada_at IS NOT NULL THEN 'anulada'
        WHEN v.saldo_usd <= 0 THEN 'al_dia'
        WHEN v.fecha_vencimiento > CURRENT_DATE + t.dias_por_vencer THEN 'al_dia'
        WHEN v.fecha_vencimiento >= CURRENT_DATE THEN 'por_vencer'
        WHEN CURRENT_DATE - v.fecha_vencimiento > 90 THEN 'incobrable'
        WHEN CURRENT_DATE - v.fecha_vencimiento > t.dias_moroso THEN 'moroso'
        ELSE 'vencido'
    END AS semaforo,
    -- El criterio viejo sobrevive como faceta ortogonal: "nunca abono" es una senal
    -- de riesgo genuinamente distinta de "abono dos veces y se detuvo".
    (COALESCE(a.cantidad_abonos, 0) = 0 AND v.saldo_usd > 0) AS sin_abonos,
    CASE
        WHEN v.saldo_usd <= 0 THEN 'al_dia'
        WHEN CURRENT_DATE <= v.fecha_vencimiento THEN 'al_dia'
        WHEN CURRENT_DATE - v.fecha_vencimiento <= 7  THEN '1_7'
        WHEN CURRENT_DATE - v.fecha_vencimiento <= 15 THEN '8_15'
        WHEN CURRENT_DATE - v.fecha_vencimiento <= 30 THEN '16_30'
        WHEN CURRENT_DATE - v.fecha_vencimiento <= 60 THEN '31_60'
        ELSE 'mas_60'
    END AS bucket
FROM ventas v
JOIN clientes c ON c.id = v.cliente_id
JOIN usuarios u ON u.id = v.vendedor_usuario_id
LEFT JOIN abonos a ON a.venta_id = v.id
LEFT JOIN recordatorios_ultimos r ON r.venta_id = v.id
CROSS JOIN umbrales t;

COMMENT ON VIEW v_cobranza IS
    'Cobranza con antiguedad real. Reemplaza el semaforo sin fechas de '
    'load_pending_collections_dataframe(), donde moroso significaba "nunca abono".';


-- ====================================================== conciliacion de ventas
-- El pedido de "auditar facilmente", comprimido en una vista: el saldo almacenado y
-- el calculado, uno al lado del otro, siempre. El almacenado es sobre el que actua
-- el negocio; el calculado es la verdad.
CREATE OR REPLACE VIEW v_conciliacion_ventas AS
SELECT
    v.id            AS venta_id,
    v.codigo,
    v.fecha,
    v.total_usd,
    COALESCE(i.suma_items, 0)  AS suma_lineas_usd,
    COALESCE(p.abonado, 0)     AS abonado_usd,
    v.total_usd - COALESCE(p.abonado, 0) AS saldo_calculado_usd,
    v.saldo_usd                AS saldo_almacenado_usd,
    v.saldo_usd - (v.total_usd - COALESCE(p.abonado, 0)) AS diferencia_usd,
    v.saldo_congelado_migracion,
    (
        abs(v.saldo_usd - (v.total_usd - COALESCE(p.abonado, 0))) <= 0.005
        AND abs(v.total_usd - COALESCE(i.suma_items, 0)) <= 0.005
    ) AS ok
FROM ventas v
LEFT JOIN (SELECT venta_id, sum(monto_usd) AS abonado FROM pagos GROUP BY venta_id) p
       ON p.venta_id = v.id
LEFT JOIN (SELECT venta_id, sum(subtotal_usd) AS suma_items FROM venta_items GROUP BY venta_id) i
       ON i.venta_id = v.id;


-- ============================================== conciliacion de pagos en bolivares
-- Atrapa los tasa=1.00 metidos a la fuerza y cualquier tipeo futuro.
CREATE OR REPLACE VIEW v_conciliacion_pagos AS
SELECT
    p.id AS pago_id,
    p.venta_id,
    p.fecha,
    p.moneda,
    p.monto_moneda,
    p.tasa_aplicada,
    p.monto_usd,
    round(p.monto_moneda / NULLIF(p.tasa_aplicada, 0), 2) AS monto_usd_calculado,
    p.monto_usd - round(p.monto_moneda / NULLIF(p.tasa_aplicada, 0), 2) AS diferencia_usd,
    p.origen_tasa,
    p.confianza_tasa,
    (abs(p.monto_usd - round(p.monto_moneda / NULLIF(p.tasa_aplicada, 0), 2)) <= 0.01) AS ok
FROM pagos p;


-- ================================================= conciliacion de stock
CREATE OR REPLACE VIEW v_conciliacion_stock AS
SELECT
    p.id AS producto_id,
    p.nombre,
    p.stock AS stock_almacenado,
    COALESCE(m.suma, 0) AS stock_calculado,
    p.stock - COALESCE(m.suma, 0) AS diferencia,
    (p.stock = COALESCE(m.suma, 0)) AS ok
FROM productos p
LEFT JOIN (SELECT producto_id, sum(cantidad) AS suma FROM movimientos_stock GROUP BY producto_id) m
       ON m.producto_id = p.id
WHERE p.estado <> 'fusionado';


-- ============================================ calidad de datos: la fuga de precio
-- Convierte un hallazgo puntual de un PDF en un numero vivo del que alguien es
-- responsable. Es la pantalla mas valiosa del sistema para este negocio.
CREATE OR REPLACE VIEW v_fuga_precio AS
SELECT
    i.id                AS venta_item_id,
    v.id                AS venta_id,
    v.codigo,
    v.fecha,
    v.moneda_cotizacion,
    c.nombre            AS cliente,
    u.nombre            AS vendedor,
    i.descripcion_libre AS producto_tecleado,
    pr.nombre           AS producto,
    i.cantidad,
    i.costo_unitario_usd,
    i.precio_unitario_usd   AS cobrado_usd,
    i.precio_lista_usd      AS politica_usd,
    i.desviacion_pct,
    round((i.precio_lista_usd - i.precio_unitario_usd) * i.cantidad, 2) AS fuga_usd,
    i.motivo_desviacion,
    i.aprobado_por_usuario_id IS NOT NULL AS autorizado,
    (i.precio_unitario_usd < i.costo_unitario_usd) AS bajo_costo
FROM venta_items i
JOIN ventas v   ON v.id = i.venta_id
JOIN clientes c ON c.id = v.cliente_id
JOIN usuarios u ON u.id = v.vendedor_usuario_id
JOIN productos pr ON pr.id = i.producto_id
WHERE i.precio_lista_usd IS NOT NULL
  AND i.precio_unitario_usd < i.precio_lista_usd;

COMMENT ON VIEW v_fuga_precio IS
    'Lineas cobradas por debajo del precio de politica de su nivel declarado. El '
    'informe midio $123 perdidos en 56 dias por esta causa: 26 % de la ganancia.';


-- ================================================= margenes por producto
-- Agrupa por producto_id y no por el texto del nombre, que era lo que hacia que dos
-- grafias del mismo perfume fueran dos productos en todos los reportes.
CREATE OR REPLACE VIEW v_margen_producto AS
SELECT
    pr.id       AS producto_id,
    pr.nombre,
    pr.linea,
    pr.costo_usd,
    count(DISTINCT v.id)          AS operaciones,
    sum(i.cantidad)               AS unidades,
    sum(i.subtotal_usd)           AS ingreso_usd,
    sum(i.cantidad * i.costo_unitario_usd) AS costo_usd_total,
    sum(i.ganancia_usd)           AS ganancia_usd,
    CASE WHEN sum(i.subtotal_usd) > 0
         THEN round(sum(i.ganancia_usd) / sum(i.subtotal_usd) * 100, 2) END AS margen_pct
FROM venta_items i
JOIN productos pr ON pr.id = i.producto_id
JOIN ventas v ON v.id = i.venta_id AND v.anulada_at IS NULL
GROUP BY pr.id, pr.nombre, pr.linea, pr.costo_usd;


-- ================================================= deuda por cliente
-- La cobranza va por persona y no por venta: 18 ventas son ~12 personas, y mandarle
-- a alguien tres mensajes separados es como se pierde un cliente.
CREATE OR REPLACE VIEW v_deuda_cliente AS
SELECT
    c.id        AS cliente_id,
    c.nombre    AS cliente,
    c.telefono_e164,
    c.telefono_e164 IS NOT NULL AS puede_notificar,
    c.es_socio,
    count(*)                    AS ventas_abiertas,
    sum(cb.saldo_usd)           AS deuda_usd,
    max(cb.dias_mora)           AS dias_mora_maximo,
    min(cb.fecha_vencimiento)   AS vencimiento_mas_viejo,
    max(cb.ultimo_abono_fecha)  AS ultimo_abono_fecha,
    max(cb.ultimo_recordatorio_at) AS ultimo_recordatorio_at,
    bool_and(cb.sin_abonos)     AS nunca_abono,
    -- El peor semaforo del cliente manda: es lo que decide la urgencia.
    (ARRAY['incobrable','moroso','vencido','por_vencer','al_dia'])[
        min(array_position(ARRAY['incobrable','moroso','vencido','por_vencer','al_dia'],
                           cb.semaforo))
    ] AS peor_semaforo
FROM v_cobranza cb
JOIN clientes c ON c.id = cb.cliente_id
WHERE cb.saldo_usd > 0
GROUP BY c.id, c.nombre, c.telefono_e164, c.es_socio;


-- ================================================= rentabilidad semanal
CREATE OR REPLACE VIEW v_rentabilidad_semanal AS
SELECT
    date_trunc('week', v.fecha)::date AS semana,
    count(DISTINCT v.id)      AS ventas,
    sum(i.subtotal_usd)       AS ingreso_usd,
    sum(i.cantidad * i.costo_unitario_usd) AS costo_usd,
    sum(i.ganancia_usd)       AS ganancia_usd
FROM ventas v
JOIN venta_items i ON i.venta_id = v.id
WHERE v.anulada_at IS NULL
GROUP BY 1;


-- ================================================= stock bajo y demanda sin stock
CREATE OR REPLACE VIEW v_stock_bajo AS
SELECT p.id AS producto_id, p.nombre, p.linea, p.stock, p.stock_minimo, p.costo_usd,
       (SELECT count(*) FROM venta_items i WHERE i.producto_id = p.id) AS ventas_historicas
FROM productos p
WHERE p.estado = 'activo' AND p.stock <= p.stock_minimo;

CREATE OR REPLACE VIEW v_demanda_sin_stock AS
SELECT p.id AS producto_id, p.nombre, p.linea, p.costo_usd,
       count(*)          AS operaciones,
       sum(i.cantidad)   AS unidades_vendidas,
       max(v.fecha)      AS ultima_venta
FROM productos p
JOIN venta_items i ON i.producto_id = p.id
JOIN ventas v ON v.id = i.venta_id
WHERE p.stock <= 0 AND p.estado <> 'fusionado'
GROUP BY p.id, p.nombre, p.linea, p.costo_usd;


-- ================================================= calidad de datos, resumen
-- Alimenta las tarjetas de /auditoria/calidad. Un solo lugar donde se define que
-- cuenta como problema, para que el numero de la tarjeta y las filas del drill-down
-- no puedan discrepar.
CREATE OR REPLACE VIEW v_calidad_datos AS
SELECT 'productos_sin_costo' AS clave, 'Productos sin costo cargado' AS etiqueta,
       'alta' AS severidad,
       (SELECT count(*) FROM productos
         WHERE estado <> 'fusionado' AND costo_usd IS NULL AND precio_original_usd IS NULL) AS cantidad,
       'Su precio no se puede calcular ni validar' AS explicacion
UNION ALL
SELECT 'productos_por_revisar', 'Productos pendientes de revision', 'media',
       (SELECT count(*) FROM productos WHERE estado = 'borrador_por_revisar'),
       'Creados al vuelo desde una venta o sin evidencia para fusionar'
UNION ALL
SELECT 'clientes_sin_telefono', 'Clientes sin telefono', 'alta',
       (SELECT count(*) FROM clientes
         WHERE estado = 'activo' AND telefono_e164 IS NULL),
       'Sin telefono no se les puede enviar un recordatorio'
UNION ALL
SELECT 'deudores_sin_telefono', 'Deudores sin telefono', 'alta',
       (SELECT count(*) FROM v_deuda_cliente WHERE NOT puede_notificar),
       'Deben plata y no hay como notificarles'
UNION ALL
SELECT 'pagos_sin_tasa_confiable', 'Pagos con tasa deducida', 'media',
       (SELECT count(*) FROM pagos WHERE origen_tasa = 'sintetizada_migracion'),
       'La tasa se despejo de una heuristica, no se registro'
UNION ALL
SELECT 'ventas_bajo_costo', 'Ventas por debajo del costo', 'alta',
       (SELECT count(*) FROM venta_items WHERE precio_unitario_usd < costo_unitario_usd),
       'Se vendio perdiendo dinero'
UNION ALL
SELECT 'fuga_precio', 'Ventas cobradas bajo la politica', 'alta',
       (SELECT count(*) FROM v_fuga_precio),
       'Se cobro el nivel divisa declarando BCV, o menos'
UNION ALL
SELECT 'clientes_a_revisar', 'Clientes posiblemente duplicados', 'media',
       (SELECT count(*) FROM clientes WHERE notas LIKE 'Revisar:%'),
       'Un nombre es prefijo de otro; hay que decidir si es la misma persona'
UNION ALL
SELECT 'conciliacion_ventas', 'Ventas descuadradas', 'critica',
       (SELECT count(*) FROM v_conciliacion_ventas WHERE NOT ok),
       'El saldo almacenado no coincide con el libro de pagos'
UNION ALL
SELECT 'conciliacion_pagos', 'Pagos descuadrados', 'critica',
       (SELECT count(*) FROM v_conciliacion_pagos WHERE NOT ok),
       'monto en moneda / tasa no reproduce el monto en dolares'
UNION ALL
SELECT 'conciliacion_stock', 'Stock descuadrado', 'media',
       (SELECT count(*) FROM v_conciliacion_stock WHERE NOT ok),
       'El stock guardado no coincide con la suma de sus movimientos';
