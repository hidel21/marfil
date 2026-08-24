-- Auditoria generica por trigger.
--
-- Por trigger y no en la aplicacion porque el codigo tiene tres caminos de
-- escritura que evitan register_payment y un migrador de DDL que corre SQL crudo:
-- auditar en Python audita solo los caminos que alguien recordo.
--
-- El actor sale de current_setting('app.usuario_id'), que la sesion pone con
-- SET LOCAL en cada transaccion. Sin actor, el cambio es de 'sistema'.

CREATE OR REPLACE FUNCTION fn_auditar() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_antes        jsonb;
    v_despues      jsonb;
    v_cambiados    text[];
    v_usuario_id   integer;
    v_request_id   uuid;
    v_actor        actor_auditoria;
    v_registro_id  text;
    v_motivo       text;
BEGIN
    -- Actor
    BEGIN
        v_usuario_id := nullif(current_setting('app.usuario_id', true), '')::integer;
    EXCEPTION WHEN others THEN
        v_usuario_id := NULL;
    END;
    BEGIN
        v_request_id := nullif(current_setting('app.request_id', true), '')::uuid;
    EXCEPTION WHEN others THEN
        v_request_id := NULL;
    END;

    IF v_usuario_id IS NOT NULL THEN
        v_actor := 'usuario';
    ELSE
        v_actor := COALESCE(
            nullif(current_setting('app.actor_tipo', true), '')::actor_auditoria,
            'sistema'
        );
    END IF;

    IF (TG_OP = 'DELETE') THEN
        v_antes   := to_jsonb(OLD);
        v_despues := NULL;
    ELSIF (TG_OP = 'INSERT') THEN
        v_antes   := NULL;
        v_despues := to_jsonb(NEW);
    ELSE
        v_antes   := to_jsonb(OLD);
        v_despues := to_jsonb(NEW);
        -- Solo las claves que realmente cambiaron: hace legible un UPDATE de un vistazo.
        SELECT array_agg(clave ORDER BY clave) INTO v_cambiados
        FROM (
            SELECT key AS clave FROM jsonb_each(v_despues)
            EXCEPT
            SELECT key FROM jsonb_each(v_antes)
            UNION
            SELECT d.key
            FROM jsonb_each(v_despues) d
            JOIN jsonb_each(v_antes) a ON a.key = d.key
            WHERE d.value IS DISTINCT FROM a.value
        ) AS diferencias;

        -- Un UPDATE que no cambia nada no merece una fila.
        IF v_cambiados IS NULL OR array_length(v_cambiados, 1) = 0 THEN
            RETURN NEW;
        END IF;
    END IF;

    v_registro_id := COALESCE(v_despues, v_antes) ->> 'id';
    IF v_registro_id IS NULL THEN
        v_registro_id := COALESCE(v_despues, v_antes) ->> 'clave';
    END IF;

    -- El motivo, cuando la fila lo trae, es lo que alimenta el filtro
    -- "solo excepciones" de la pantalla de auditoria.
    v_motivo := COALESCE(
        COALESCE(v_despues, v_antes) ->> 'motivo',
        COALESCE(v_despues, v_antes) ->> 'motivo_desviacion',
        COALESCE(v_despues, v_antes) ->> 'motivo_anulacion'
    );

    INSERT INTO auditoria (
        actor_tipo, usuario_id, accion, tabla, registro_id,
        antes, despues, campos_cambiados, motivo, request_id
    ) VALUES (
        v_actor, v_usuario_id, TG_OP::accion_auditoria, TG_TABLE_NAME, v_registro_id,
        v_antes, v_despues, v_cambiados, v_motivo, v_request_id
    );

    IF (TG_OP = 'DELETE') THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION fn_auditar() IS
    'Trigger de auditoria generico. Se cuelga AFTER INSERT/UPDATE/DELETE FOR EACH ROW.';
