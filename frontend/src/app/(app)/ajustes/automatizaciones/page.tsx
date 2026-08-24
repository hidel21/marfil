"use client";

import { toast } from "sonner";
import { Bot, Play, ShieldCheck } from "lucide-react";
import { Boton, Cargando, Insignia, Tarjeta, Titulo, Vacio } from "@/components/ui";
import { useAutomatizaciones, useEjecutarAutomatizacion } from "@/hooks/datos";
import { FalloApi } from "@/lib/api";
import { fechaHora } from "@/lib/formato";

const NOMBRES: Record<string, [string,string]> = { conciliacion: ["Conciliación diaria", "Verifica saldos, pagos e inventario."], limpiar_sesiones: ["Limpieza de sesiones", "Retira sesiones vencidas y revocadas."], snapshot_tasa: ["Captura de tasa", "Guarda el snapshot diario configurado."] };
export default function Automatizaciones() {
  const consulta = useAutomatizaciones(); const ejecutar = useEjecutarAutomatizacion();
  async function correr(nombre: string) { try { await ejecutar.mutateAsync(nombre); toast.success("Automatización completada"); } catch (e) { toast.error(e instanceof FalloApi ? e.mensaje : "La ejecución falló"); } }
  return <><Titulo detalle="Tareas idempotentes: se pueden ejecutar manualmente o desde el cron de producción.">Automatizaciones</Titulo>{consulta.isLoading ? <Cargando /> : !(consulta.data?.length) ? <Vacio titulo="No hay automatizaciones configuradas" /> : <div className="grid gap-4 lg:grid-cols-3">{consulta.data.map((j) => { const [titulo, texto] = NOMBRES[j.nombre] ?? [j.nombre, "Tarea operativa del sistema."]; return <Tarjeta key={j.nombre}><div className="flex items-start justify-between"><span className="grid size-11 place-items-center rounded-xl bg-acento-suave text-marca"><Bot className="size-5" /></span>{j.ultima && <Insignia tono={j.ultima.estado === "ok" ? "ok" : "critico"}>{j.ultima.estado}</Insignia>}</div><p className="mt-4 font-semibold">{titulo}</p><p className="mt-1 min-h-10 text-xs text-texto-suave">{texto}</p>{j.ultima ? <div className="mt-3 rounded-xl bg-fondo p-3 text-xs"><p className="flex items-center gap-1 font-medium"><ShieldCheck className="size-3" />Última ejecución</p><p className="mt-1 text-texto-suave">{fechaHora(j.ultima.inicio)} · {j.ultima.filas_afectadas} cambios</p>{j.ultima.error && <p className="mt-1 text-critico">{j.ultima.error}</p>}</div> : <p className="mt-3 text-xs text-texto-suave">Aún no se ha ejecutado.</p>}<Boton className="mt-4 w-full" variante="secundario" onClick={() => correr(j.nombre)} disabled={ejecutar.isPending}><Play className="size-4" />Ejecutar ahora</Boton></Tarjeta>; })}</div>}</>;
}
