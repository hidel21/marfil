-- Capa de compatibilidad con Streamlit. TEMPORAL: se suelta en el cutover.
--
-- El problema que resuelve: desde la revision 0005 el modelo canonico de una venta
-- es `ventas` + `venta_items` + `cuotas`, y el saldo lo calcula un trigger desde el
-- libro de pagos. Pero Streamlit sigue siendo el escritor durante las fases 2 y 3,
-- y `register_sale` escribe una venta de una sola linea con columnas planas
-- (cliente, producto, precio_venta, deuda) sin tocar `venta_items`.
--
-- Sin esta capa hay dos representaciones distintas de la misma venta y el saldo de
-- las que crea Streamlit queda en cero. Con ella hay una sola: los triggers traducen
-- la escritura plana al modelo canonico, y devuelven el saldo calculado a las
-- columnas viejas para que las 28 consultas de Streamlit sigan leyendo bien.
--
-- Es deliberadamente generoso (crea el cliente si no existe, resuelve el vendedor
-- por nombre) porque su alternativa es que el negocio no pueda registrar una venta
-- durante la convivencia.

-- ------------------------------------------------------- ventas: rellenar lo nuevo
CREATE OR REPLACE FUNCTION fn_compat_ventas_completar() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_clave      text;
    v_cliente_id integer;
    v_plazo      integer;
BEGIN
    -- Codigo legible: V-<anio>-<id>. Se completa despues del INSERT porque el id
    -- todavia no existe; aca solo se reserva un valor unico provisional.
    IF NEW.codigo IS NULL THEN
        NEW.codigo := 'V-' || to_char(COALESCE(NEW.fecha, CURRENT_DATE), 'YYYY')
                      || '-' || nextval('ventas_codigo_seq');
    END IF;

    -- Cliente: se resuelve por alias y, si no existe, se crea. Bloquear una venta
    -- porque el cliente es nuevo seria exactamente el problema que hay que evitar.
    IF NEW.cliente_id IS NULL AND NEW.cliente IS NOT NULL THEN
        v_clave := clave_nombre(NEW.cliente);
        SELECT cliente_id INTO v_cliente_id
          FROM clientes_alias WHERE alias_normalizado = v_clave;

        IF v_cliente_id IS NULL THEN
            INSERT INTO clientes (nombre, nombre_normalizado)
            VALUES (btrim(NEW.cliente), v_clave)
            ON CONFLICT (nombre_normalizado) WHERE estado <> 'fusionado'
            DO UPDATE SET nombre = clientes.nombre
            RETURNING id INTO v_cliente_id;

            INSERT INTO clientes_alias (cliente_id, alias, alias_normalizado, origen)
            VALUES (v_cliente_id, btrim(NEW.cliente), v_clave, 'compat_streamlit')
            ON CONFLICT (alias_normalizado) DO NOTHING;
        END IF;
        NEW.cliente_id := v_cliente_id;
    END IF;

    -- Vendedor: por nombre exacto contra usuarios. Si no coincide, cae en el primer
    -- admin, porque la venta tiene que quedar registrada aunque la atribucion falle.
    IF NEW.vendedor_usuario_id IS NULL THEN
        SELECT id INTO NEW.vendedor_usuario_id
          FROM usuarios
         WHERE clave_nombre(nombre) = clave_nombre(COALESCE(NEW.vendedor, ''))
         LIMIT 1;
        IF NEW.vendedor_usuario_id IS NULL THEN
            SELECT id INTO NEW.vendedor_usuario_id
              FROM usuarios WHERE rol = 'admin' ORDER BY id LIMIT 1;
        END IF;
    END IF;

    -- 'BCV' era el unico valor que escribia register_sale, y significa tasa BCV.
    IF NEW.moneda_cotizacion IS NULL THEN
        NEW.moneda_cotizacion := CASE
            WHEN upper(COALESCE(NEW.moneda, 'BCV')) IN ('USD', 'DIVISA') THEN 'USD'::moneda
            WHEN upper(COALESCE(NEW.moneda, 'BCV')) = 'USDT' THEN 'USDT'::moneda
            ELSE 'VES'::moneda
        END;
    END IF;

    IF NEW.fecha IS NULL THEN
        NEW.fecha := CURRENT_DATE;
    END IF;

    IF NEW.plazo_dias IS NULL THEN
        SELECT COALESCE(valor::integer, 15) INTO v_plazo
          FROM parametros_precio
         WHERE clave = 'PLAZO_CREDITO_DIAS' AND vigencia @> NEW.fecha
         LIMIT 1;
        NEW.plazo_dias := COALESCE(v_plazo, 15);
    END IF;

    IF NEW.fecha_vencimiento IS NULL THEN
        NEW.fecha_vencimiento := NEW.fecha + NEW.plazo_dias;
    END IF;

    RETURN NEW;
END;
$$;

-- ------------------------------ ventas: crear la linea y la cuota implicita
CREATE OR REPLACE FUNCTION fn_compat_ventas_linea() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_producto_id integer;
    v_cantidad    integer := GREATEST(1, COALESCE(NEW.cantidad, 1));
    v_precio      numeric(14,2) := COALESCE(NEW.precio_venta, 0);
    v_costo       numeric(14,2) := COALESCE(NEW.costo, 0);
