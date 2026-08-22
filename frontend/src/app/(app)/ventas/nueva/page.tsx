"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Plus, ShieldAlert, Trash2, TriangleAlert } from "lucide-react";
import { ComboboxProducto } from "@/components/combobox-producto";
import { Dinero } from "@/components/dinero";
import {
  Aviso,
  Boton,
  Campo,
  Cargando,
  Input,
  Insignia,
  Select,
  Tarjeta,
  Titulo,
} from "@/components/ui";
import { useClientes, useCotizar, useCrearVenta } from "@/hooks/datos";
import { useSesion } from "@/hooks/sesion";
import { FalloApi } from "@/lib/api";
import { d, plano, usd } from "@/lib/dinero";
import { fecha } from "@/lib/formato";
import type { Cotizacion, LineaCotizada } from "@/lib/tipos";

/**
 * Registrar venta.
 *
 * Acá se corta la fuga de precio. La causa era estructural, no humana: la app anterior
 * fijaba `moneda = 'BCV'` a mano mientras el precio venía de
 * `max(precio_bcv, precio_divisa)`, así que el nivel declarado y el precio cobrado los
 * calculaban dos expresiones que nunca se encontraban. El informe midió $123 perdidos
 * en 56 días —26 % de la ganancia— por eso.
 *
 * El nivel de precio es un control **obligatorio y sin valor por defecto**, y es el
 * que manda: define el precio sugerido en vez de que se elija de memoria. La
 * evaluación la hace el backend en cada cambio, así que la pantalla nunca puede
 * mostrar un número que la API acepte distinto.
 */

type Linea = {
  producto_id: number;
  nombre: string;
  cantidad: number;
  precio: string;
  motivo?: string;
};

const MONEDAS = [
  { valor: "VES", etiqueta: "Tasa BCV (+120 % sobre el costo)" },
  { valor: "USD", etiqueta: "Divisa / USDT (+70 % sobre el costo)" },
];

