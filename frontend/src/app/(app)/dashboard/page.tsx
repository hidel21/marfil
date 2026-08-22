"use client";

import Link from "next/link";
import { ArrowRight, CircleDollarSign, PackageSearch, ShoppingBag, UsersRound } from "lucide-react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Dinero } from "@/components/dinero";
import { Cargando, Insignia, Tarjeta, Titulo, Vacio } from "@/components/ui";
import { useDashboard } from "@/hooks/datos";
import { useSesion } from "@/hooks/sesion";
import { fecha, fechaCorta } from "@/lib/formato";

export default function Dashboard() {
  const { yo } = useSesion();
  const consulta = useDashboard(30);
  if (consulta.isLoading) return <Cargando que="Preparando el resumen" />;
  if (!consulta.data) return <Vacio titulo="No se pudo cargar el resumen" />;
  const { metricas: m, actividad, top_productos: top, ventas_recientes: recientes } = consulta.data;
  const serie = actividad.map((p) => ({ ...p, ventas_usd: Number(p.ventas_usd), cobrado_usd: Number(p.cobrado_usd) }));

  return (
    <>
      <Titulo detalle={`Una lectura clara de los últimos 30 días, ${yo?.nombre?.split(" ")[0] ?? ""}.`}>
        Resumen del negocio
      </Titulo>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi etiqueta="Ventas del mes" valor={<Dinero valor={m.ventas_mes_usd} />} icono={<ShoppingBag />} />
        <Kpi etiqueta="Cobrado este mes" valor={<Dinero valor={m.cobrado_mes_usd} />} icono={<CircleDollarSign />} />
        <Kpi etiqueta="Por cobrar" valor={<Dinero valor={m.por_cobrar_usd} />} detalle={`${m.clientes_deudores} clientes`} icono={<UsersRound />} />
        {yo?.ve_costos ? (
          <Kpi etiqueta="Utilidad bruta" valor={<Dinero valor={m.ganancia_bruta_mes_usd} />} icono={<PackageSearch />} />
        ) : (
          <Kpi etiqueta="Operaciones del mes" valor={String(actividad.reduce((a, d) => a + d.ventas, 0))} icono={<PackageSearch />} />
        )}
      </div>

      {yo?.rol === "admin" && (m.stock_bajo > 0 || m.productos_sin_costo > 0) && (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <Accion href="/productos" titulo={`${m.stock_bajo} productos con stock bajo`} texto="Revisar inventario y planificar reposición." />
          <Accion href="/productos/revision" titulo={`${m.productos_sin_costo} productos sin base de precio`} texto="Completar el costo evita ventas sin margen verificable." />
        </div>
      )}

      <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1.65fr)_minmax(18rem,.75fr)]">
        <Tarjeta>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <div><h2 className="font-semibold">Actividad diaria</h2><p className="text-xs text-texto-suave">Venta facturada frente a dinero cobrado</p></div>
            <div className="flex gap-3 text-xs text-texto-suave"><span><i className="mr-1 inline-block size-2 rounded-full bg-marca" />Ventas</span><span><i className="mr-1 inline-block size-2 rounded-full bg-acento" />Cobros</span></div>
          </div>
          <div className="h-72 w-full" aria-label="Gráfico de ventas y cobros diarios">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={serie} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
                <CartesianGrid stroke="#e7e1d4" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="fecha" tickFormatter={fechaCorta} tick={{ fontSize: 11 }} minTickGap={28} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `$${v}`} />
                <Tooltip labelFormatter={(v) => fecha(String(v))} formatter={(v) => [`$${Number(v).toFixed(2)}`, ""]} />
                <Line type="monotone" dataKey="ventas_usd" stroke="#343a40" strokeWidth={2.5} dot={false} />
                <Line type="monotone" dataKey="cobrado_usd" stroke="#a98750" strokeWidth={2.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Tarjeta>

        <Tarjeta>
          <h2 className="font-semibold">Productos destacados</h2>
          <p className="mb-4 text-xs text-texto-suave">Por ventas de los últimos 30 días</p>
          {top.length ? <ol className="space-y-4">{top.map((p, i) => (
            <li key={p.nombre} className="flex items-center gap-3">
              <span className="grid size-8 shrink-0 place-items-center rounded-full bg-acento-suave text-xs font-bold text-marca">{i + 1}</span>
              <div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{p.nombre}</p><p className="text-xs text-texto-suave">{p.unidades} unidades</p></div>
              <Dinero valor={p.ventas_usd} className="text-sm font-semibold" />
            </li>
          ))}</ol> : <Vacio titulo="Todavía no hay ventas" />}
        </Tarjeta>
      </div>

      <Tarjeta className="mt-5 overflow-hidden p-0 sm:p-0">
        <div className="flex items-center justify-between px-4 py-4 sm:px-5"><div><h2 className="font-semibold">Ventas recientes</h2><p className="text-xs text-texto-suave">Últimos movimientos registrados</p></div><Link href="/cobranza" className="text-sm font-semibold text-marca">Ver cobranza</Link></div>
        <div className="divide-y divide-borde/70">
          {recientes.map((v) => <div key={v.id} className="grid gap-2 px-4 py-3 sm:grid-cols-[1fr_auto_auto] sm:items-center sm:px-5">
            <div><p className="text-sm font-medium">{v.cliente}</p><p className="text-xs text-texto-suave">{v.codigo} · {fecha(v.fecha)}</p></div>
            <Dinero valor={v.total_usd} className="text-sm font-semibold" />
            <Insignia tono={Number(v.saldo_usd) > 0 ? "ambar" : "ok"}>{Number(v.saldo_usd) > 0 ? `Debe $${Number(v.saldo_usd).toFixed(2)}` : "Pagada"}</Insignia>
          </div>)}
        </div>
      </Tarjeta>
    </>
  );
}

function Kpi({ etiqueta, valor, detalle, icono }: { etiqueta: string; valor: React.ReactNode; detalle?: string; icono: React.ReactNode }) {
  return <Tarjeta className="relative overflow-hidden"><div className="absolute -right-5 -top-5 size-24 rounded-full bg-acento-suave/65" /><div className="relative flex items-start justify-between"><div><p className="text-xs font-medium text-texto-suave">{etiqueta}</p><div className="marca-serif mt-2 text-2xl font-semibold">{valor}</div>{detalle && <p className="mt-1 text-xs text-texto-suave">{detalle}</p>}</div><span className="grid size-10 place-items-center rounded-xl bg-navegacion text-[#fff8df] [&>svg]:size-5">{icono}</span></div></Tarjeta>;
}

function Accion({ href, titulo, texto }: { href: string; titulo: string; texto: string }) {
  return <Link href={href} className="group flex items-center gap-3 rounded-2xl border border-acento/25 bg-acento-suave/45 p-4"><div className="min-w-0 flex-1"><p className="text-sm font-semibold">{titulo}</p><p className="text-xs text-texto-suave">{texto}</p></div><ArrowRight className="size-4 text-acento transition group-hover:translate-x-1" /></Link>;
}
