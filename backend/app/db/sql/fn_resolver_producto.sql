-- Resolucion de un nombre de producto a un id, deterministica.
--
-- Hace falta porque un mismo nombre puede tener DOS alias: 'bharara king' existe en
-- `PRECIOS PERF TOP QUALITY` y en `PRECIOS PERF ORIGINALES`, y la clave de unicidad
-- es (nombre, es_original) justamente para no fusionarlos. Pero una venta historica
-- solo dice 'Bharara King' y no de cual de las dos listas salio, asi que hay que
-- elegir con una regla escrita en un solo lugar.
--
-- La regla, en orden:
--   1. el que tiene costo cargado  -> es el que el negocio realmente vende;
--   2. el Top Quality antes que el Original -> es la linea que mueven;
--   3. el id mas bajo -> desempate estable, para que dos corridas den lo mismo.

CREATE OR REPLACE FUNCTION resolver_producto(nombre_libre text)
RETURNS integer LANGUAGE sql STABLE AS $$
    SELECT p.id
      FROM productos_alias a
      JOIN productos p ON p.id = a.producto_id
     WHERE a.alias_normalizado = clave_nombre(nombre_libre)
       AND p.estado <> 'fusionado'
     ORDER BY (p.costo_usd IS NULL), p.es_original, p.id
     LIMIT 1;
$$;

COMMENT ON FUNCTION resolver_producto(text) IS
    'Nombre libre -> producto_id, con desempate deterministico. Un mismo nombre puede '
    'estar en Top Quality y en Originales; la venta historica no dice cual.';