export default function NuevaVenta() {
  const router = useRouter();
  const { yo } = useSesion();
  const hoy = new Date().toISOString().slice(0, 10);

  const [clienteId, setClienteId] = useState<number | null>(null);
  const [fechaVenta, setFechaVenta] = useState(hoy);
  const [moneda, setMoneda] = useState<string>("");
  const [lineas, setLineas] = useState<Linea[]>([]);
  const [permitirSobreventa, setPermitirSobreventa] = useState(false);

  const clientes = useClientes();
  const cotizar = useCotizar();
  const crear = useCrearVenta();
  const [resultadoCotizacion, setResultadoCotizacion] = useState<{
    firma: string;
    valor: Cotizacion;
  } | null>(null);

  const cuerpo = useMemo(
    () => ({
      cliente_id: clienteId,
      fecha: fechaVenta,
      moneda_cotizacion: moneda,
      permitir_sobreventa: permitirSobreventa,
      autorizaciones: Object.fromEntries(
        lineas.map((l, i) => [i, l.motivo]).filter(([, m]) => Boolean(m)),
      ),
      lineas: lineas.map((l) => ({
        producto_id: l.producto_id,
        cantidad: l.cantidad,
        precio_unitario_usd: l.precio || "0",
      })),
    }),
    [clienteId, fechaVenta, moneda, lineas, permitirSobreventa],
  );

  const listoParaCotizar = Boolean(clienteId && moneda && lineas.length > 0);
  const firmaCuerpo = JSON.stringify(cuerpo);
  const cotizacion =
    listoParaCotizar && resultadoCotizacion?.firma === firmaCuerpo
      ? resultadoCotizacion.valor
      : null;

  // Se cotiza contra el backend en cada cambio: es la misma función que valida al
  // guardar, así que lo que se ve es lo que se va a aceptar.
  useEffect(() => {
    if (!listoParaCotizar) return;
    const t = setTimeout(() => {
      cotizar.mutate(cuerpo, {
        onSuccess: (valor) => setResultadoCotizacion({ firma: firmaCuerpo, valor }),
        onError: () =>
          setResultadoCotizacion((anterior) =>
            anterior?.firma === firmaCuerpo ? null : anterior,
          ),
      });
    }, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firmaCuerpo, listoParaCotizar]);

  function agregar(p: { producto_id: number; nombre: string; precio_politica_usd: string | null }) {
    setLineas((prev) => [
      ...prev,
      {
        producto_id: p.producto_id,
        nombre: p.nombre,
        cantidad: 1,
        // Se prefila con el precio de política: es el punto, que no se elija de memoria.
        precio: p.precio_politica_usd ? plano(p.precio_politica_usd) : "",
      },
    ]);
  }

  function actualizar(i: number, cambios: Partial<Linea>) {
    setLineas((prev) => prev.map((l, j) => (j === i ? { ...l, ...cambios } : l)));
  }

  async function guardar() {
    try {
      const r = await crear.mutateAsync(cuerpo);
      toast.success(`Venta ${r.codigo as string} registrada`, {
        description: `Total ${usd(r.total_usd as string)} · vence ${fecha(
          r.fecha_vencimiento as string,
        )}`,
      });
      router.push("/cobranza");
    } catch (err) {
      const fallo = err instanceof FalloApi ? err : null;
      toast.error(fallo?.mensaje ?? "No se pudo registrar la venta", {
        description: fallo?.sugerencia,
      });
    }
  }

  return (
    <>
      <Titulo detalle="El nivel de precio define el precio sugerido. Es obligatorio.">
        Registrar venta
      </Titulo>

      <div className="grid gap-5 lg:grid-cols-[1fr_20rem]">
        <div className="space-y-4">
          <Tarjeta className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Campo etiqueta="Cliente" requerido>
                <Select
                  value={clienteId ?? ""}
                  onChange={(e) => setClienteId(Number(e.target.value) || null)}
                >
                  <option value="">Elegí un cliente…</option>
                  {(clientes.data ?? []).map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.nombre}
                      {Number(c.deuda_usd) > 0 && ` — debe ${usd(c.deuda_usd)}`}
                    </option>
                  ))}
                </Select>
              </Campo>

              <Campo etiqueta="Fecha" requerido>
                <Input
                  type="date"
                  value={fechaVenta}
                  max={hoy}
                  onChange={(e) => setFechaVenta(e.target.value)}
                />
              </Campo>
            </div>

            {/* El cliente muestra su deuda ANTES de venderle: ninguna pantalla lo
                hacía, y es lo que evita seguir dando crédito a quien ya debe. */}
            {clienteId != null &&
              (() => {
                const c = (clientes.data ?? []).find((x) => x.id === clienteId);
                if (!c || Number(c.deuda_usd) <= 0) return null;
                return (
                  <Aviso tono="ambar" titulo={`${c.nombre} ya debe ${usd(c.deuda_usd)}`}>
                    {c.ventas_abiertas} venta(s) abierta(s)
                    {c.dias_mora_maximo > 0 &&
                      `, la más atrasada hace ${c.dias_mora_maximo} días`}
                    .
                  </Aviso>
                );
              })()}

            <Campo
              etiqueta="Nivel de precio"
              requerido
              ayuda="La ganancia se mide sobre el costo, no sobre el precio de venta."
            >
              <div className="flex flex-wrap gap-2">
                {MONEDAS.map((m) => (
                  <button
                    key={m.valor}
                    type="button"
                    onClick={() => setMoneda(m.valor)}
                    className={
                      moneda === m.valor
                        ? "rounded-lg border border-marca bg-marca-suave px-3 py-2 text-sm text-marca"
                        : "rounded-lg border border-borde px-3 py-2 text-sm"
                    }
                  >
                    {m.etiqueta}
                  </button>
                ))}
              </div>
            </Campo>
          </Tarjeta>

          <Tarjeta className="space-y-3">
            <p className="text-sm font-medium">Productos</p>
            <ComboboxProducto moneda={moneda || "VES"} onElegir={agregar} />

            {lineas.length === 0 && (
              <p className="text-sm text-texto-suave">
                Escribí el nombre. Si no está en el catálogo, se puede crear ahí mismo:
                registrar la venta nunca se bloquea.
              </p>
            )}

            {lineas.map((l, i) => {
              const cotizada = cotizacion?.lineas.find((x) => x.indice === i);
              return (
                <LineaVenta
                  key={i}
                  linea={l}
                  cotizada={cotizada}
                  esAdmin={yo?.rol === "admin"}
                  onCambiar={(c) => actualizar(i, c)}
                  onQuitar={() =>
                    setLineas((prev) => prev.filter((_, j) => j !== i))
                  }
                />
              );
            })}

            {lineas.length > 0 && (
              <button
                type="button"
                onClick={() => document.querySelector<HTMLInputElement>("input[placeholder^='Escribí']")?.focus()}
                className="flex items-center gap-1 text-sm text-marca"
              >
                <Plus className="size-4" />
                Agregar otro producto
              </button>
            )}
          </Tarjeta>
        </div>

        <div className="space-y-4 lg:sticky lg:top-6 lg:self-start">
          <Tarjeta>
            <p className="mb-3 text-sm font-medium">Resumen</p>
            {!listoParaCotizar ? (
              <p className="text-sm text-texto-suave">
                Elegí cliente, nivel de precio y al menos un producto.
              </p>
            ) : cotizar.isPending && !cotizacion ? (
              <Cargando que="Calculando" />
            ) : cotizacion ? (
              <dl className="space-y-2 text-sm">
                <Fila etiqueta="Total">
                  <Dinero valor={cotizacion.total_usd} className="font-semibold" />
                </Fila>
                {yo?.ve_costos && (
                  <>
                    <Fila etiqueta="Costo">
                      <Dinero valor={cotizacion.costo_usd} />
                    </Fila>
                    <Fila etiqueta="Ganancia">
                      <Dinero valor={cotizacion.ganancia_usd} />
                    </Fila>
                  </>
                )}
                <Fila etiqueta="Plazo">{cotizacion.plazo_dias} días</Fila>
                <Fila etiqueta="Vence">{fecha(cotizacion.fecha_vencimiento)}</Fila>
              </dl>
            ) : null}

            {cotizacion?.lineas.some((l) => l.sobreventa) && (
              <label className="mt-4 flex items-start gap-2 rounded-lg bg-ambar-suave p-2 text-xs text-ambar">
                <input
                  type="checkbox"
                  checked={permitirSobreventa}
                  onChange={(e) => setPermitirSobreventa(e.target.checked)}
                  className="mt-0.5"
                />
                <span>
                  Venta sobre pedido: el stock puede quedar en negativo. Es más honesto
                  que no poder registrar la venta.
                </span>
              </label>
            )}

            <Boton
              onClick={guardar}
              disabled={
                !listoParaCotizar ||
                !cotizacion ||
                cotizacion.bloqueada ||
                crear.isPending
              }
              className="mt-4 w-full"
            >
              {crear.isPending ? "Guardando…" : "Registrar venta"}
            </Boton>

            {cotizacion?.bloqueada && (
              <p className="mt-2 text-xs text-critico">
                Resolvé los avisos de precio antes de guardar.
              </p>
            )}
          </Tarjeta>
        </div>
      </div>
    </>
  );
}

