"use client";

import { useQuery } from "@tanstack/react-query";
import { Dinero } from "@/components/dinero";
import { Cargando, Tabla, Td, Th, Titulo, Vacio } from "@/components/ui";
import { api } from "@/lib/api";
import { fecha } from "@/lib/formato";
type Fila = { venta: string; fecha: string; cliente: string; vendedor: string; producto: string; cantidad: number; precio_unitario_usd: string; costo_unitario_usd: string; perdida_usd: string; motivo_desviacion: string | null };
export default function BajoCosto() { const consulta = useQuery({ queryKey: ["auditoria","bajo-costo"], queryFn: () => api.get<Fila[]>("/auditoria/bajo-costo") }); return <><Titulo detalle="Excepciones donde el precio unitario fue menor que el costo.">Ventas bajo costo</Titulo>{consulta.isLoading ? <Cargando /> : !(consulta.data?.length) ? <Vacio titulo="No hay ventas con pérdida" /> : <Tabla><thead><tr><Th>Venta</Th><Th>Cliente</Th><Th>Producto</Th><Th>Vendedor</Th><Th className="text-right">Precio</Th><Th className="text-right">Costo</Th><Th className="text-right">Pérdida</Th><Th>Motivo</Th></tr></thead><tbody>{consulta.data.map((f, i) => <tr key={`${f.venta}-${i}`}><Td><p>{f.venta}</p><p className="text-xs text-texto-suave">{fecha(f.fecha)}</p></Td><Td>{f.cliente}</Td><Td>{f.producto} × {f.cantidad}</Td><Td>{f.vendedor}</Td><Td className="text-right"><Dinero valor={f.precio_unitario_usd} /></Td><Td className="text-right"><Dinero valor={f.costo_unitario_usd} /></Td><Td className="text-right font-semibold text-critico"><Dinero valor={f.perdida_usd} /></Td><Td>{f.motivo_desviacion ?? "Sin documentar"}</Td></tr>)}</tbody></Tabla>}</>; }
