"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { toast } from "sonner";
import { Info, TriangleAlert } from "lucide-react";
import { Dinero } from "@/components/dinero";
import {
  Boton,
  Campo,
  Cargando,
  Input,
  Insignia,
  Select,
  Tarjeta,
  Titulo,
} from "@/components/ui";
import { useCobranza, useRegistrarPago, useTasaSugerida } from "@/hooks/datos";
import { FalloApi } from "@/lib/api";
import { d, usd } from "@/lib/dinero";
import { fecha } from "@/lib/formato";

/**
 * Registrar abono.
 *
 * Dos cosas que la app anterior no tenía:
 *
 * 1. **`Efectivo USD` es una ruta explícita**, sin campo de tasa. Antes había que
 *    inventar `tasa = 1,00` para registrar un pago en dólares, y esos montos se
 *    sumaban al total en bolívares: 28 Bs que nunca fueron bolívares.
 * 2. **La tasa muestra de dónde salió.** La app anterior caía en silencio a un valor
 *    fijo de meses atrás; en un negocio que congela la tasa por pago, eso convierte
 *    cada cobro en dólares en una estimación.
 */

/**
 * El `value` del select no es el canal a secas: `otro` puede cobrarse en bolívares o
 * en divisa, y el enum del backend tiene un solo `otro`. Por eso la opción lleva
 * sufijo en la UI y la moneda viaja aparte, en `en_bolivares`.
 */
const CANALES_BS = [
  { valor: "pago_movil", etiqueta: "Pago móvil" },
  { valor: "transferencia", etiqueta: "Transferencia" },
  { valor: "efectivo_bs", etiqueta: "Efectivo Bs" },
  { valor: "otro:bs", etiqueta: "Otro (en bolívares)" },
];
const CANALES_DIVISA = [
  { valor: "efectivo_usd", etiqueta: "Efectivo USD" },
  { valor: "zelle", etiqueta: "Zelle" },
  { valor: "binance", etiqueta: "Binance" },
  { valor: "usdt", etiqueta: "USDT" },
  { valor: "otro:usd", etiqueta: "Otro (en divisa)" },
];

/** Las series que el sistema captura a diario. El BCV es la referencia legal. */
const TIPOS_TASA = [
  { valor: "bcv", etiqueta: "Dólar BCV" },
  { valor: "paralelo", etiqueta: "Dólar paralelo" },
  { valor: "usdt_ve", etiqueta: "USDT" },
  { valor: "euro", etiqueta: "Euro oficial" },
  { valor: "euro_paralelo", etiqueta: "Euro paralelo" },
];

/** "otro:bs" y "otro:usd" son de la UI; el backend solo conoce "otro". */
function canalReal(valor: string): string {
  return valor.startsWith("otro:") ? "otro" : valor;
}

export default function PaginaAbono() {
  return (
    <Suspense fallback={<Cargando />}>
      <NuevoAbono />
    </Suspense>
  );
}

