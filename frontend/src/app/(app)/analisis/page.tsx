"use client";

import clsx from "clsx";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import {
  endOfMonth,
  format,
  startOfMonth,
  startOfYear,
  subDays,
  subMonths,
} from "date-fns";
import { ArrowDownRight, ArrowUpRight, Minus, RotateCcw } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Dinero } from "@/components/dinero";
import { Aviso, Cargando, Input, Select, Tabla, Tarjeta, Td, Th, Titulo, Vacio } from "@/components/ui";
import { type Analisis, type Indicadores, useAnalisis, useOpcionesAnalisis } from "@/hooks/datos";
import { d, sumar, usd } from "@/lib/dinero";
import { contar, fecha, fechaCorta } from "@/lib/formato";

/**
 * Análisis: cuánto se vende y se cobra, en el período y con el corte que se elija.
 *
 * Los filtros van en una sola fila arriba y recortan TODO lo de abajo, así los
 * números de la pantalla siempre suman entre sí. Viven en la URL: un recorte se
 * comparte o se guarda como enlace, y recargar no lo pierde.
 *
 * Colores validados (ver la guía de visualización): azul pizarra para lo vendido y
 * bronce para lo cobrado, cerca de la paleta de la marca. El carbón y el bronce
 * originales fallaban el chequeo de luminosidad y croma: el carbón se leía gris.
 */

const VENDIDO = "#3b6ea8";
const COBRADO = "#b8862f";

const HOY = () => new Date();
const iso = (f: Date) => format(f, "yyyy-MM-dd");

type Atajo = { clave: string; etiqueta: string; rango: () => [Date, Date]; agrupar: string };
const ATAJOS: Atajo[] = [
  { clave: "7d", etiqueta: "7 días", rango: () => [subDays(HOY(), 6), HOY()], agrupar: "dia" },
  { clave: "15d", etiqueta: "15 días", rango: () => [subDays(HOY(), 14), HOY()], agrupar: "dia" },
  { clave: "30d", etiqueta: "30 días", rango: () => [subDays(HOY(), 29), HOY()], agrupar: "semana" },
  { clave: "90d", etiqueta: "90 días", rango: () => [subDays(HOY(), 89), HOY()], agrupar: "quincena" },
  { clave: "mes", etiqueta: "Este mes", rango: () => [startOfMonth(HOY()), HOY()], agrupar: "dia" },
  {
    clave: "mes-ant",
    etiqueta: "Mes anterior",
    rango: () => [startOfMonth(subMonths(HOY(), 1)), endOfMonth(subMonths(HOY(), 1))],
    agrupar: "semana",
  },
  { clave: "anio", etiqueta: "Este año", rango: () => [startOfYear(HOY()), HOY()], agrupar: "mes" },
];

const AGRUPACIONES = [
  ["dia", "Por día"],
  ["semana", "Por semana"],
  ["quincena", "Por quincena"],
  ["mes", "Por mes"],
] as const;

const CANAL: Record<string, string> = {
  pago_movil: "Pago móvil",
  transferencia: "Transferencia",
  efectivo_bs: "Efectivo Bs",
  efectivo_usd: "Efectivo USD",
  zelle: "Zelle",
  binance: "Binance",
  usdt: "USDT",
  otro: "Otro",
  sin_dato: "Sin dato",
};
const MONEDA: Record<string, string> = { VES: "BCV (bolívares)", USD: "Divisa", USDT: "USDT" };

const FILTROS = ["vendedor_id", "cliente_id", "producto_id", "linea", "moneda", "canal"] as const;

export default function PaginaAnalisis() {
  return (
    <Suspense fallback={<Cargando />}>
      <AnalisisVentas />
    </Suspense>
  );
}

