"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";
import { Check, Phone, PhoneOff } from "lucide-react";
import { Dinero } from "@/components/dinero";
import {
  Aviso,
  Boton,
  Cargando,
  Input,
  Insignia,
  Tabla,
  Td,
  Th,
  Titulo,
  Vacio,
} from "@/components/ui";
import { useClientes, useGuardarTelefono } from "@/hooks/datos";
import { FalloApi } from "@/lib/api";
import { contar, telefonoLegible } from "@/lib/formato";
import { tonoPorMora } from "@/lib/semaforo";
import type { Cliente } from "@/lib/tipos";

/**
 * Clientes, y sobre todo: la carga de teléfonos.
 *
 * Es la pantalla que desbloquea la cobranza por WhatsApp. Ninguna fuente del negocio
 * tenía un teléfono —ni la base, ni el Excel original, ni el auditado—, así que hasta
 * que estos 14 números se carguen no se puede reclamar nada. Por eso el teléfono se
 * edita en la propia fila y no en una ficha aparte: son catorce, se hacen de una
 * sentada.
 */
export default function PaginaClientes() {
  return (
    <Suspense fallback={<Cargando />}>
      <Clientes />
    </Suspense>
  );
}

function Clientes() {
  const params = useSearchParams();
  const [q, setQ] = useState("");
  const [soloSinTelefono, setSoloSinTelefono] = useState(
    params.get("sin_telefono") === "1",
  );
  const [soloConDeuda, setSoloConDeuda] = useState(params.get("con_deuda") === "1");

  const clientes = useClientes({
    q: q.trim() || undefined,
    sin_telefono: soloSinTelefono || undefined,
    con_deuda: soloConDeuda || undefined,
  });

  const filas = clientes.data ?? [];
  const pendientes = filas.filter((c) => !c.telefono_e164 && Number(c.deuda_usd) > 0);

  return (
    <>
      <Titulo detalle="Cargá un teléfono y ese cliente ya se puede notificar.">
        Clientes
      </Titulo>

      {pendientes.length > 0 && (
        <div className="mb-5">
          <Aviso
            tono="critico"
            titulo={`${contar(pendientes.length, "cliente")} con deuda y sin teléfono`}
          >
            Es lo único que falta para poder cobrarles por WhatsApp. Se edita en la
            misma fila.
          </Aviso>
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Input
          placeholder="Buscar por nombre o alias…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="max-w-xs"
        />
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={soloSinTelefono}
            onChange={(e) => setSoloSinTelefono(e.target.checked)}
          />
          Sin teléfono
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={soloConDeuda}
            onChange={(e) => setSoloConDeuda(e.target.checked)}
          />
          Con deuda
        </label>
      </div>

      {clientes.isLoading ? (
        <Cargando que="Cargando clientes" />
      ) : filas.length === 0 ? (
        <Vacio titulo="Ningún cliente coincide" />
      ) : (
        <Tabla>
          <thead>
            <tr>
              <Th>Cliente</Th>
              <Th>Teléfono</Th>
              <Th className="text-right">Deuda</Th>
              <Th className="text-right">Atraso</Th>
              <Th className="text-right">Compras</Th>
              <Th>Notas</Th>
            </tr>
          </thead>
          <tbody>
            {filas.map((c) => (
              <FilaCliente key={c.id} cliente={c} />
            ))}
          </tbody>
        </Tabla>
      )}
    </>
  );
}

function FilaCliente({ cliente: c }: { cliente: Cliente }) {
  const [editando, setEditando] = useState(false);
  const [valor, setValor] = useState("");
  const guardar = useGuardarTelefono();

  async function onGuardar() {
    try {
      const r = await guardar.mutateAsync({ id: c.id, telefono: valor });
      toast.success(`${c.nombre} ya se puede notificar`, {
        description: telefonoLegible(
          (r as { telefono_e164?: string } | undefined)?.telefono_e164 ?? valor,
        ),
      });
      setEditando(false);
      setValor("");
    } catch (err) {
      const fallo = err instanceof FalloApi ? err : null;
      toast.error(fallo?.mensaje ?? "No se pudo guardar", {
        description: fallo?.sugerencia,
      });
    }
  }

  const deuda = Number(c.deuda_usd);

  return (
    <tr className="hover:bg-fondo/60">
      <Td>
        <div className="flex items-center gap-2">
          <span className="font-medium">{c.nombre}</span>
          {c.es_socio && <Insignia tono="marca">socio</Insignia>}
        </div>
        {c.alias && c.alias.length > 1 && (
          <span
            className="text-xs text-texto-suave"
            title="Grafías con las que aparece en el histórico"
          >
            {c.alias.join(" · ")}
          </span>
        )}
      </Td>

      <Td>
        {editando ? (
          <div className="flex items-center gap-2">
            <Input
              autoFocus
              placeholder="0412-1234567"
              value={valor}
              onChange={(e) => setValor(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") onGuardar();
                if (e.key === "Escape") setEditando(false);
              }}
              className="w-36"
            />
            <Boton
              onClick={onGuardar}
              disabled={guardar.isPending || valor.length < 7}
              className="px-2 py-1"
            >
              <Check className="size-4" />
            </Boton>
          </div>
        ) : c.telefono_e164 ? (
          <button
            onClick={() => {
              setValor(telefonoLegible(c.telefono_e164));
              setEditando(true);
            }}
            className="flex items-center gap-1 text-xs tabular hover:underline"
          >
            <Phone className="size-3 text-ok" />
            {telefonoLegible(c.telefono_e164)}
          </button>
        ) : (
          <button
            onClick={() => setEditando(true)}
            className="flex items-center gap-1"
            title="Cargar el teléfono"
          >
            <Insignia tono={deuda > 0 ? "critico" : "neutro"}>
              <PhoneOff className="size-3" />
              cargar
            </Insignia>
          </button>
        )}
      </Td>

      <Td className="text-right">
        {deuda > 0 ? <Dinero valor={c.deuda_usd} /> : <span className="text-texto-suave">—</span>}
      </Td>
      <Td className="text-right">
        {c.dias_mora_maximo > 0 ? (
          <Insignia tono={tonoPorMora(c.dias_mora_maximo)}>
            {c.dias_mora_maximo} d
          </Insignia>
        ) : (
          <span className="text-texto-suave">—</span>
        )}
      </Td>
      <Td className="text-right tabular">{c.compras}</Td>
      <Td className="max-w-xs text-xs text-texto-suave">
        {c.notas && (
          <span title={c.notas}>
            {c.notas.length > 60 ? `${c.notas.slice(0, 60)}…` : c.notas}
          </span>
        )}
      </Td>
    </tr>
  );
}
