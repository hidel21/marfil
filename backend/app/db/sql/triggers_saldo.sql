-- Triggers que mantienen los cachés derivados y hacen inmutable el libro de pagos.
--
-- La decision de fondo: el libro (pagos) es la unica fuente de verdad y
-- ventas.saldo_usd es un cache. Un SUM() en cada lectura le cuesta un scan a las
-- dos consultas mas calientes y total - SUM(pagos) no se puede indexar; un trigger
-- da una columna indexable que ningun camino de escritura puede desincronizar.

-- ---------------------------------------------------------------- pagos: inmutable
-- Compara via jsonb y no con NEW.<columna> a proposito: entre la revision 0001 y la
-- 0006 la tabla `pagos` tiene la forma vieja (monto_bs, tasa_bcv) y despues la nueva
-- (monto_moneda, tasa_aplicada, moneda, tipo). Referenciar una columna que todavia no
-- existe hace que el trigger falle con "record new has no field ...": bloquea, pero
-- por la razon equivocada y sin comprobar nada. Asi el mismo trigger vale en las dos
-- formas y solo compara los campos que existen.
CREATE OR REPLACE FUNCTION fn_pagos_inmutable() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    INMUTABLES constant text[] := ARRAY[
        'venta_id', 'fecha', 'monto_usd',
        'monto_bs', 'tasa_bcv',                    -- forma anterior a 0006
        'monto_moneda', 'tasa_aplicada', 'moneda', 'tipo'  -- forma desde 0006
    ];
    v_antes    jsonb := to_jsonb(OLD);
    v_despues  jsonb := to_jsonb(NEW);
    v_campo    text;
    v_violados text[] := '{}';
BEGIN
    IF (TG_OP = 'DELETE') THEN
        RAISE EXCEPTION
            'El libro de pagos es append-only: no se borra el pago %. Registra un reverso (tipo=''reverso'').',
            OLD.id
            USING ERRCODE = 'restrict_violation';
    END IF;

    FOREACH v_campo IN ARRAY INMUTABLES LOOP
        IF v_antes ? v_campo
           AND (v_antes -> v_campo) IS DISTINCT FROM (v_despues -> v_campo) THEN
            v_violados := array_append(v_violados, v_campo);
        END IF;
    END LOOP;

    IF array_length(v_violados, 1) > 0 THEN
        RAISE EXCEPTION
            'El pago % es inmutable en %. Registra un reverso en vez de editarlo.',
            OLD.id, array_to_string(v_violados, ', ')
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$;

-- ------------------------------------------------- ventas: total, costo desde items
CREATE OR REPLACE FUNCTION fn_recalcular_totales_venta() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_venta_id integer := COALESCE(NEW.venta_id, OLD.venta_id);
    v_total    numeric(14,2);
    v_con_plan boolean;
    v_vence    date;
BEGIN
    UPDATE ventas v
       SET total_usd = COALESCE(i.total, 0),
           costo_usd = COALESCE(i.costo, 0)
      FROM (
            SELECT SUM(subtotal_usd) AS total,
                   SUM(cantidad * costo_unitario_usd) AS costo
              FROM venta_items
             WHERE venta_id = v_venta_id
           ) i
     WHERE v.id = v_venta_id;

    -- La cuota implicita del plazo por defecto.
    --
    -- Va aca y no en la capa de compatibilidad porque es parte del modelo, no un
    -- parche: TODA venta tiene al menos una cuota, para que la consulta de
    -- antiguedad tenga un solo camino de codigo con plan y sin plan. Sin esto, una
    -- venta recien registrada queda fuera de la cobranza, que es exactamente el
    -- agujero que este sistema viene a cerrar.
    SELECT total_usd, tiene_plan_cuotas, fecha_vencimiento
      INTO v_total, v_con_plan, v_vence
      FROM ventas WHERE id = v_venta_id;

    IF v_total > 0 AND NOT COALESCE(v_con_plan, FALSE) THEN
        INSERT INTO cuotas (venta_id, numero, fecha_vencimiento, monto_usd, implicita)
        VALUES (v_venta_id, 1, v_vence, v_total, TRUE)
        ON CONFLICT (venta_id, numero) DO UPDATE
           SET monto_usd = EXCLUDED.monto_usd
         WHERE cuotas.implicita;
    END IF;

    PERFORM fn_recalcular_saldo_venta(v_venta_id);
    RETURN NULL;
