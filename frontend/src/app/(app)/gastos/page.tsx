"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Plus, ReceiptText } from "lucide-react";
import { Dinero } from "@/components/dinero";
import { Boton, Campo, Cargando, Input, Select, Tarjeta, Titulo, Vacio } from "@/components/ui";
import { useCrearGasto, useGastos } from "@/hooks/datos";
import { FalloApi } from "@/lib/api";
import { fecha } from "@/lib/formato";

const hoy = new Date().toISOString().slice(0, 10);
const inicioMes = `${hoy.slice(0, 8)}01`;
const CATEGORIAS = ["publicidad", "envíos", "empaque", "transporte", "servicios", "comisiones", "administración", "otros"];

export default function Gastos() {
  const [desde, setDesde] = useState(inicioMes);
  const [hasta, setHasta] = useState(hoy);
  const [formulario, setFormulario] = useState(false);
  const consulta = useGastos({ desde, hasta });
  const crear = useCrearGasto();

  async function guardar(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const datos = Object.fromEntries(new FormData(form));
    try {
      await crear.mutateAsync(datos);
      toast.success("Gasto registrado");
      form.reset(); setFormulario(false);
    } catch (err) {
      toast.error(err instanceof FalloApi ? err.mensaje : "No se pudo registrar el gasto");
    }
  }

  return <>
    <Titulo detalle="Costos operativos separados de la compra de inventario." accion={<Boton onClick={() => setFormulario(!formulario)}><Plus className="size-4" />Nuevo gasto</Boton>}>Gastos</Titulo>

    {formulario && <Tarjeta className="mb-5"><form onSubmit={guardar} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"><Campo etiqueta="Fecha" requerido><Input name="fecha" type="date" defaultValue={hoy} required /></Campo><Campo etiqueta="Categoría" requerido><Select name="categoria" required>{CATEGORIAS.map((c) => <option key={c}>{c}</option>)}</Select></Campo><Campo etiqueta="Monto USD" requerido><Input name="monto_usd" type="number" min="0.01" step="0.01" required /></Campo><div className="sm:col-span-2"><Campo etiqueta="Descripción" requerido><Input name="descripcion" placeholder="Qué se pagó y para qué" required /></Campo></div><Campo etiqueta="Método"><Select name="canal" defaultValue=""><option value="">No especificado</option><option value="pago_movil">Pago móvil</option><option value="transferencia">Transferencia</option><option value="efectivo_bs">Efectivo Bs</option><option value="efectivo_usd">Efectivo USD</option><option value="zelle">Zelle</option><option value="binance">Binance</option><option value="usdt">USDT</option></Select></Campo><div className="sm:col-span-2 lg:col-span-3"><Boton type="submit" disabled={crear.isPending}>Guardar gasto</Boton></div></form></Tarjeta>}

    <Tarjeta className="mb-5"><div className="flex flex-wrap items-end gap-3"><Campo etiqueta="Desde"><Input type="date" value={desde} onChange={(e) => setDesde(e.target.value)} /></Campo><Campo etiqueta="Hasta"><Input type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} /></Campo><div className="ml-auto"><p className="text-xs text-texto-suave">Total del período</p><p className="marca-serif text-2xl font-semibold"><Dinero valor={consulta.data?.total_usd ?? "0"} /></p></div></div></Tarjeta>

    {consulta.isLoading ? <Cargando que="Cargando gastos" /> : !(consulta.data?.items.length) ? <Vacio titulo="No hay gastos en este período" /> : <div className="space-y-3">{consulta.data.items.map((g) => <Tarjeta key={g.id} className="grid gap-3 sm:grid-cols-[auto_minmax(0,1fr)_auto] sm:items-center"><span className="grid size-11 place-items-center rounded-xl bg-acento-suave text-marca"><ReceiptText className="size-5" /></span><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><p className="font-medium">{g.descripcion}</p><span className="rounded-full bg-fondo px-2 py-0.5 text-[11px] capitalize text-texto-suave">{g.categoria}</span></div><p className="text-xs text-texto-suave">{fecha(g.fecha)}{g.canal ? ` · ${g.canal.replaceAll("_", " ")}` : ""}{g.lote ? ` · lote ${g.lote}` : ""}</p></div><Dinero valor={g.monto_usd} className="text-lg font-semibold" /></Tarjeta>)}</div>}
  </>;
}