BEGIN
    -- Codigo definitivo, ahora que hay id.
    UPDATE ventas
       SET codigo = 'V-' || to_char(fecha, 'YYYY') || '-' || lpad(id::text, 4, '0')
     WHERE id = NEW.id AND codigo LIKE 'V-%-%' AND codigo !~ '-[0-9]{4}$';

    IF EXISTS (SELECT 1 FROM venta_items WHERE venta_id = NEW.id) THEN
        RETURN NULL;
    END IF;

    IF NEW.producto IS NOT NULL THEN
        -- Misma regla de desempate que usa la migracion, en un solo lugar.
        v_producto_id := resolver_producto(NEW.producto);

        -- Producto que no esta en el catalogo: se crea como borrador. Es el mismo
        -- mecanismo que va a usar la API para el alta rapida.
        IF v_producto_id IS NULL THEN
            INSERT INTO productos (nombre, costo, precio_divisa, precio_bcv, stock,
                                   precio_unitario, precio_original, precio_team,
                                   precio_revendedor, estado, origen_alta, notas)
            VALUES (btrim(NEW.producto), 0, 0, 0, 0, 0, 0, 0, 0,
                    'borrador_por_revisar', 'venta_rapida',
                    'Creado desde una venta de Streamlit durante la convivencia.')
            RETURNING id INTO v_producto_id;

            INSERT INTO productos_alias (producto_id, alias, alias_normalizado,
                                         es_original, origen)
            VALUES (v_producto_id, btrim(NEW.producto), clave_nombre(NEW.producto),
                    FALSE, 'compat_streamlit')
            ON CONFLICT (alias_normalizado, es_original) DO NOTHING;
        END IF;

        INSERT INTO venta_items (venta_id, linea, producto_id, descripcion_libre,
                                 cantidad, precio_unitario_usd, costo_unitario_usd)
        VALUES (NEW.id, 1, v_producto_id, NEW.producto, v_cantidad,
                round(v_precio / v_cantidad, 2), round(v_costo / v_cantidad, 2));
    END IF;

    RETURN NULL;
END;
$$;

-- ------------------------------------- devolver el saldo calculado a las columnas viejas
CREATE OR REPLACE FUNCTION fn_compat_espejo_saldo() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    -- `deuda` y `estatus` pasan a ser un espejo de solo lectura de lo que calcula el
    -- trigger canonico. Streamlit las lee en 12 de sus 28 consultas.
    --
    -- El espejo habla el vocabulario VIEJO a proposito: solo 'YA PAGO' y 'PENDIENTE'.
    -- El tercer estado ('pendiente_sin_abonos') vive en `estado_cobro`, que es el
    -- campo real. Escribirlo en `estatus` romperia los filtros de Streamlit, que
    -- comparan con igualdad exacta contra esas dos cadenas: la venta sin abonos
    -- desapareceria de sus listas de pendientes.
    IF NEW.saldo_usd IS DISTINCT FROM OLD.saldo_usd
       OR NEW.total_usd IS DISTINCT FROM OLD.total_usd
       OR NEW.estado_cobro IS DISTINCT FROM OLD.estado_cobro THEN
        UPDATE ventas
           SET deuda = NEW.saldo_usd,
               total = NEW.total_usd,
               precio_venta = NEW.total_usd,
               costo = NEW.costo_usd,
               ganancia = NEW.total_usd - NEW.costo_usd,
               estatus = CASE WHEN NEW.estado_cobro = 'pagada'
                              THEN 'YA PAGO' ELSE 'PENDIENTE' END
         WHERE id = NEW.id
           AND (deuda IS DISTINCT FROM NEW.saldo_usd
                OR total IS DISTINCT FROM NEW.total_usd
                OR estatus IS DISTINCT FROM CASE WHEN NEW.estado_cobro = 'pagada'
                                                 THEN 'YA PAGO' ELSE 'PENDIENTE' END);
    END IF;
    RETURN NULL;
END;
$$;

-- ------------------------------------------- pagos: rellenar la forma del libro
CREATE OR REPLACE FUNCTION fn_compat_pagos_completar() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.tipo IS NULL THEN
        NEW.tipo := 'abono';
    END IF;

    -- Streamlit escribe monto_bs + tasa_bcv. Si la tasa es 1, el pago fue en dolares
    -- en efectivo: es el hack que esta capa traduce a la ruta explicita.
    IF NEW.moneda IS NULL THEN
        IF COALESCE(NEW.tasa_bcv, 0) <= 1 THEN
            NEW.moneda := 'USD'::moneda;
            NEW.monto_moneda := COALESCE(NEW.monto_usd, NEW.monto_bs, 0);
            NEW.tasa_aplicada := 1;
            NEW.canal := COALESCE(NEW.canal, 'efectivo_usd'::canal_pago);
            NEW.origen_tasa := COALESCE(NEW.origen_tasa, 'manual'::origen_tasa);
        ELSE
            NEW.moneda := 'VES'::moneda;
            NEW.monto_moneda := COALESCE(NEW.monto_bs, 0);
            NEW.tasa_aplicada := NEW.tasa_bcv;
            NEW.canal := COALESCE(NEW.canal, 'pago_movil'::canal_pago);
            NEW.origen_tasa := COALESCE(NEW.origen_tasa, 'manual'::origen_tasa);
        END IF;
    END IF;

    IF NEW.nro_bloque IS NULL THEN
        NEW.nro_bloque := NEW.nro_cuota;
    END IF;

    -- La cuota mas vieja con saldo, para que el abono se aplique a algo.
    IF NEW.cuota_id IS NULL THEN
        SELECT id INTO NEW.cuota_id
          FROM cuotas
         WHERE venta_id = NEW.venta_id AND monto_abonado_usd < monto_usd
         ORDER BY numero LIMIT 1;
    END IF;

    IF NEW.referencia IS NOT NULL AND btrim(NEW.referencia) IN ('', 'SIN REFERENCIA') THEN
        NEW.referencia := NULL;
    END IF;

    RETURN NEW;
END;
$$;
