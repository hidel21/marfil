"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { Boton, Campo, Cargando, Input, Select, Tarjeta, Titulo } from "@/components/ui";
import { api, FalloApi } from "@/lib/api";
import { porcentaje, usd } from "@/lib/dinero";

type Politica = { parametros: Array<{ clave: string; valor: string }>; ejemplo: { costo_usd: string; precio_divisa_usd: string; precio_bcv_usd: string; explicacion: string } };
const ETIQUETAS: Record<string, string> = { GANANCIA_DIVISA: "Margen en divisa", GANANCIA_BCV: "Margen a tasa BCV", TASA_COMISION: "Comisión de ventas", UMBRAL_DESVIACION: "Desviación que exige motivo" };

export default function PoliticaPrecios() {
  const qc = useQueryClient();
  const consulta = useQuery({ queryKey: ["ajustes", "politica"], queryFn: () => api.get<Politica>("/ajustes/politica"), staleTime: 60_000 });
  const cambiar = useMutation({ mutationFn: (c: unknown) => api.post("/ajustes/politica", c), onSuccess: () => { qc.invalidateQueries({ queryKey: ["ajustes", "politica"] }); qc.invalidateQueries({ queryKey: ["productos"] }); } });
  const [clave, setClave] = useState("GANANCIA_DIVISA"); const [valor, setValor] = useState(""); const [desde, setDesde] = useState(new Date().toISOString().slice(0,10)); const [motivo, setMotivo] = useState("");
  async function guardar(e: React.FormEvent) { e.preventDefault(); try { await cambiar.mutateAsync({ clave, valor, desde, motivo }); toast.success("Nueva política vigente"); setValor(""); setMotivo(""); } catch (err) { toast.error(err instanceof FalloApi ? err.mensaje : "No se pudo actualizar"); } }
  return <><Titulo detalle="Cada cambio abre una vigencia nueva; las ventas históricas conservan su regla.">Política de precios</Titulo>{consulta.isLoading ? <Cargando /> : <div className="grid gap-5 lg:grid-cols-[1fr_22rem]"><div className="grid gap-3 sm:grid-cols-2">{consulta.data?.parametros.map((p) => <Tarjeta key={p.clave}><p className="text-xs text-texto-suave">{ETIQUETAS[p.clave] ?? p.clave}</p><p className="marca-serif mt-2 text-2xl font-semibold">{porcentaje(p.valor)}</p><p className="mt-1 font-mono text-[10px] text-texto-suave">{p.clave}</p></Tarjeta>)}{consulta.data?.ejemplo && <Tarjeta className="sm:col-span-2"><p className="font-semibold">Ejemplo con costo {usd(consulta.data.ejemplo.costo_usd)}</p><div className="mt-3 grid grid-cols-2 gap-3"><div><p className="text-xs text-texto-suave">Precio divisa</p><p className="text-lg font-semibold">{usd(consulta.data.ejemplo.precio_divisa_usd)}</p></div><div><p className="text-xs text-texto-suave">Precio BCV</p><p className="text-lg font-semibold">{usd(consulta.data.ejemplo.precio_bcv_usd)}</p></div></div><p className="mt-3 text-xs text-texto-suave">{consulta.data.ejemplo.explicacion}</p></Tarjeta>}</div><Tarjeta><h2 className="mb-4 font-semibold">Programar cambio</h2><form onSubmit={guardar} className="space-y-4"><Campo etiqueta="Parámetro"><Select value={clave} onChange={(e) => setClave(e.target.value)}>{Object.entries(ETIQUETAS).map(([k,v]) => <option key={k} value={k}>{v}</option>)}</Select></Campo><Campo etiqueta="Nuevo porcentaje" ayuda="Ejemplo: 70% se escribe 0.70"><Input type="number" step="0.0001" value={valor} onChange={(e) => setValor(e.target.value)} required /></Campo><Campo etiqueta="Vigente desde"><Input type="date" value={desde} onChange={(e) => setDesde(e.target.value)} required /></Campo><Campo etiqueta="Motivo"><Input value={motivo} onChange={(e) => setMotivo(e.target.value)} required minLength={5} /></Campo><Boton className="w-full" type="submit" disabled={cambiar.isPending}>Guardar vigencia</Boton></form></Tarjeta></div>}</>;
}
