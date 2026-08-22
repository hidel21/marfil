-- clave_nombre() en SQL, gemela de app.core.normalizacion.clave_nombre().
--
-- Existe para que la invariante "nombre_normalizado siempre corresponde a nombre"
-- la garantice la base y no cada escritor. Streamlit, la API y el ETL escriben en
-- `productos` y `clientes`; pedirle a los tres que se acuerden de llenar la columna
-- es pedir que uno se olvide. Con el trigger no se puede olvidar.
--
-- Las dos definiciones tienen que dar lo mismo. Hay un test que lo comprueba sobre
-- los nombres reales del catalogo: tests/test_clave_nombre_paridad.py.

CREATE OR REPLACE FUNCTION clave_nombre(texto text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    -- unaccent() con el diccionario explicito para poder marcar la funcion IMMUTABLE:
    -- unaccent(text) sola es STABLE porque resuelve el diccionario en tiempo de
    -- ejecucion, y eso impediria usar clave_nombre() en un indice.
    SELECT regexp_replace(
        lower(unaccent('unaccent'::regdictionary, btrim(texto))),
        '[^a-z0-9]', '', 'g'
    );
$$;

COMMENT ON FUNCTION clave_nombre(text) IS
    'Clave de unicidad de nombres: minusculas, sin acentos, sin espacios ni signos. '
    'Gemela de app.core.normalizacion.clave_nombre(). Sin espacios porque la auditoria '
    'documenta 212 Vip / 212 vip / 212Vip como el mismo producto.';


-- Trigger reutilizable: llena <columna>_normalizado desde <columna>.
CREATE OR REPLACE FUNCTION fn_normalizar_nombre() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_origen  text := COALESCE(TG_ARGV[0], 'nombre');
    v_destino text := COALESCE(TG_ARGV[1], 'nombre_normalizado');
    v_valor   text;
    v_fila    jsonb := to_jsonb(NEW);
BEGIN
    v_valor := v_fila ->> v_origen;
    IF v_valor IS NULL THEN
        RETURN NEW;
    END IF;
    -- Siempre se recalcula: si alguien cambia el nombre, la clave lo sigue. Dejar
    -- que un escritor imponga su propia clave es como se desincronizan las dos.
    NEW := jsonb_populate_record(NEW, jsonb_build_object(v_destino, clave_nombre(v_valor)));
    RETURN NEW;
END;
$$;
