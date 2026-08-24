"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Landmark, Pencil, UsersRound } from "lucide-react";
import { Dinero } from "@/components/dinero";
import { Boton, Campo, Cargando, Input, Tarjeta, Titulo, Vacio } from "@/components/ui";
import { useActualizarSocio, useSocios } from "@/hooks/datos";
import { FalloApi } from "@/lib/api";
import { porcentaje } from "@/lib/dinero";

export default function Socios() {
  const consulta = useSocios();
  const actualizar = useActualizarSocio();
  const [edicion, setEdicion] = useState<{ id: number; capital: string } | null>(null);
  if (consulta.isLoading) return <Cargando que="Cargando socios" />;
  if (!consulta.data) return <Vacio titulo="No hay socios registrados" />;
  const datos = consulta.data;

  async function guardar() {
    if (!edicion) return;
    try { await actualizar.mutateAsync({ id: edicion.id, capital_invertido: edicion.capital }); toast.success("Capital actualizado"); setEdicion(null); }
    catch (e) { toast.error(e instanceof FalloApi ? e.mensaje : "No se pudo actualizar"); }
  }

  return <>
    <Titulo detalle="Participación informativa calculada sobre el capital registrado.">Socios</Titulo>
    <div className="mb-5 grid gap-3 sm:grid-cols-2"><Tarjeta><div className="flex items-start justify-between"><div><p className="text-xs text-texto-suave">Capital total</p><p className="marca-serif mt-2 text-2xl font-semibold"><Dinero valor={datos.capital_total_usd} /></p></div><Landmark className="size-6 text-acento" /></div></Tarjeta><Tarjeta><div className="flex items-start justify-between"><div><p className="text-xs text-texto-suave">Utilidad neta del mes</p><p className="marca-serif mt-2 text-2xl font-semibold"><Dinero valor={datos.utilidad_mes_usd} /></p></div><UsersRound className="size-6 text-acento" /></div></Tarjeta></div>
    <div className="grid gap-4 lg:grid-cols-2">{datos.items.map((s) => <Tarjeta key={s.id}><div className="flex items-start justify-between gap-3"><div><p className="font-semibold">{s.nombre}</p><p className="text-xs text-texto-suave">{s.email ?? "Sin cuenta de acceso vinculada"}</p></div><span className="marca-serif rounded-full bg-acento-suave px-3 py-1 text-sm font-semibold">{porcentaje(s.participacion)}</span></div><div className="mt-5 grid grid-cols-2 gap-3"><div><p className="text-[11px] uppercase tracking-wide text-texto-suave">Capital</p><Dinero valor={s.capital_invertido} className="font-semibold" /></div><div><p className="text-[11px] uppercase tracking-wide text-texto-suave">Utilidad estimada</p><Dinero valor={s.utilidad_estimada_usd} className="font-semibold" /></div></div><div className="mt-4 border-t border-borde pt-3">{edicion?.id === s.id ? <div className="flex items-end gap-2"><Campo etiqueta="Capital invertido"><Input type="number" min="0" step="0.01" value={edicion.capital} onChange={(e) => setEdicion({ ...edicion, capital: e.target.value })} /></Campo><Boton onClick={guardar} disabled={actualizar.isPending}>Guardar</Boton></div> : <Boton variante="fantasma" onClick={() => setEdicion({ id: s.id, capital: s.capital_invertido })}><Pencil className="size-4" />Editar capital</Boton>}</div></Tarjeta>)}</div>
  </>;
}
