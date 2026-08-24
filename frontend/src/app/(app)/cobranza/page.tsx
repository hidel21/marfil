"use client";

import clsx from "clsx";
import Link from "next/link";
import { useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  MessageSquare,
  PhoneOff,
  Send,
} from "lucide-react";
import { Dinero } from "@/components/dinero";
import {
  Aviso,
  Boton,
  Cargando,
  Insignia,
  Tabla,
  Tarjeta,
  Td,
  Th,
  Titulo,
  Vacio,
} from "@/components/ui";
import { useCobranza, useResumenCobranza } from "@/hooks/datos";
import { contar, fechaCorta, relativo, telefonoLegible } from "@/lib/formato";
import {
  ETIQUETA_SEMAFORO,
  EXPLICACION_SEMAFORO,
  TONO_SEMAFORO,
} from "@/lib/semaforo";
import type { ClienteEnCobranza } from "@/lib/tipos";

/**
 * Cobranza.
 *
 * Va por CLIENTE y no por venta: el recordatorio se le manda a una persona, y las 18
 * ventas abiertas son 14 personas. Mandarle a alguien cuatro mensajes separados por
 * sus cuatro ventas es cómo se pierde un cliente.
 *
 * Los filtros viven en el estado de la página y no en la URL todavía; cuando haga
 * falta compartir un corte por WhatsApp, pasan a query string.
 */
export default function Cobranza() {
  const [tramo, setTramo] = useState<string | undefined>();
  const [soloSinAbonos, setSoloSinAbonos] = useState(false);
  const [incluirSocios, setIncluirSocios] = useState(false);
  const [expandido, setExpandido] = useState<number | null>(null);
  const [elegidos, setElegidos] = useState<Set<number>>(new Set());

  const resumen = useResumenCobranza();
  const clientes = useCobranza({
    tramo,
    sin_abonos: soloSinAbonos || undefined,
    incluir_socios: incluirSocios,
  });

  const alternar = (id: number) =>
    setElegidos((prev) => {
      const siguiente = new Set(prev);
      if (siguiente.has(id)) siguiente.delete(id);
      else siguiente.add(id);
      return siguiente;
    });

  const filas = clientes.data ?? [];
  const notificables = filas.filter((c) => c.puede_notificar);
  const sinTelefono = filas.filter((c) => !c.puede_notificar);

  return (
    <>
      <Titulo detalle="Quién debe, desde cuándo, y cómo avisarle.">Cobranza</Titulo>

      {/* Las métricas. Cada una trae su definición: un número sin definición no se
          puede auditar. */}
      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-3">
        {(resumen.data?.metricas ?? []).map((m) => (
          <Tarjeta key={m.clave}>
            <p className="text-xs text-texto-suave">{m.etiqueta}</p>
            <p className="mt-1 text-2xl font-semibold tabular">
              {m.es_monto ? <Dinero valor={m.valor} /> : m.valor}
            </p>
            <p className="mt-1 text-xs text-texto-suave" title={m.definicion}>
              {m.definicion.length > 46
                ? `${m.definicion.slice(0, 46)}…`
                : m.definicion}
            </p>
          </Tarjeta>
        ))}
      </div>

      {/* El bloqueo real de la cobranza: sin teléfono no hay a quién escribirle. */}
      {sinTelefono.length > 0 && (
        <div className="mb-5">
          <Aviso
            tono="critico"
            titulo={`${contar(sinTelefono.length, "deudor", "deudores")} sin teléfono`}
            accion={
              <Link href="/clientes?sin_telefono=1&con_deuda=1">
                <Boton variante="secundario">Cargar teléfonos</Boton>
              </Link>
            }
          >
            Deben{" "}
            <Dinero
              valor={sinTelefono
                .reduce((a, c) => a + Number(c.deuda_usd), 0)
                .toFixed(2)}
            />{" "}
            y no hay forma de avisarles. Es lo primero que conviene resolver.
          </Aviso>
        </div>
      )}

      {/* Tramos de antigüedad: clicables, son un filtro y no una página aparte. */}
      <div className="mb-4 flex flex-wrap gap-2">
        <button
          onClick={() => setTramo(undefined)}
          className={clsx(
            "rounded-lg border px-3 py-2 text-sm",
            !tramo ? "border-marca bg-marca-suave text-marca" : "border-borde",
          )}
        >
          Todos
        </button>
        {(resumen.data?.tramos ?? [])
          .filter((t) => t.cantidad > 0)
          .map((t) => (
            <button
              key={t.clave}
              onClick={() => setTramo(t.clave === tramo ? undefined : t.clave)}
              className={clsx(
                "rounded-lg border px-3 py-2 text-left text-sm",
                t.clave === tramo
                  ? "border-marca bg-marca-suave text-marca"
                  : "border-borde",
              )}
            >
              <span className="block">{t.etiqueta}</span>
              <span className="block text-xs text-texto-suave">
                {t.cantidad} · <Dinero valor={t.monto_usd} />
              </span>
            </button>
          ))}
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-4 text-sm">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={soloSinAbonos}
            onChange={(e) => setSoloSinAbonos(e.target.checked)}
          />
          {/* El criterio viejo sobrevive como faceta: "nunca abonó" es un riesgo
              distinto de "abonó dos veces y se detuvo". */}
          <span title="El criterio de la app anterior, ahora como filtro y no como estado.">
            Solo los que nunca abonaron
          </span>
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={incluirSocios}
            onChange={(e) => setIncluirSocios(e.target.checked)}
          />
          <span title="Los socios comprando para sí mismos no son ingreso real.">
            Incluir autoconsumo de socios
          </span>
        </label>

        {elegidos.size > 0 && (
          <Link
            href={`/recordatorios/lote?clientes=${[...elegidos].join(",")}`}
            className="ml-auto"
          >
            <Boton>
              <MessageSquare className="size-4" />
              Generar {contar(elegidos.size, "recordatorio")}
            </Boton>
          </Link>
        )}
      </div>

      {clientes.isLoading ? (
        <Cargando que="Cargando la cobranza" />
      ) : filas.length === 0 ? (
        <Vacio
          titulo="Nadie debe nada en este filtro"
          detalle="Probá con otro tramo de antigüedad."
        />
      ) : (
        <Tabla>
          <thead>
            <tr>
              <Th className="w-8">
                <input
                  type="checkbox"
                  aria-label="Elegir todos los notificables"
                  checked={
                    notificables.length > 0 && elegidos.size === notificables.length
                  }
                  onChange={(e) =>
                    setElegidos(
                      e.target.checked
                        ? new Set(notificables.map((c) => c.cliente_id))
                        : new Set(),
                    )
                  }
                />
              </Th>
              <Th>Cliente</Th>
              <Th className="text-right">Deuda</Th>
              <Th className="text-right">Atraso</Th>
              <Th>Estado</Th>
              <Th>Teléfono</Th>
              <Th>Último abono</Th>
              <Th>Último aviso</Th>
              <Th className="w-8" />
            </tr>
          </thead>
          <tbody>
            {filas.map((c) => (
              <FilaCliente
                key={c.cliente_id}
                cliente={c}
                elegido={elegidos.has(c.cliente_id)}
                onElegir={() => alternar(c.cliente_id)}
                abierto={expandido === c.cliente_id}
                onAbrir={() =>
                  setExpandido(expandido === c.cliente_id ? null : c.cliente_id)
                }
              />
            ))}
          </tbody>
        </Tabla>
      )}
    </>
  );
}

