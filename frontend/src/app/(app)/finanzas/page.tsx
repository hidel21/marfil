"use client";

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CircleDollarSign, Package, Receipt, TrendingUp } from "lucide-react";
import { Dinero } from "@/components/dinero";
import { Cargando, Tarjeta, Titulo, Vacio } from "@/components/ui";
import { useComisiones, useFinanzas } from "@/hooks/datos";
import { fecha } from "@/lib/formato";
import { porcentaje } from "@/lib/dinero";

export default function Finanzas() {
  const consulta = useFinanzas();
  const comisiones = useComisiones();
  if (consulta.isLoading) return <Cargando que="Calculando resultados" />;
  if (!consulta.data) return <Vacio titulo="No hay información financiera" />;
  const d = consulta.data;
  const mes = d.mes_actual;
  const serie = d.mensual.map((m) => ({ ...m, mes: fecha(m.mes, "MMM yy"), ventas: Number(m.ventas_usd), gastos: Number(m.gastos_usd), utilidad: Number(m.utilidad_neta_usd) }));
  return <>
    <Titulo detalle="Resultados contables derivados de ventas, costo vendido y gastos registrados.">Finanzas</Titulo>
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <Kpi titulo="Ventas del mes" valor={String(mes.ventas_usd ?? "0")} icono={<TrendingUp />} />
      <Kpi titulo="Utilidad neta" valor={String(mes.utilidad_neta_usd ?? "0")} icono={<CircleDollarSign />} />
      <Kpi titulo="Cuentas por pagar" valor={d.cuentas_por_pagar.por_pagar_usd} detalle={`${d.cuentas_por_pagar.cuentas_abiertas} abiertas`} icono={<Receipt />} />
      <Kpi titulo="Inventario al costo" valor={d.inventario.valor_costo_usd} detalle={`${d.inventario.unidades} unidades`} icono={<Package />} />
    </div>

    <Tarjeta className="mt-5"><h2 className="font-semibold">Evolución mensual</h2><p className="mb-4 text-xs text-texto-suave">Ventas, gastos operativos y utilidad neta</p><div className="h-80"><ResponsiveContainer width="100%" height="100%"><BarChart data={serie} margin={{ left: -20, right: 8 }}><CartesianGrid stroke="#e7e1d4" strokeDasharray="3 3" vertical={false} /><XAxis dataKey="mes" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `$${v}`} /><Tooltip formatter={(v) => `$${Number(v).toFixed(2)}`} /><Legend /><Bar dataKey="ventas" name="Ventas" fill="#343a40" radius={[4,4,0,0]} /><Bar dataKey="gastos" name="Gastos" fill="#c8ad7a" radius={[4,4,0,0]} /><Bar dataKey="utilidad" name="Utilidad" fill="#6e806b" radius={[4,4,0,0]} /></BarChart></ResponsiveContainer></div></Tarjeta>

    <Tarjeta className="mt-5"><div className="mb-4"><h2 className="font-semibold">Comisiones del mes</h2><p className="text-xs text-texto-suave">Tasa vigente: {porcentaje(comisiones.data?.tasa ?? "0")}</p></div>{comisiones.isLoading ? <Cargando /> : <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{comisiones.data?.items.map((v) => <div key={v.usuario_id} className="rounded-xl border border-borde p-4"><div className="flex justify-between gap-3"><div><p className="font-medium">{v.vendedor}</p><p className="text-xs text-texto-suave">{v.ventas} ventas · <Dinero valor={v.vendido_usd} /></p></div><div className="text-right"><p className="text-[11px] uppercase tracking-wide text-texto-suave">Comisión</p><Dinero valor={v.comision_usd} className="font-semibold" /></div></div></div>)}</div>}</Tarjeta>
  </>;
}

function Kpi({ titulo, valor, detalle, icono }: { titulo: string; valor: string; detalle?: string; icono: React.ReactNode }) { return <Tarjeta><div className="flex items-start justify-between"><div><p className="text-xs text-texto-suave">{titulo}</p><p className="marca-serif mt-2 text-2xl font-semibold"><Dinero valor={valor} /></p>{detalle && <p className="mt-1 text-xs text-texto-suave">{detalle}</p>}</div><span className="grid size-10 place-items-center rounded-xl bg-acento-suave text-marca [&>svg]:size-5">{icono}</span></div></Tarjeta>; }