function Fila({ etiqueta, children }: { etiqueta: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-texto-suave">{etiqueta}</dt>
      <dd>{children}</dd>
    </div>
  );
}

/**
 * Una línea, con el guardia de precio.
 *
 * El panel ámbar ofrece las tres salidas y **exige elegir una**: cobrar el precio de
 * política, cambiar el nivel (que es la resolución correcta y hace que el registro sea
 * honesto), o cobrar menos con un motivo escrito. Nada se prohíbe; lo que no se puede
 * es hacerlo en silencio.
 */
function LineaVenta({
  linea,
  cotizada,
  esAdmin,
  onCambiar,
  onQuitar,
}: {
  linea: Linea;
  cotizada: LineaCotizada | undefined;
  esAdmin: boolean;
  onCambiar: (c: Partial<Linea>) => void;
  onQuitar: () => void;
}) {
  const bloqueantes = (cotizada?.advertencias ?? []).filter((a) => a.bloqueante);
  const avisos = (cotizada?.advertencias ?? []).filter((a) => !a.bloqueante);

  return (
    <div className="rounded-lg border border-borde p-3">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{linea.nombre}</p>
          {cotizada && (
            <p className="text-xs text-texto-suave">
              stock {cotizada.stock_actual} → {cotizada.stock_resultante}
              {cotizada.precio_politica_usd && (
                <> · política {usd(cotizada.precio_politica_usd)}</>
              )}
            </p>
          )}
        </div>

        <label className="w-20">
          <span className="mb-1 block text-xs text-texto-suave">Cantidad</span>
          <Input
            type="number"
            min={1}
            value={linea.cantidad}
            onChange={(e) => onCambiar({ cantidad: Math.max(1, Number(e.target.value)) })}
          />
        </label>

        <label className="w-28">
          <span className="mb-1 block text-xs text-texto-suave">Precio USD</span>
          <Input
            type="number"
            step="0.01"
            min={0}
            value={linea.precio}
            onChange={(e) => onCambiar({ precio: e.target.value })}
          />
        </label>

        <div className="w-24 text-right">
          <span className="mb-1 block text-xs text-texto-suave">Subtotal</span>
          <span className="text-sm tabular">
            {usd(d(linea.precio || 0).times(linea.cantidad))}
          </span>
        </div>

        <button
          type="button"
          onClick={onQuitar}
          className="rounded p-2 text-texto-suave hover:bg-fondo"
          aria-label="Quitar producto"
        >
          <Trash2 className="size-4" />
        </button>
      </div>

      {bloqueantes.map((a) => (
        <div
          key={a.codigo}
          className="mt-3 rounded-lg border border-critico/30 bg-critico-suave p-3 text-sm text-critico"
        >
          <p className="flex items-center gap-1 font-medium">
            {a.exige_admin ? (
              <ShieldAlert className="size-4" />
            ) : (
              <TriangleAlert className="size-4" />
            )}
            {a.mensaje}
          </p>
          {a.sugerencia && <p className="mt-1 text-xs opacity-90">{a.sugerencia}</p>}

          <div className="mt-3 space-y-2">
            {a.detalles.precio_esperado && (
              <button
                type="button"
                onClick={() => onCambiar({ precio: String(a.detalles.precio_esperado) })}
                className="block w-full rounded-lg border border-critico/40 px-3 py-2 text-left text-xs"
              >
                Cobrar el precio de política ({usd(String(a.detalles.precio_esperado))})
              </button>
            )}
            {a.detalles.moneda_sugerida && (
              <p className="rounded-lg border border-critico/40 px-3 py-2 text-xs">
                O cambiá el nivel de precio arriba a{" "}
                <strong>
                  {a.detalles.moneda_sugerida === "USD" ? "Divisa / USDT" : "Tasa BCV"}
                </strong>
                : el registro queda correcto.
              </p>
            )}
            {(!a.exige_admin || esAdmin) && (
              <label className="block">
                <span className="mb-1 block text-xs">
                  O cobrá {usd(linea.precio || 0)} con un motivo
                  {a.exige_admin && " (queda firmado con tu nombre)"}
                </span>
                <Input
                  placeholder="Cliente frecuente, promoción, precio acordado antes…"
                  value={linea.motivo ?? ""}
                  onChange={(e) => onCambiar({ motivo: e.target.value })}
                />
              </label>
            )}
            {a.exige_admin && !esAdmin && (
              <p className="text-xs">
                Esto lo tiene que autorizar un socio: vender por debajo del costo es una
                pérdida.
              </p>
            )}
          </div>
        </div>
      ))}

      {avisos.map((a) => (
        <div key={a.codigo} className="mt-2 flex items-start gap-2 text-xs text-texto-suave">
          <Insignia tono="neutro">aviso</Insignia>
          <span>
            {a.mensaje}
            {a.sugerencia && ` ${a.sugerencia}`}
          </span>
        </div>
      ))}
    </div>
  );
}