function FilaCliente({
  cliente: c,
  elegido,
  onElegir,
  abierto,
  onAbrir,
}: {
  cliente: ClienteEnCobranza;
  elegido: boolean;
  onElegir: () => void;
  abierto: boolean;
  onAbrir: () => void;
}) {
  return (
    <>
      <tr className="hover:bg-fondo/60">
        <Td>
          <input
            type="checkbox"
            checked={elegido}
            onChange={onElegir}
            disabled={!c.puede_notificar}
            title={
              c.puede_notificar
                ? undefined
                : "Sin teléfono no se le puede enviar un recordatorio"
            }
          />
        </Td>
        <Td>
          <div className="flex items-center gap-2">
            <span className="font-medium">{c.cliente}</span>
            {c.es_socio && <Insignia tono="marca">socio</Insignia>}
            {c.nunca_abono && (
              <Insignia tono="ambar" titulo="Nunca hizo un abono">
                sin abonos
              </Insignia>
            )}
          </div>
          <span className="text-xs text-texto-suave">
            {contar(c.ventas_abiertas, "venta")}
            {c.vendedor && ` · ${c.vendedor}`}
          </span>
        </Td>
        <Td className="text-right font-medium">
          <Dinero valor={c.deuda_usd} />
        </Td>
        <Td className="text-right tabular">
          {c.dias_mora_maximo > 0 ? `${c.dias_mora_maximo} d` : "—"}
        </Td>
        <Td>
          <Insignia
            tono={TONO_SEMAFORO[c.semaforo]}
            titulo={EXPLICACION_SEMAFORO[c.semaforo]}
          >
            {ETIQUETA_SEMAFORO[c.semaforo]}
          </Insignia>
        </Td>
        <Td>
          {c.puede_notificar ? (
            <span className="tabular text-xs">
              {telefonoLegible(c.telefono_e164)}
            </span>
          ) : (
            <Link href={`/clientes?sin_telefono=1&con_deuda=1`}>
              <Insignia tono="critico">
                <PhoneOff className="size-3" />
                sin teléfono
              </Insignia>
            </Link>
          )}
        </Td>
        <Td className="text-xs text-texto-suave">{relativo(c.ultimo_abono_fecha)}</Td>
        <Td className="text-xs text-texto-suave">
          {relativo(c.ultimo_recordatorio_at)}
        </Td>
        <Td>
          <button
            onClick={onAbrir}
            className="rounded p-1 hover:bg-fondo"
            aria-label={abierto ? "Cerrar detalle" : "Ver ventas"}
          >
            {abierto ? (
              <ChevronDown className="size-4" />
            ) : (
              <ChevronRight className="size-4" />
            )}
          </button>
        </Td>
      </tr>

      {abierto && (
        <tr>
          <Td className="bg-fondo/40" />
          <Td className="bg-fondo/40" colSpan={8}>
            <div className="space-y-1 py-1">
              {c.ventas.map((v) => (
                <div
                  key={v.venta_id}
                  className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs"
                >
                  <span className="font-mono">{v.codigo}</span>
                  <span className="min-w-0 flex-1 truncate">
                    {v.producto ?? "—"}
                  </span>
                  <span className="tabular">
                    <Dinero valor={v.saldo_usd} /> de{" "}
                    <Dinero valor={v.total_usd} />
                  </span>
                  <span className="text-texto-suave">
                    vence {fechaCorta(v.fecha_vencimiento)}
                    {v.dias_mora > 0 && ` (${v.dias_mora} d)`}
                  </span>
                  <Insignia tono={TONO_SEMAFORO[v.semaforo]}>
                    {ETIQUETA_SEMAFORO[v.semaforo]}
                  </Insignia>
                  <Link
                    href={`/abonos/nuevo?venta=${v.venta_id}`}
                    className="text-marca underline"
                  >
                    <Send className="mr-1 inline size-3" />
                    Registrar abono
                  </Link>
                </div>
              ))}
            </div>
          </Td>
        </tr>
      )}
    </>
  );
}
