"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { Boton, Campo, Cargando, Input, Insignia, Select, Tabla, Tarjeta, Td, Th, Titulo } from "@/components/ui";
import { api, FalloApi } from "@/lib/api";
import { fecha, fechaHora } from "@/lib/formato";

type Tasa = { fecha: string; tipo: string; valor: string; origen: string; confianza: string; capturado_at: string };
export default function Tasas() {
  const qc = useQueryClient(); const tasas = useQuery({ queryKey: ["ajustes", "tasas"], queryFn: () => api.get<Tasa[]>("/ajustes/tasas", { limite: 60 }), staleTime: 60_000 });
  const guardar = useMutation({ mutationFn: (c: unknown) => api.post("/ajustes/tasas", c), onSuccess: () => qc.invalidateQueries({ queryKey: ["ajustes", "tasas"] }) });
  const [fechaTasa, setFechaTasa] = useState(new Date().toISOString().slice(0,10)); const [tipo, setTipo] = useState("bcv"); const [valor, setValor] = useState(""); const [motivo, setMotivo] = useState("");
  async function enviar(e: React.FormEvent) { e.preventDefault(); try { await guardar.mutateAsync({ fecha: fechaTasa, tipo, valor, motivo }); toast.success("Tasa guardada con evidencia manual"); setValor(""); setMotivo(""); } catch (err) { toast.error(err instanceof FalloApi ? err.mensaje : "No se pudo guardar"); } }
  return <><Titulo detalle="Corregir un snapshot no modifica pagos que ya fueron contabilizados.">Tasas de cambio</Titulo><Tarjeta className="mb-5"><form onSubmit={enviar} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_1fr_2fr_auto] lg:items-end"><Campo etiqueta="Fecha"><Input type="date" value={fechaTasa} onChange={(e) => setFechaTasa(e.target.value)} /></Campo><Campo etiqueta="Tipo"><Select value={tipo} onChange={(e) => setTipo(e.target.value)}><option value="bcv">BCV</option><option value="binance">Binance</option><option value="usdt_ve">USDT/VE</option><option value="paralelo">Paralelo</option></Select></Campo><Campo etiqueta="Valor"><Input type="number" step="0.00000001" min="0.01" value={valor} onChange={(e) => setValor(e.target.value)} required /></Campo><Campo etiqueta="Motivo"><Input value={motivo} onChange={(e) => setMotivo(e.target.value)} minLength={5} required /></Campo><Boton type="submit" disabled={guardar.isPending}>Guardar</Boton></form></Tarjeta>{tasas.isLoading ? <Cargando /> : <Tabla><thead><tr><Th>Fecha</Th><Th>Tipo</Th><Th className="text-right">Tasa</Th><Th>Origen</Th><Th>Confianza</Th><Th>Captura</Th></tr></thead><tbody>{tasas.data?.map((t, i) => <tr key={`${t.fecha}-${t.tipo}-${i}`}><Td>{fecha(t.fecha)}</Td><Td className="uppercase">{t.tipo}</Td><Td className="text-right font-semibold tabular">{Number(t.valor).toLocaleString("es-VE", { maximumFractionDigits: 4 })}</Td><Td className="capitalize">{t.origen.replaceAll("_", " ")}</Td><Td><Insignia tono={t.confianza === "alta" ? "ok" : t.confianza === "media" ? "ambar" : "neutro"}>{t.confianza}</Insignia></Td><Td className="text-xs text-texto-suave">{fechaHora(t.capturado_at)}</Td></tr>)}</tbody></Tabla>}</>;
}
