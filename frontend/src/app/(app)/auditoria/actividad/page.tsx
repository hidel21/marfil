"use client";

import { useQuery } from "@tanstack/react-query";
import { Cargando, Insignia, Tabla, Td, Th, Titulo, Vacio } from "@/components/ui";
import { api } from "@/lib/api";
import { fechaHora } from "@/lib/formato";
type Actividad = { id: number; ocurrido_at: string; actor_tipo: string; usuario: string | null; accion: string; tabla: string; registro_id: number; campos_cambiados: string[] | null; motivo: string | null };
export default function Actividad() { const consulta = useQuery({ queryKey: ["auditoria","actividad"], queryFn: () => api.get<Actividad[]>("/auditoria/actividad", { limite: 200 }) }); return <><Titulo detalle="Trazabilidad de cambios sensibles, ordenada desde el más reciente.">Actividad del sistema</Titulo>{consulta.isLoading ? <Cargando /> : !(consulta.data?.length) ? <Vacio titulo="Todavía no hay actividad auditada" /> : <Tabla><thead><tr><Th>Momento</Th><Th>Actor</Th><Th>Acción</Th><Th>Registro</Th><Th>Campos</Th><Th>Motivo</Th></tr></thead><tbody>{consulta.data.map((a) => <tr key={a.id}><Td className="whitespace-nowrap">{fechaHora(a.ocurrido_at)}</Td><Td>{a.usuario ?? a.actor_tipo}</Td><Td><Insignia tono={a.accion === "delete" ? "critico" : a.accion === "update" ? "ambar" : "ok"}>{a.accion}</Insignia></Td><Td>{a.tabla} #{a.registro_id}</Td><Td className="text-xs text-texto-suave">{a.campos_cambiados?.join(", ") ?? "—"}</Td><Td>{a.motivo ?? "—"}</Td></tr>)}</tbody></Tabla>}</>; }