END;
$$;

-- ----------------------------------------- ventas: saldo y estado desde el libro
CREATE OR REPLACE FUNCTION fn_recalcular_saldo_venta(p_venta_id integer) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    v_total    numeric(14,2);
    v_abonado  numeric(14,2);
    v_saldo    numeric(14,2);
    v_pagos    integer;
    v_anulada  boolean;
    v_estado   estado_cobro;
BEGIN
    SELECT total_usd, anulada_at IS NOT NULL
      INTO v_total, v_anulada
      FROM ventas WHERE id = p_venta_id;

    IF NOT FOUND THEN
        RETURN;
    END IF;

    SELECT COALESCE(SUM(monto_usd), 0), COUNT(*) FILTER (WHERE tipo = 'abono')
      INTO v_abonado, v_pagos
      FROM pagos WHERE venta_id = p_venta_id;

    v_saldo := GREATEST(0, v_total - v_abonado);
    -- Mismo epsilon de medio centavo que ya usaba register_payment.
    IF v_saldo < 0.005 THEN
        v_saldo := 0;
    END IF;

    IF v_anulada THEN
        v_estado := 'anulada';
    ELSIF v_saldo = 0 THEN
        v_estado := 'pagada';
    ELSIF v_pagos = 0 THEN
        -- El tercer estado que el Excel usaba y la app habia perdido.
        v_estado := 'pendiente_sin_abonos';
    ELSE
        v_estado := 'pendiente_parcial';
    END IF;

    UPDATE ventas
       SET saldo_usd = v_saldo,
           estado_cobro = v_estado
     WHERE id = p_venta_id
       AND (saldo_usd IS DISTINCT FROM v_saldo OR estado_cobro IS DISTINCT FROM v_estado);
END;
$$;

CREATE OR REPLACE FUNCTION fn_pagos_actualizan_saldo() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_venta_id integer := COALESCE(NEW.venta_id, OLD.venta_id);
    v_cuota_id integer;
BEGIN
    PERFORM fn_recalcular_saldo_venta(v_venta_id);

    -- Cuota afectada (la nueva y la vieja, si cambiaron)
    FOR v_cuota_id IN
        SELECT DISTINCT c FROM unnest(ARRAY[NEW.cuota_id, OLD.cuota_id]) AS c WHERE c IS NOT NULL
    LOOP
        UPDATE cuotas q
           SET monto_abonado_usd = LEAST(
                   q.monto_usd,
                   GREATEST(0, COALESCE((SELECT SUM(monto_usd) FROM pagos WHERE cuota_id = q.id), 0))
               )
         WHERE q.id = v_cuota_id;
    END LOOP;

    RETURN NULL;
END;
$$;

-- ------------------------------------- ventas: vencimiento desde la cuota mas vieja
CREATE OR REPLACE FUNCTION fn_actualizar_vencimiento_venta() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_venta_id integer := COALESCE(NEW.venta_id, OLD.venta_id);
    v_fecha    date;
BEGIN
    SELECT MIN(fecha_vencimiento) INTO v_fecha
      FROM cuotas
     WHERE venta_id = v_venta_id
       AND monto_abonado_usd < monto_usd;

    IF v_fecha IS NOT NULL THEN
        UPDATE ventas SET fecha_vencimiento = v_fecha
         WHERE id = v_venta_id AND fecha_vencimiento IS DISTINCT FROM v_fecha;
    END IF;
    RETURN NULL;
END;
$$;

-- --------------------------------------------- productos.stock desde movimientos
CREATE OR REPLACE FUNCTION fn_recalcular_stock() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_producto_id integer := COALESCE(NEW.producto_id, OLD.producto_id);
BEGIN
    UPDATE productos p
       SET stock = COALESCE(
               (SELECT SUM(cantidad) FROM movimientos_stock WHERE producto_id = v_producto_id), 0
           )
     WHERE p.id = v_producto_id;
    RETURN NULL;
END;
$$;