function NuevoAbono() {
  const router = useRouter();
  const params = useSearchParams();
  const hoy = new Date().toISOString().slice(0, 10);

  const [ventaId, setVentaId] = useState<number | null>(
    Number(params.get("venta")) || null,
  );
  const [fechaPago, setFechaPago] = useState(hoy);
  const [canal, setCanal] = useState("pago_movil");
  const [monto, setMonto] = useState("");
  const [tasaManual, setTasaManual] = useState("");
  const [tipoTasa, setTipoTasa] = useState("bcv");
  const [referencia, setReferencia] = useState("");
  const [permitirExcedente, setPermitirExcedente] = useState(false);

  const cobranza = useCobranza({ incluir_socios: true });
  const tasa = useTasaSugerida(fechaPago, tipoTasa);
  const registrar = useRegistrarPago();

  const enBolivares = CANALES_BS.some((c) => c.valor === canal);
  const tasaUsada = tasaManual || tasa.data?.valor || "";

  const ventas = useMemo(
    () =>
      (cobranza.data ?? []).flatMap((c) =>
        c.ventas.map((v) => ({ ...v, cliente: c.cliente })),
      ),
    [cobranza.data],
  );
  const venta = ventas.find((v) => v.venta_id === ventaId);

  const equivalenteUsd =
    enBolivares && tasaUsada && d(tasaUsada).gt(0)
      ? d(monto || 0).div(d(tasaUsada))
      : d(monto || 0);
  const saldoResultante = venta
    ? d(venta.saldo_usd).minus(equivalenteUsd)
    : null;

  async function guardar() {
    if (!ventaId) return;
    try {
      const r = await registrar.mutateAsync({
        venta_id: ventaId,
        fecha: fechaPago,
        canal: canalReal(canal),
        monto_moneda: monto,
        ...(enBolivares ? { tipo_tasa: tipoTasa } : {}),
        ...(canal.startsWith("otro:") ? { en_bolivares: enBolivares } : {}),
        ...(enBolivares && tasaManual ? { tasa_aplicada: tasaManual } : {}),
        ...(referencia.trim() ? { referencia: referencia.trim() } : {}),
        permitir_excedente: permitirExcedente,
      });
      toast.success(`Abono de ${usd(r.monto_usd as string)} registrado`, {
        description: `Saldo: ${usd(r.saldo_usd as string)} · ${r.estado_cobro as string}`,
      });
      router.push("/cobranza");
    } catch (err) {
      const fallo = err instanceof FalloApi ? err : null;
      if (fallo?.codigo === "ABONO_SUPERA_SALDO") {
        setPermitirExcedente(true);
      }
      toast.error(fallo?.mensaje ?? "No se pudo registrar el abono", {
        description: fallo?.sugerencia,
      });
    }
  }

  return (
    <>
      <Titulo detalle="La tasa se congela en el pago y no se recalcula nunca.">
        Registrar abono
      </Titulo>

      <div className="grid gap-5 lg:grid-cols-[1fr_18rem]">
        <Tarjeta className="space-y-4">
          <Campo etiqueta="Venta" requerido>
            <Select
              value={ventaId ?? ""}
              onChange={(e) => setVentaId(Number(e.target.value) || null)}
            >
              <option value="">Elegí la venta…</option>
              {ventas.map((v) => (
                <option key={v.venta_id} value={v.venta_id}>
                  {v.cliente} — {v.producto ?? v.codigo} — debe {usd(v.saldo_usd)}
                  {v.dias_mora > 0 && ` (${v.dias_mora} d)`}
                </option>
              ))}
            </Select>
          </Campo>

          <div className="grid gap-4 sm:grid-cols-2">
            <Campo
              etiqueta="Fecha del pago"
              requerido
              ayuda="Se pueden cargar pagos de días anteriores."
            >
              <Input
                type="date"
                value={fechaPago}
                max={hoy}
                onChange={(e) => setFechaPago(e.target.value)}
              />
            </Campo>

            <Campo etiqueta="Método" requerido>
              <Select
                value={canal}
                onChange={(e) => {
                  const siguienteCanal = e.target.value;
                  setCanal(siguienteCanal);
                  if (!CANALES_BS.some((c) => c.valor === siguienteCanal)) {
                    setTasaManual("");
                  }
                }}
              >
                <optgroup label="En bolívares (lleva tasa)">
                  {CANALES_BS.map((c) => (
                    <option key={c.valor} value={c.valor}>
                      {c.etiqueta}
                    </option>
                  ))}
                </optgroup>
                <optgroup label="En divisa (sin tasa)">
                  {CANALES_DIVISA.map((c) => (
                    <option key={c.valor} value={c.valor}>
                      {c.etiqueta}
                    </option>
                  ))}
                </optgroup>
              </Select>
            </Campo>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <Campo etiqueta={enBolivares ? "Monto en bolívares" : "Monto en dólares"} requerido>
              <Input
                type="number"
                step="0.01"
                min={0}
                value={monto}
                onChange={(e) => setMonto(e.target.value)}
              />
            </Campo>

            {enBolivares && (
              <Campo etiqueta="Tasa a usar">
                <Select value={tipoTasa} onChange={(e) => { setTipoTasa(e.target.value); setTasaManual(""); }}>
                  {TIPOS_TASA.map((t) => (
                    <option key={t.valor} value={t.valor}>
                      {t.etiqueta}
                    </option>
                  ))}
                </Select>
              </Campo>
            )}

            {enBolivares && (
              <Campo
                etiqueta="Tasa aplicada"
                ayuda={
                  tasa.data?.disponible ? (
                    <span className={tasa.data.es_respaldo ? "text-ambar" : undefined}>
                      {tasa.data.procedencia}
                      {tasa.data.es_respaldo && " — conviene revisarla"}
                    </span>
                  ) : (
                    <span className="text-critico">{tasa.data?.mensaje}</span>
                  )
                }
              >
                <Input
                  type="number"
                  step="0.0001"
                  placeholder={tasa.data?.valor ?? ""}
                  value={tasaManual}
                  onChange={(e) => setTasaManual(e.target.value)}
                />
              </Campo>
            )}
          </div>

          {!enBolivares && (
            <div className="flex items-start gap-2 rounded-lg bg-marca-suave p-3 text-xs text-marca">
              <Info className="mt-0.5 size-4 shrink-0" />
              <span>
                Este método no lleva tasa: el monto ya está en dólares. Es la ruta
                correcta para el efectivo en divisa, que antes había que registrar como
                bolívares con tasa 1.
              </span>
            </div>
          )}

          <Campo
            etiqueta="Referencia"
            ayuda={
              enBolivares
                ? "El número de la operación. Se avisa si ya está registrada."
                : "Opcional: el efectivo no tiene referencia bancaria."
            }
          >
            <Input
              value={referencia}
              onChange={(e) => setReferencia(e.target.value)}
              placeholder={enBolivares ? "Ej. 5863" : "Recibo o nota"}
            />
          </Campo>

          {permitirExcedente && (
            <label className="flex items-start gap-2 rounded-lg bg-ambar-suave p-3 text-xs text-ambar">
              <input
                type="checkbox"
                checked={permitirExcedente}
                onChange={(e) => setPermitirExcedente(e.target.checked)}
                className="mt-0.5"
              />
              <span>
                El abono supera el saldo. Confirmado, se aplica lo que cubre esta venta y
                el resto queda como saldo a favor.
              </span>
            </label>
          )}
        </Tarjeta>

        <Tarjeta className="lg:sticky lg:top-6 lg:self-start">
          <p className="mb-3 text-sm font-medium">Cómo se aplica</p>
          {!venta ? (
            <p className="text-sm text-texto-suave">Elegí una venta.</p>
          ) : (
            <dl className="space-y-2 text-sm">
              <Fila etiqueta="Venta">
                <span className="font-mono text-xs">{venta.codigo}</span>
              </Fila>
              <Fila etiqueta="Total">
                <Dinero valor={venta.total_usd} />
              </Fila>
              <Fila etiqueta="Debe hoy">
                <Dinero valor={venta.saldo_usd} />
              </Fila>
              <Fila etiqueta="Vence">{fecha(venta.fecha_vencimiento)}</Fila>
              <hr className="border-borde" />
              <Fila etiqueta="Este abono">
                <span className="font-semibold tabular">
                  {usd(equivalenteUsd)}
                </span>
              </Fila>
              {enBolivares && tasaUsada && (
                <p className="text-xs text-texto-suave">
                  {monto || 0} Bs ÷ {tasaUsada}
                </p>
              )}
              <Fila etiqueta="Saldo después">
                <span
                  className={
                    saldoResultante && saldoResultante.lt(0)
                      ? "text-ambar tabular"
                      : "tabular"
                  }
                >
                  {saldoResultante ? usd(saldoResultante) : "—"}
                </span>
              </Fila>
              {saldoResultante?.lt(0) && (
                <Insignia tono="ambar">
                  <TriangleAlert className="size-3" />
                  sobran {usd(saldoResultante.abs())}
                </Insignia>
              )}
            </dl>
          )}

          <Boton
            onClick={guardar}
            disabled={!ventaId || !monto || registrar.isPending}
            className="mt-4 w-full"
          >
            {registrar.isPending ? "Guardando…" : "Registrar abono"}
          </Boton>
        </Tarjeta>
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
