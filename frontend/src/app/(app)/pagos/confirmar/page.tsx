"use client";

import { useMemo, useState } from "react";
import { toast } from "sonner";
import { BadgeCheck, X } from "lucide-react";
import { Dinero } from "@/components/dinero";
import {
  Aviso,
  Boton,
  Cargando,
  Input,
  Insignia,
  Select,
  Tabla,
  Td,
  Th,
  Titulo,
  Vacio,
} from "@/components/ui";
import {
  type PagoAVerificar,
  useConfirmarPagos,
  useRechazarPago,
  useVerificacion,
} from "@/hooks/datos";
import { FalloApi } from "@/lib/api";
import { sumar } from "@/lib/dinero";
import { fecha, fechaHora } from "@/lib/formato";

/**
 * Verificación bancaria: cada abono registrado se compara contra la cuenta.
 *
 * Un pago "por confirmar" ya descuenta la deuda —así lo decidieron los socios: no se
 * persigue a quien pagó solo porque falta revisar el banco—. Confirmar deja escrito
 * que la plata llegó. Rechazar lo reversa con su fecha y la deuda vuelve.
 *
 * Se confirma en lote porque así se trabaja con el estado de cuenta en la mano: se
 * marcan los que aparecen y se confirman juntos. Rechazar va de a uno y con motivo,
 * porque cambia la deuda de un cliente y alguien va a preguntar por qué.
 */

const CANAL: Record<string, string> = {
  pago_movil: "Pago móvil",
  transferencia: "Transferencia",
  efectivo_bs: "Efectivo Bs",
  efectivo_usd: "Efectivo USD",
  zelle: "Zelle",
  binance: "Binance",
  usdt: "USDT",
  otro: "Otro",
};

