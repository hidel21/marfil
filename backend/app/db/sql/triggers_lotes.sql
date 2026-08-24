-- Trigger del bloque de oferta. Separado de triggers_saldo.sql porque su tabla
-- (`compras` con su forma nueva) llega en la revision 0009, no en 0001.

-- ------------------------------ lotes_compra.subtotal_calculado desde las compras
CREATE OR REPLACE FUNCTION fn_recalcular_subtotal_lote() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_lote_id integer := COALESCE(NEW.lote_id, OLD.lote_id);
BEGIN
    UPDATE lotes_compra l
       SET subtotal_calculado_usd = COALESCE(
               (SELECT SUM(cantidad * costo_unitario_usd) FROM compras WHERE lote_id = v_lote_id), 0
           )
     WHERE l.id = v_lote_id;
    RETURN NULL;
END;
$$;
