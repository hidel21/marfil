"use client";

import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { Check, Copy, ExternalLink, MessageSquare, PhoneOff } from "lucide-react";
import { Dinero } from "@/components/dinero";
import {
  Aviso,
  Boton,
  Insignia,
  Tarjeta,
  Titulo,
  Vacio,
} from "@/components/ui";
import {
  useDatosPago,
  useGenerarLote,
  usePrevisualizarLote,
} from "@/hooks/datos";
import { FalloApi } from "@/lib/api";
import { contar } from "@/lib/formato";
import type { Preparado } from "@/lib/tipos";

/**
 * Recordatorios de WhatsApp.
 *
 * No hay integración con la API de WhatsApp, así que el sistema arma el mensaje y un
 * link `wa.me` **con el número del cliente** que se abre con un clic. La app anterior
 * generaba `wa.me/?text=` sin destinatario, así que abría WhatsApp sin saber a quién
 * escribirle.
 *
 * Un deep link no puede confirmar entrega, y la pantalla lo dice: el estado se llama
 * "entregado a WhatsApp" y se marca cuando la persona vuelve. Mentir sobre eso haría
 * inútil el historial.
 */
export default function Recordatorios() {
  const datosPago = useDatosPago();
  const previsualizar = usePrevisualizarLote();
  const generar = useGenerarLote();
  const [enviados, setEnviados] = useState<Set<number>>(new Set());

  const lote = previsualizar.data ?? generar.data ?? null;
  const bloqueado = datosPago.data && !datosPago.data.completo;

  async function cargar() {
    try {
      await previsualizar.mutateAsync({});
    } catch (err) {
      const fallo = err instanceof FalloApi ? err : null;
      toast.error(fallo?.mensaje ?? "No se pudo armar el lote", {
        description: fallo?.sugerencia,
      });
    }
  }

  return (
    <>
      <Titulo
        detalle="El sistema arma el mensaje; el envío lo hace una persona con un clic."
        accion={
          <Boton onClick={cargar} disabled={Boolean(bloqueado) || previsualizar.isPending}>
            <MessageSquare className="size-4" />
            {previsualizar.isPending ? "Armando…" : "Armar los recordatorios"}
          </Boton>
        }
      >
        Recordatorios
      </Titulo>

      {bloqueado && (
        <div className="mb-5">
          <Aviso
            tono="critico"
            titulo="Faltan los datos de pago"
            accion={
              <Link href="/ajustes/pagos">
                <Boton variante="secundario">Completarlos</Boton>
              </Link>
            }
          >
            Falta {datosPago.data?.faltantes.join(", ")}. Sin ellos no se puede{" "}
            <strong>generar</strong> ningún recordatorio, no solo enviarlo: un mensaje de
            cobro sin datos de cobro no sirve, y uno con datos de relleno es peor.
          </Aviso>
        </div>
      )}

      {lote && (
        <>
          <p className="mb-4 text-sm text-texto-suave">{lote.resumen}</p>

          {lote.omitidos.length > 0 && (
            <Tarjeta className="mb-4">
              <p className="mb-2 text-sm font-medium">
                {contar(lote.omitidos.length, "omitido")}
              </p>
              <ul className="space-y-1 text-sm">
                {lote.omitidos.map((o) => (
                  <li
                    key={`${o.cliente_id}-${o.motivo}`}
                    className="flex flex-wrap items-center gap-2"
                  >
                    <Insignia tono={o.motivo === "sin_telefono" ? "critico" : "neutro"}>
                      {o.motivo === "sin_telefono" ? (
                        <PhoneOff className="size-3" />
                      ) : null}
                      {o.motivo.replace("_", " ")}
                    </Insignia>
                    <span className="font-medium">{o.cliente}</span>
                    <span className="text-texto-suave">{o.detalle}</span>
                    {o.motivo === "sin_telefono" && (
                      <Link
                        href="/clientes?sin_telefono=1&con_deuda=1"
                        className="text-marca underline"
                      >
                        cargar teléfono
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
            </Tarjeta>
          )}

          {lote.preparados.length === 0 ? (
            <Vacio
              titulo="No hay recordatorios para enviar"
              detalle="Puede ser que nadie esté vencido, o que a quienes lo están les falte el teléfono."
            />
          ) : (
            <>
              <div className="mb-4 flex items-center gap-3">
                <Boton
                  onClick={async () => {
                    await generar.mutateAsync({});
                    toast.success("Recordatorios registrados", {
                      description: "Quedan en el historial con el mensaje congelado.",
                    });
                  }}
                  disabled={generar.isPending}
                >
                  Registrar {contar(lote.preparados.length, "recordatorio")}
                </Boton>
                <span className="text-xs text-texto-suave">
                  Registrarlos guarda el mensaje tal como se envió, para poder probarlo
                  después.
                </span>
              </div>

              <div className="space-y-3">
                {lote.preparados.map((p) => (
                  <TarjetaRecordatorio
                    key={p.cliente_id}
                    preparado={p}
                    enviado={enviados.has(p.cliente_id)}
                    onEnviado={() =>
                      setEnviados((s) => new Set(s).add(p.cliente_id))
                    }
                  />
                ))}
              </div>
            </>
          )}
        </>
      )}

      {!lote && !bloqueado && (
        <Vacio
          titulo="Armá los recordatorios del día"
          detalle="El sistema elige la plantilla según los días de atraso de cada cliente."
        />
      )}
    </>
  );
}

function TarjetaRecordatorio({
  preparado: p,
  enviado,
  onEnviado,
}: {
  preparado: Preparado;
  enviado: boolean;
  onEnviado: () => void;
}) {
  return (
    <Tarjeta>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-medium">{p.cliente}</p>
          <p className="text-xs text-texto-suave">
            <Dinero valor={p.deuda_usd} /> · {p.dias_mora} días de atraso ·{" "}
            {p.plantilla_clave.replace("recordatorio_", "")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {enviado && (
            <Insignia tono="ok">
              <Check className="size-3" />
              entregado a WhatsApp
            </Insignia>
          )}
          <Boton
            variante="secundario"
            onClick={() => {
              navigator.clipboard.writeText(p.cuerpo).then(
                () => toast.success("Mensaje copiado"),
                () => toast.error("No se pudo copiar"),
              );
            }}
          >
            <Copy className="size-4" />
            Copiar
          </Boton>
          {p.accion.tipo === "DEEP_LINK" && p.accion.url ? (
            <a href={p.accion.url} target="_blank" rel="noopener noreferrer">
              <Boton onClick={onEnviado}>
                <ExternalLink className="size-4" />
                Abrir en WhatsApp
              </Boton>
            </a>
          ) : (
            <Boton disabled>Enviar</Boton>
          )}
        </div>
      </div>

      <pre className="max-h-56 overflow-y-auto rounded-lg bg-fondo p-3 text-xs whitespace-pre-wrap">
        {p.cuerpo}
      </pre>

      {p.avisos.map((a) => (
        <p key={a} className="mt-2 text-xs text-texto-suave">
          {a}
        </p>
      ))}
    </Tarjeta>
  );
}