export default function ConfirmarPagos() {
  const [estado, setEstado] = useState("pendiente");
  const [canal, setCanal] = useState("");
  const [elegidos, setElegidos] = useState<Set<number>>(new Set());
  const consulta = useVerificacion(estado);
  const confirmar = useConfirmarPagos();

  const pagos = useMemo(
    () => (consulta.data?.pagos ?? []).filter((p) => !canal || p.canal === canal),
    [consulta.data, canal],
  );
  const pendientes = estado === "pendiente";
  const seleccion = pagos.filter((p) => elegidos.has(p.id));

  function alternar(id: number) {
    setElegidos((actual) => {
      const nuevo = new Set(actual);
      if (nuevo.has(id)) nuevo.delete(id);
      else nuevo.add(id);
      return nuevo;
    });
  }

  async function confirmarSeleccion() {
    try {
      const r = await confirmar.mutateAsync({ pago_ids: seleccion.map((p) => p.id) });
      toast.success(`${r.confirmados} pago(s) confirmados contra el banco`);
      setElegidos(new Set());
    } catch (err) {
      const fallo = err instanceof FalloApi ? err : null;
      toast.error(fallo?.mensaje ?? "No se pudieron confirmar", {
        description: "No se confirmó ninguno: es todo o nada.",
      });
    }
  }

  return (
    <>
      <Titulo detalle="Compará cada abono contra la cuenta. Confirmar deja constancia de que la plata llegó; rechazar lo reversa y la deuda vuelve.">
        Confirmar pagos
      </Titulo>

      {consulta.data && Number(consulta.data.resumen.pendientes) > 0 && (
        <div className="mb-5">
          <Aviso tono="ambar" titulo={`${consulta.data.resumen.pendientes} pagos por confirmar`}>
            Suman <Dinero valor={consulta.data.resumen.pendientes_usd} />. Ya descuentan la deuda
            de cada cliente; lo que falta es verificar que llegaron.
          </Aviso>
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <Select value={estado} onChange={(e) => { setEstado(e.target.value); setElegidos(new Set()); }} className="w-44">
          <option value="pendiente">Por confirmar</option>
          <option value="confirmado">Confirmados</option>
          <option value="rechazado">Rechazados</option>
        </Select>
        <Select value={canal} onChange={(e) => setCanal(e.target.value)} className="w-44">
          <option value="">Todos los métodos</option>
          {Object.entries(CANAL).map(([valor, etiqueta]) => (
            <option key={valor} value={valor}>{etiqueta}</option>
          ))}
        </Select>
        {pendientes && seleccion.length > 0 && (
          <Boton onClick={confirmarSeleccion} disabled={confirmar.isPending}>
            <BadgeCheck className="size-4" />
            Confirmar {seleccion.length} · <Dinero valor={sumar(seleccion.map((p) => p.monto_usd)).toString()} />
          </Boton>
        )}
      </div>

      {consulta.isLoading ? (
        <Cargando que="Cargando pagos" />
      ) : pagos.length === 0 ? (
        <Vacio
          titulo={pendientes ? "No hay pagos por confirmar" : "No hay pagos en este estado"}
          detalle={pendientes ? "Todo lo registrado ya se verificó contra el banco." : undefined}
        />
      ) : (
        <Tabla>
          <thead>
            <tr>
              {pendientes && (
                <Th>
                  <input
                    type="checkbox"
                    aria-label="Elegir todos"
                    checked={seleccion.length === pagos.length}
                    onChange={(e) => setElegidos(e.target.checked ? new Set(pagos.map((p) => p.id)) : new Set())}
                  />
                </Th>
              )}
              <Th>Fecha</Th>
              <Th>Cliente</Th>
              <Th>Método</Th>
              <Th>Referencia</Th>
              <Th className="text-right">Recibido</Th>
              <Th className="text-right">Abona</Th>
              <Th>{pendientes ? "Registrado por" : "Verificado"}</Th>
              {pendientes && <Th />}
            </tr>
          </thead>
          <tbody>
            {pagos.map((p) => (
              <FilaPago key={p.id} pago={p} pendientes={pendientes} elegido={elegidos.has(p.id)} onElegir={() => alternar(p.id)} />
            ))}
          </tbody>
        </Tabla>
      )}
    </>
  );
}

function FilaPago({
  pago: p,
  pendientes,
  elegido,
  onElegir,
}: {
  pago: PagoAVerificar;
  pendientes: boolean;
  elegido: boolean;
  onElegir: () => void;
}) {
  return (
    <tr className={elegido ? "bg-acento-suave/40" : undefined}>
      {pendientes && (
        <Td>
          <input type="checkbox" checked={elegido} onChange={onElegir} aria-label={`Elegir el pago de ${p.cliente}`} />
        </Td>
      )}
      <Td className="whitespace-nowrap">{fecha(p.fecha)}</Td>
      <Td>
        <p className="font-medium">{p.cliente}</p>
        <p className="font-mono text-xs text-texto-suave">{p.venta}</p>
        {p.notas && <p className="mt-0.5 max-w-xs text-xs text-texto-suave" title={p.notas}>{p.notas.length > 90 ? `${p.notas.slice(0, 90)}…` : p.notas}</p>}
      </Td>
      <Td>{CANAL[p.canal ?? ""] ?? p.canal ?? "—"}</Td>
      <Td className="font-mono text-xs">{p.referencia ?? <span className="text-texto-suave">—</span>}</Td>
      <Td className="text-right">
        <Dinero valor={p.monto_moneda} moneda={p.moneda === "VES" ? "VES" : "USD"} />
      </Td>
      <Td className="text-right font-semibold"><Dinero valor={p.monto_usd} /></Td>
      <Td className="text-xs text-texto-suave">
        {pendientes ? (
          p.registrado_por ?? "Importación"
        ) : (
          <>
            <Insignia tono={p.estado === "confirmado" ? "ok" : "critico"}>{p.estado}</Insignia>
            <p className="mt-1">{p.verificado_por} · {p.verificado_at ? fechaHora(p.verificado_at) : ""}</p>
            {p.nota_verificacion && <p>{p.nota_verificacion}</p>}
          </>
        )}
      </Td>
      {pendientes && (
        <Td className="text-right">
          <Rechazar pago={p} />
        </Td>
      )}
    </tr>
  );
}

/** En dos pasos, como anular una venta: el primer clic solo abre el motivo. */
function Rechazar({ pago }: { pago: PagoAVerificar }) {
  const [abierto, setAbierto] = useState(false);
  const [motivo, setMotivo] = useState("");
  const rechazar = useRechazarPago();

  async function enviar() {
    try {
      await rechazar.mutateAsync({ id: pago.id, motivo: motivo.trim() });
      toast.success(`Pago de ${pago.cliente} rechazado`, {
        description: "Se reversó con su fecha y la deuda volvió a la venta.",
      });
      setAbierto(false);
    } catch (err) {
      toast.error(err instanceof FalloApi ? err.mensaje : "No se pudo rechazar");
    }
  }

  if (!abierto) {
    return (
      <button onClick={() => setAbierto(true)} className="text-xs text-texto-suave underline hover:text-critico">
        No llegó
      </button>
    );
  }
  return (
    <span className="flex items-center justify-end gap-1">
      <Input
        value={motivo}
        onChange={(e) => setMotivo(e.target.value)}
        placeholder="Motivo, ej. no aparece en el BNC"
        className="h-7 w-52 text-xs"
        autoFocus
      />
      <Boton onClick={enviar} disabled={motivo.trim().length < 5 || rechazar.isPending} className="px-2 py-1 text-xs">
        Rechazar
      </Boton>
      <button onClick={() => setAbierto(false)} aria-label="Cancelar" className="text-texto-suave">
        <X className="size-3" />
      </button>
    </span>
  );
}
