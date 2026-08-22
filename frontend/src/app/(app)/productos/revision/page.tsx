"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, PackageCheck } from "lucide-react";
import { Boton, Campo, Cargando, Input, Select, Tarjeta, Titulo, Vacio } from "@/components/ui";
import { api, FalloApi } from "@/lib/api";
import { fechaHora } from "@/lib/formato";

type Pendiente = { id: number; nombre: string; linea: string | null; costo_usd: string | null; origen_alta: string; notas: string | null; created_at: string; ventas: number };

export default function RevisionProductos() {
  const qc = useQueryClient();
  const consulta = useQuery({ queryKey: ["productos", "revision"], queryFn: () => api.get<Pendiente[]>("/productos/revision"), staleTime: 30_000 });
  const guardar = useMutation({ mutationFn: ({ id, ...datos }: { id: number; linea: string; modelo_precio: string; costo_usd?: string; precio_original_usd?: string }) => api.put(`/productos/${id}`, datos), onSuccess: () => { qc.invalidateQueries({ queryKey: ["productos"] }); qc.invalidateQueries({ queryKey: ["dashboard"] }); } });
  const [edicion, setEdicion] = useState<Record<number, { costo: string; linea: string; modelo: string }>>({});

  async function revisar(p: Pendiente) {
    const e = edicion[p.id] ?? { costo: "", linea: p.linea ?? "", modelo: "costo" };
    try { await guardar.mutateAsync({ id: p.id, linea: e.linea, modelo_precio: e.modelo, ...(e.modelo === "lista" ? { precio_original_usd: e.costo } : { costo_usd: e.costo }) }); toast.success(`${p.nombre} quedó activo`); }
    catch (err) { toast.error(err instanceof FalloApi ? err.mensaje : "No se pudo actualizar"); }
  }

  return <>
    <Titulo detalle="Completa la base de precio de los productos creados durante una venta.">Revisión de productos</Titulo>
    {consulta.isLoading ? <Cargando /> : !(consulta.data?.length) ? <Vacio titulo="La cola está al día" detalle="No quedan productos sin revisar." /> : <div className="space-y-3">{consulta.data.map((p) => { const e = edicion[p.id] ?? { costo: p.costo_usd ?? "", linea: p.linea ?? "", modelo: "costo" }; return <Tarjeta key={p.id}><div className="flex flex-wrap items-start justify-between gap-3"><div className="flex gap-3"><span className="grid size-11 place-items-center rounded-xl bg-acento-suave text-marca"><PackageCheck className="size-5" /></span><div><p className="font-semibold">{p.nombre}</p><p className="text-xs text-texto-suave">Creado {fechaHora(p.created_at)} · {p.ventas} ventas</p>{p.notas && <p className="mt-1 text-xs text-ambar">{p.notas}</p>}</div></div></div><div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_1fr_auto] lg:items-end"><Campo etiqueta="Línea"><Input value={e.linea} onChange={(x) => setEdicion((m) => ({ ...m, [p.id]: { ...e, linea: x.target.value } }))} placeholder="Ej. árabe, diseñador" /></Campo><Campo etiqueta="Modelo"><Select value={e.modelo} onChange={(x) => setEdicion((m) => ({ ...m, [p.id]: { ...e, modelo: x.target.value } }))}><option value="costo">Margen sobre costo</option><option value="lista">Precio de lista</option></Select></Campo><Campo etiqueta={e.modelo === "costo" ? "Costo USD" : "Precio de lista USD"} requerido><Input type="number" min="0" step="0.01" value={e.costo} onChange={(x) => setEdicion((m) => ({ ...m, [p.id]: { ...e, costo: x.target.value } }))} /></Campo><Boton onClick={() => revisar(p)} disabled={!e.costo || guardar.isPending}><CheckCircle2 className="size-4" />Aprobar</Boton></div></Tarjeta>; })}</div>}
  </>;
}
