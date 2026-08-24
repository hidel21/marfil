"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";
import { Cargando, Tarjeta, Titulo, Vacio } from "@/components/ui";
import { usePrevisualizarLote } from "@/hooks/datos";
import { Dinero } from "@/components/dinero";

/** El lote de una selección concreta, desde la pantalla de cobranza. */
export default function PaginaLote() {
  return (
    <Suspense fallback={<Cargando />}>
      <Lote />
    </Suspense>
  );
}

function Lote() {
  const params = useSearchParams();
  const ids = (params.get("clientes") ?? "")
    .split(",")
    .map(Number)
    .filter(Boolean);
  const previsualizar = usePrevisualizarLote();

  useEffect(() => {
    if (ids.length > 0) previsualizar.mutate({ cliente_ids: ids });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.get("clientes")]);

  const lote = previsualizar.data;

  return (
    <>
      <Titulo detalle="Cada mensaje va con los números de ese cliente.">
        Recordatorios del lote
      </Titulo>

      {previsualizar.isPending && <Cargando que="Armando los mensajes" />}
      {lote && (
        <>
          <p className="mb-4 text-sm text-texto-suave">{lote.resumen}</p>
          <div className="space-y-3">
            {lote.preparados.map((p) => (
              <Tarjeta key={p.cliente_id}>
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <p className="font-medium">{p.cliente}</p>
                  <p className="text-xs text-texto-suave">
                    <Dinero valor={p.deuda_usd} /> · {p.dias_mora} d
                  </p>
                </div>
                <pre className="max-h-48 overflow-y-auto rounded-lg bg-fondo p-3 text-xs whitespace-pre-wrap">
                  {p.cuerpo}
                </pre>
                {p.accion.url && (
                  <a
                    href={p.accion.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-2 inline-block text-sm text-marca underline"
                  >
                    Abrir en WhatsApp
                  </a>
                )}
              </Tarjeta>
            ))}
          </div>
        </>
      )}
      {ids.length === 0 && (
        <Vacio
          titulo="Sin clientes elegidos"
          detalle="Volvé a cobranza y elegí a quiénes avisarle."
        />
      )}
    </>
  );
}