function AnalisisVentas() {
  const router = useRouter();
  const url = useSearchParams();
  const opciones = useOpcionesAnalisis();

  // Sin parámetros, los últimos 15 días por día: la pregunta más frecuente.
  const atajo = url.get("periodo") ?? (url.get("desde") ? "custom" : "15d");
  const elegido = ATAJOS.find((a) => a.clave === atajo);
  const [desdeDef, hastaDef] = elegido ? elegido.rango() : [subDays(HOY(), 14), HOY()];
  const params: Record<string, string | undefined> = {
    desde: url.get("desde") ?? iso(desdeDef),
    hasta: url.get("hasta") ?? iso(hastaDef),
    agrupar: url.get("agrupar") ?? elegido?.agrupar ?? "dia",
  };
  for (const f of FILTROS) params[f] = url.get(f) ?? undefined;

  const consulta = useAnalisis(params);
  const datos = consulta.data;

  function cambiar(nuevos: Record<string, string | undefined>) {
    const sig = new URLSearchParams(url.toString());
    for (const [k, v] of Object.entries(nuevos)) {
      if (v) sig.set(k, v);
      else sig.delete(k);
    }
    router.replace(`/analisis?${sig.toString()}`, { scroll: false });
  }

  function usarAtajo(a: Atajo) {
    // El atajo trae su agrupación natural; las fechas explícitas se descartan.
    cambiar({ periodo: a.clave, desde: undefined, hasta: undefined, agrupar: a.agrupar });
  }

  const hayFiltros = FILTROS.some((f) => url.get(f));

  return (
    <>
      <Titulo detalle="Cuánto se vende y se cobra en el período que elijas, con el corte que necesites. Todo lo de abajo responde a estos filtros.">
        Análisis
      </Titulo>

      {/* Una fila de filtros, arriba de todo y antes que cualquier número. */}
      <Tarjeta className="mb-5 space-y-3">
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Período">
          {ATAJOS.map((a) => (
            <button
              key={a.clave}
              onClick={() => usarAtajo(a)}
              className={clsx(
                "min-h-9 rounded-full border px-3 text-sm transition",
                atajo === a.clave
                  ? "border-marca bg-marca font-semibold text-white"
                  : "border-borde hover:border-marca",
              )}
            >
              {a.etiqueta}
            </button>
          ))}
          <span className="mx-1 h-6 w-px bg-borde" aria-hidden />
          <label className="flex items-center gap-1 text-sm text-texto-suave">
            Desde
            <Input
              type="date"
              value={params.desde}
              max={params.hasta}
              onChange={(e) => cambiar({ periodo: "custom", desde: e.target.value, hasta: params.hasta })}
              className="h-9 w-40"
            />
          </label>
          <label className="flex items-center gap-1 text-sm text-texto-suave">
            Hasta
            <Input
              type="date"
              value={params.hasta}
              min={params.desde}
              onChange={(e) => cambiar({ periodo: "custom", desde: params.desde, hasta: e.target.value })}
              className="h-9 w-40"
            />
          </label>
        </div>

        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <Select value={params.agrupar} onChange={(e) => cambiar({ agrupar: e.target.value })} className="h-9" aria-label="Agrupar">
            {AGRUPACIONES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
          </Select>
          <Select value={params.vendedor_id ?? ""} onChange={(e) => cambiar({ vendedor_id: e.target.value })} className="h-9" aria-label="Vendedor">
            <option value="">Todos los vendedores</option>
            {opciones.data?.vendedores.map((v) => <option key={v.id} value={v.id}>{v.nombre}</option>)}
          </Select>
          <Select value={params.cliente_id ?? ""} onChange={(e) => cambiar({ cliente_id: e.target.value })} className="h-9" aria-label="Cliente">
            <option value="">Todos los clientes</option>
            {opciones.data?.clientes.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
          </Select>
          <Select value={params.producto_id ?? ""} onChange={(e) => cambiar({ producto_id: e.target.value })} className="h-9" aria-label="Producto">
            <option value="">Todos los productos</option>
            {opciones.data?.productos.map((p) => <option key={p.id} value={p.id}>{p.nombre}</option>)}
          </Select>
          <Select value={params.linea ?? ""} onChange={(e) => cambiar({ linea: e.target.value })} className="h-9" aria-label="Línea">
            <option value="">Todas las líneas</option>
            {opciones.data?.lineas.map((l) => <option key={l} value={l}>{l}</option>)}
          </Select>
          <Select value={params.moneda ?? ""} onChange={(e) => cambiar({ moneda: e.target.value })} className="h-9" aria-label="Moneda de la venta">
            <option value="">Toda moneda</option>
            {Object.entries(MONEDA).map(([v, t]) => <option key={v} value={v}>{t}</option>)}
          </Select>
          <Select value={params.canal ?? ""} onChange={(e) => cambiar({ canal: e.target.value })} className="h-9" aria-label="Método de cobro">
            <option value="">Todo método de cobro</option>
            {Object.entries(CANAL).filter(([v]) => v !== "sin_dato").map(([v, t]) => <option key={v} value={v}>{t}</option>)}
          </Select>
        </div>
        {hayFiltros && (
          <button
            onClick={() => cambiar(Object.fromEntries(FILTROS.map((f) => [f, undefined])))}
            className="inline-flex items-center gap-1 text-sm text-texto-suave underline hover:text-texto"
          >
            <RotateCcw className="size-3.5" /> Quitar filtros
          </button>
        )}
      </Tarjeta>

      {!datos ? (
        consulta.isError ? <Aviso tono="critico" titulo="No se pudo cargar el análisis" /> : <Cargando que="Calculando" />
      ) : (
        <div className={clsx("transition-opacity", consulta.isFetching && "opacity-60")}>
          <p className="mb-3 text-sm text-texto-suave">
            Del {fecha(datos.periodo.desde)} al {fecha(datos.periodo.hasta)} ({datos.periodo.dias} días),
            comparado con los {datos.periodo.dias} días anteriores ({fechaCorta(datos.anterior.desde)} – {fechaCorta(datos.anterior.hasta)}).
          </p>

          <Indicadores actual={datos.indicadores} anterior={datos.indicadores_anterior} />

          {datos.indicadores.ventas_sin_costo > 0 && (
            <div className="mt-4">
              <Aviso tono="ambar" titulo={`${contar(datos.indicadores.ventas_sin_costo, "venta")} del período ${datos.indicadores.ventas_sin_costo === 1 ? "es" : "son"} de productos sin costo`}>
                Su ganancia cuenta el precio completo, así que la ganancia y el margen salen más altos de lo real.
                Cargá esos costos en Productos → Revisión.
              </Aviso>
            </div>
          )}

          <Serie datos={datos} />
          <Desgloses datos={datos} />
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------- indicadores
function variacion(actual: string | number | null, anterior: string | number | null) {
  const a = d(actual ?? 0);
  const b = d(anterior ?? 0);
  if (b.isZero()) return a.isZero() ? 0 : null;
  return a.minus(b).div(b).times(100).toNumber();
}

function Indicadores({ actual, anterior }: { actual: Indicadores; anterior: Indicadores }) {
  // `delta: undefined` = no se compara a proposito; `null` = no hay contra que comparar.
  const tarjetas: { titulo: string; valor: React.ReactNode; delta?: number | null; detalle?: string }[] = [
    { titulo: "Vendido", valor: <Dinero valor={actual.vendido_usd} />, delta: variacion(actual.vendido_usd, anterior.vendido_usd), detalle: contar(actual.unidades, "unidad", "unidades") },
    { titulo: "Ventas", valor: actual.ventas, delta: variacion(actual.ventas, anterior.ventas), detalle: `${contar(actual.clientes, "cliente")} distinto${actual.clientes === 1 ? "" : "s"}` },
    { titulo: "Ticket promedio", valor: <Dinero valor={actual.ticket_promedio_usd} />, delta: variacion(actual.ticket_promedio_usd, anterior.ticket_promedio_usd) },
    { titulo: "Cobrado", valor: <Dinero valor={actual.cobrado_usd} />, delta: variacion(actual.cobrado_usd, anterior.cobrado_usd), detalle: "Plata entrada en el período" },
    { titulo: "Ganancia", valor: <Dinero valor={actual.ganancia_usd} />, delta: variacion(actual.ganancia_usd, anterior.ganancia_usd), detalle: actual.margen_pct ? `Margen ${actual.margen_pct} %` : undefined },
    { titulo: "Por cobrar", valor: <Dinero valor={actual.por_cobrar_usd} />, detalle: "De las ventas del período" },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
      {tarjetas.map((t) => (
        <Tarjeta key={t.titulo} className="p-4">
          <p className="text-xs font-medium text-texto-suave">{t.titulo}</p>
          <p className="mt-1 text-2xl font-semibold tabular">{t.valor}</p>
          {t.delta !== undefined && <Delta valor={t.delta} />}
          {t.detalle && <p className="mt-0.5 text-xs text-texto-suave">{t.detalle}</p>}
        </Tarjeta>
      ))}
    </div>
  );
}

/** El cambio contra el período anterior, siempre con flecha y texto: nunca solo color. */
function Delta({ valor }: { valor: number | null }) {
  if (valor === null) return <p className="mt-1 text-xs text-texto-suave">Sin período anterior comparable</p>;
  const plano = Math.abs(valor) < 0.5;
  const Icono = plano ? Minus : valor > 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <p className={clsx("mt-1 inline-flex items-center gap-0.5 text-xs font-medium", plano ? "text-texto-suave" : valor > 0 ? "text-ok" : "text-critico")}>
      <Icono className="size-3.5" aria-hidden />
      {plano ? "Igual" : `${valor > 0 ? "+" : ""}${valor.toFixed(0)} %`}
      <span className="font-normal text-texto-suave">&nbsp;vs anterior</span>
    </p>
  );
}

// ---------------------------------------------------------------------- serie
function etiquetaPeriodo(p: { desde: string; hasta: string }, agrupar: string) {
  if (agrupar === "dia") return fecha(p.desde, "EEE dd/MM");
  if (agrupar === "mes") return fecha(p.desde, "MMMM yyyy");
  return p.desde === p.hasta ? fechaCorta(p.desde) : `${fechaCorta(p.desde)} – ${fechaCorta(p.hasta)}`;
}

function Serie({ datos }: { datos: Analisis }) {
  const [verTabla, setVerTabla] = useState(datos.serie.length <= 8);
  const agrupar = datos.periodo.agrupar;
  const serie = useMemo(
    () =>
      datos.serie.map((p) => ({
        ...p,
        etiqueta: etiquetaPeriodo(p, agrupar),
        vendido: d(p.vendido_usd).toNumber(),
        cobrado: d(p.cobrado_usd).toNumber(),
      })),
    [datos.serie, agrupar],
  );
  const nombre = AGRUPACIONES.find(([v]) => v === agrupar)?.[1].toLowerCase() ?? "";
  const vacio = serie.every((p) => p.vendido === 0 && p.cobrado === 0);

  return (
    <Tarjeta className="mt-5">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="font-semibold">Vendido y cobrado {nombre}</h2>
          <p className="text-xs text-texto-suave">
            Lo vendido cuenta ventas hechas en cada período; lo cobrado, plata entrada en cada período.
          </p>
        </div>
        {/* Leyenda: siempre presente con dos series, con la forma de la marca (barra). */}
        <div className="flex gap-4 text-xs text-texto">
          <span className="inline-flex items-center gap-1.5"><i className="inline-block size-2.5 rounded-sm" style={{ background: VENDIDO }} />Vendido</span>
          <span className="inline-flex items-center gap-1.5"><i className="inline-block size-2.5 rounded-sm" style={{ background: COBRADO }} />Cobrado</span>
        </div>
      </div>

      {vacio ? (
        <Vacio titulo="Sin ventas ni cobros en este período" detalle="Probá con un período más largo o quitá algún filtro." />
      ) : (
        <div className="h-72 w-full" role="img" aria-label={`Vendido y cobrado ${nombre}`}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={serie} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barGap={2} barCategoryGap="22%">
              <CartesianGrid stroke="#ece7d8" vertical={false} />
              <XAxis dataKey="etiqueta" tick={{ fontSize: 11, fill: "#6f736f" }} tickLine={false} axisLine={{ stroke: "#ddd6c6" }} minTickGap={12} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 11, fill: "#6f736f" }} tickLine={false} axisLine={false} tickFormatter={(v) => `$${v}`} width={52} />
              <Tooltip cursor={{ fill: "#3b6ea8", fillOpacity: 0.06 }} content={<Globo />} />
              <Bar dataKey="vendido" name="Vendido" fill={VENDIDO} radius={[4, 4, 0, 0]} maxBarSize={36} />
              <Bar dataKey="cobrado" name="Cobrado" fill={COBRADO} radius={[4, 4, 0, 0]} maxBarSize={36} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <button onClick={() => setVerTabla((v) => !v)} className="mt-3 text-xs font-medium text-marca underline">
        {verTabla ? "Ocultar la tabla" : "Ver los números en una tabla"}
      </button>
      {verTabla && <TablaSerie datos={datos} />}
    </Tarjeta>
  );
}

type FilaGrafico = { etiqueta: string; ventas: number; vendido: number; cobrado: number; dias: number };

/** Valor primero, nombre después; la clave es un trazo del color de la serie. */
function Globo({ active, payload }: { active?: boolean; payload?: { payload: FilaGrafico }[] }) {
  const p = payload?.[0]?.payload;
  if (!active || !p) return null;
  return (
    <div className="rounded-xl border border-borde bg-superficie px-3 py-2 text-xs shadow-lg">
      <p className="mb-1 font-medium text-texto-suave">{p.etiqueta}{p.dias > 1 ? ` · ${p.dias} días` : ""}</p>
      <p className="flex items-center gap-2"><i className="inline-block h-0.5 w-3" style={{ background: VENDIDO }} /><b className="tabular">{usd(p.vendido)}</b> vendido · {contar(p.ventas, "venta")}</p>
      <p className="flex items-center gap-2"><i className="inline-block h-0.5 w-3" style={{ background: COBRADO }} /><b className="tabular">{usd(p.cobrado)}</b> cobrado</p>
    </div>
  );
}

function TablaSerie({ datos }: { datos: Analisis }) {
  const agrupar = datos.periodo.agrupar;
  const s = datos.serie;
  return (
    <div className="mt-3">
      <Tabla>
        <thead>
          <tr>
            <Th>Período</Th>
            <Th className="text-right">Ventas</Th>
            <Th className="text-right">Vendido</Th>
            <Th className="text-right">Cobrado</Th>
            <Th className="text-right">Ganancia</Th>
            <Th className="text-right">Promedio por día</Th>
          </tr>
        </thead>
        <tbody>
          {s.map((p) => (
            <tr key={p.desde}>
              <Td>{etiquetaPeriodo(p, agrupar)}</Td>
              <Td className="text-right tabular">{p.ventas}</Td>
              <Td className="text-right"><Dinero valor={p.vendido_usd} cero="$0,00" /></Td>
              <Td className="text-right"><Dinero valor={p.cobrado_usd} cero="$0,00" /></Td>
              <Td className="text-right"><Dinero valor={p.ganancia_usd} cero="$0,00" /></Td>
              <Td className="text-right text-texto-suave"><Dinero valor={d(p.vendido_usd).div(p.dias).toFixed(2)} /></Td>
            </tr>
          ))}
          <tr className="font-semibold">
            <Td>Total</Td>
            <Td className="text-right tabular">{s.reduce((n, p) => n + p.ventas, 0)}</Td>
            <Td className="text-right"><Dinero valor={sumar(s.map((p) => p.vendido_usd)).toFixed(2)} /></Td>
            <Td className="text-right"><Dinero valor={sumar(s.map((p) => p.cobrado_usd)).toFixed(2)} /></Td>
            <Td className="text-right"><Dinero valor={sumar(s.map((p) => p.ganancia_usd)).toFixed(2)} /></Td>
            <Td className="text-right text-texto-suave"><Dinero valor={sumar(s.map((p) => p.vendido_usd)).div(datos.periodo.dias).toFixed(2)} /></Td>
          </tr>
        </tbody>
      </Tabla>
    </div>
  );
}

// ------------------------------------------------------------------ desgloses
type Renglon = { clave: string | number; nombre: string; valor: string; detalle?: string; aviso?: boolean };

/** Ranking con barra de un solo tono: es magnitud, no identidad. Los diez primeros y "Otros". */
function Ranking({ titulo, subtitulo, renglones, limite = 10 }: { titulo: string; subtitulo?: string; renglones: Renglon[]; limite?: number }) {
  const visibles = renglones.slice(0, limite);
  const resto = renglones.slice(limite);
  const filas: Renglon[] = resto.length
    ? [...visibles, { clave: "otros", nombre: `Otros (${resto.length})`, valor: sumar(resto.map((r) => r.valor)).toFixed(2) }]
    : visibles;
  const maximo = Math.max(...filas.map((r) => d(r.valor).toNumber()), 0.01);

  return (
    <Tarjeta>
      <h2 className="font-semibold">{titulo}</h2>
      {subtitulo && <p className="text-xs text-texto-suave">{subtitulo}</p>}
      {filas.length === 0 ? (
        <p className="mt-4 text-sm text-texto-suave">Nada en este período.</p>
      ) : (
        <ol className="mt-3 space-y-2.5">
          {filas.map((r) => (
            <li key={r.clave} title={`${r.nombre}: ${usd(r.valor)}`}>
              <div className="flex items-baseline justify-between gap-3 text-sm">
                <span className={clsx("min-w-0 truncate", r.clave === "otros" && "text-texto-suave")}>
                  {r.nombre}{r.aviso && <span className="ml-1 text-xs text-ambar">· sin costo</span>}
                </span>
                <span className="shrink-0 font-semibold tabular">{usd(r.valor)}</span>
              </div>
              <div className="mt-1 h-1.5 rounded-full bg-fondo">
                <div className="h-1.5 rounded-full" style={{ width: `${(d(r.valor).toNumber() / maximo) * 100}%`, background: r.clave === "otros" ? "#c9c3b4" : VENDIDO }} />
              </div>
              {r.detalle && <p className="mt-0.5 text-xs text-texto-suave">{r.detalle}</p>}
            </li>
          ))}
        </ol>
      )}
    </Tarjeta>
  );
}

function Desgloses({ datos }: { datos: Analisis }) {
  const g = datos.desgloses;
  return (
    <div className="mt-5 grid gap-5 lg:grid-cols-2 xl:grid-cols-3">
      <Ranking
        titulo="Productos más vendidos"
        subtitulo="Por monto vendido en el período"
        renglones={g.productos.map((p) => ({ clave: p.id, nombre: p.nombre, valor: p.vendido_usd, detalle: `${contar(p.unidades, "unidad", "unidades")} · ganancia ${usd(p.ganancia_usd)}`, aviso: p.sin_costo }))}
      />
      <Ranking
        titulo="Por vendedor"
        renglones={g.vendedores.map((v) => ({ clave: v.id, nombre: v.nombre, valor: v.vendido_usd, detalle: `${contar(v.ventas, "venta")} · ganancia ${usd(v.ganancia_usd)}` }))}
      />
      <Ranking
        titulo="Mejores clientes"
        subtitulo="Por monto comprado en el período"
        renglones={g.clientes.map((c) => ({ clave: c.id, nombre: c.nombre, valor: c.vendido_usd, detalle: d(c.por_cobrar_usd).gt(0) ? `${contar(c.ventas, "compra")} · debe ${usd(c.por_cobrar_usd)}` : `${contar(c.ventas, "compra")} · al día` }))}
      />
      <Ranking
        titulo="Cobros por método"
        subtitulo="Plata entrada en el período"
        renglones={g.metodos.map((m) => ({ clave: m.canal, nombre: CANAL[m.canal] ?? m.canal, valor: m.cobrado_usd, detalle: contar(m.cobros, "cobro") }))}
      />
      <Ranking
        titulo="Por línea"
        renglones={g.lineas.map((l) => ({ clave: l.linea, nombre: l.linea, valor: l.vendido_usd, detalle: contar(l.unidades, "unidad", "unidades") }))}
      />
      <Ranking
        titulo="Por moneda de la venta"
        renglones={g.monedas.map((m) => ({ clave: m.moneda, nombre: MONEDA[m.moneda] ?? m.moneda, valor: m.vendido_usd, detalle: contar(m.ventas, "venta") }))}
      />
    </div>
  );
}
