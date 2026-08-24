"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { Cargando, Insignia, Tabla, Td, Th, Titulo, Vacio } from "@/components/ui";
import { useConciliacion } from "@/hooks/datos";

export default function Pagina() { return <Suspense fallback={<Cargando />}><Contenido /></Suspense>; }
function Contenido() {
  const params = useSearchParams(); const pedido = params.get("tipo");
  const tipo = pedido === "pagos" || pedido === "stock" ? pedido : "ventas";
  const consulta = useConciliacion(tipo); const items = consulta.data?.items ?? [];
  const columnas = items.length ? Object.keys(items[0]!) : [];
  return <><Titulo detalle="Valor almacenado frente al valor reconstruido desde el libro.">Conciliación de {tipo}</Titulo>{consulta.isLoading ? <Cargando /> : consulta.data?.ok ? <Vacio titulo="Todo cuadra" detalle={`${consulta.data.filas_revisadas} filas verificadas sin diferencias.`} /> : <><div className="mb-3"><Insignia tono="critico">{consulta.data?.filas_descuadradas} descuadres</Insignia></div><Tabla><thead><tr>{columnas.map((c) => <Th key={c}>{c.replaceAll("_", " ")}</Th>)}</tr></thead><tbody>{items.map((fila, i) => <tr key={i}>{columnas.map((c) => <Td key={c} className={c === "ok" ? "font-semibold" : undefined}>{typeof fila[c] === "boolean" ? (fila[c] ? "Sí" : "No") : String(fila[c] ?? "—")}</Td>)}</tr>)}</tbody></Tabla></>}</>;
}
