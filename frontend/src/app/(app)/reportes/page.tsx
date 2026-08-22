"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { Download, FileDown, FileText, RotateCcw } from "lucide-react";
import { Dinero } from "@/components/dinero";
import { Boton, Cargando, Input, Insignia, Tabla, Tarjeta, Td, Th, Titulo, Vacio } from "@/components/ui";
import { api, FalloApi } from "@/lib/api";
import { fecha } from "@/lib/formato";

type Pago = { id: number; fecha: string; tipo: string; venta: string; cliente: string; moneda: string; monto_moneda: string; tasa_aplicada: string; monto_usd: string; canal: string; referencia: string | null; motivo: string | null };
const EXPORTACIONES = [
  ["ventas", "Ventas", "Historial comercial y saldos"], ["pagos", "Pagos", "Libro de abonos y tasas"],
  ["productos", "Productos", "Inventario y precios vigentes"], ["clientes", "Clientes", "Directorio y condiciones"],
  ["compras", "Compras", "Lotes y cuentas por pagar"], ["gastos", "Gastos", "Egresos operativos"],
] as const;

export default function Reportes() {
  const qc = useQueryClient();
  const pagos = useQuery({ queryKey: ["pagos", "historial"], queryFn: () => api.get<Pago[]>("/pagos", { limite: 100 }), staleTime: 30_000 });
  const [reverso, setReverso] = useState<{ id: number; motivo: string } | null>(null);
  const revertir = useMutation({ mutationFn: ({ id, motivo }: { id: number; motivo: string }) => api.post(`/pagos/${id}/reversar`, { motivo }), onSuccess: () => { qc.invalidateQueries({ queryKey: ["pagos"] }); qc.invalidateQueries({ queryKey: ["cobranza"] }); } });

  async function descargar(ruta: string) {
    try {
      const archivo = await api.descargar(ruta);
      const url = URL.createObjectURL(archivo.blob); const a = document.createElement("a");
      a.href = url; a.download = archivo.nombre; a.click(); URL.revokeObjectURL(url);
    } catch (e) { toast.error(e instanceof FalloApi ? e.mensaje : "No se pudo descargar"); }
  }

  async function confirmarReverso() {
    if (!reverso) return;
    try { await revertir.mutateAsync(reverso); toast.success("Abono reversado sin borrar su historial"); setReverso(null); }
    catch (e) { toast.error(e instanceof FalloApi ? e.mensaje : "No se pudo reversar"); }
  }

  return <>
    <Titulo detalle="Archivos compatibles con Excel y recibos verificables para cada cobro.">Reportes y documentos</Titulo>
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{EXPORTACIONES.map(([clave, titulo, texto]) => <Tarjeta key={clave} className="flex items-center gap-3"><span className="grid size-11 place-items-center rounded-xl bg-acento-suave text-marca"><FileText className="size-5" /></span><div className="min-w-0 flex-1"><p className="font-semibold">{titulo}</p><p className="text-xs text-texto-suave">{texto}</p></div><Boton variante="fantasma" aria-label={`Descargar ${titulo}`} onClick={() => descargar(`/reportes/exportar/${clave}`)}><Download className="size-4" /></Boton></Tarjeta>)}</div>

    <div className="mt-7"><Titulo detalle="Los reversos se agregan al libro; el pago original nunca se borra.">Historial de pagos</Titulo>{pagos.isLoading ? <Cargando /> : !(pagos.data?.length) ? <Vacio titulo="Todavía no hay pagos" /> : <Tabla><thead><tr><Th>Fecha</Th><Th>Cliente / venta</Th><Th>Método</Th><Th className="text-right">Monto</Th><Th>Referencia</Th><Th>Acciones</Th></tr></thead><tbody>{pagos.data.map((p) => <tr key={p.id} className={p.tipo === "reverso" ? "bg-critico-suave/35" : undefined}><Td>{fecha(p.fecha)}</Td><Td><p className="font-medium">{p.cliente}</p><p className="text-xs text-texto-suave">{p.venta}</p></Td><Td><span className="capitalize">{p.canal.replaceAll("_", " ")}</span>{p.tipo === "reverso" && <div><Insignia tono="critico">reverso</Insignia></div>}</Td><Td className="text-right"><Dinero valor={p.monto_usd} /></Td><Td>{p.referencia ?? "—"}</Td><Td><div className="flex gap-1"><Boton variante="fantasma" title="Descargar recibo" onClick={() => descargar(`/reportes/recibos/${p.id}.pdf`)}><FileDown className="size-4" /></Boton>{p.tipo !== "reverso" && <Boton variante="fantasma" title="Reversar abono" onClick={() => setReverso({ id: p.id, motivo: "" })}><RotateCcw className="size-4" /></Boton>}</div>{reverso?.id === p.id && <div className="mt-2 flex min-w-72 gap-2"><Input placeholder="Motivo verificable" value={reverso.motivo} onChange={(e) => setReverso({ ...reverso, motivo: e.target.value })} /><Boton variante="peligro" disabled={reverso.motivo.length < 5 || revertir.isPending} onClick={confirmarReverso}>Confirmar</Boton></div>}</Td></tr>)}</tbody></Tabla>}</div>
  </>;
}
