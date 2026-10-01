"use client";

import { useState } from "react";
import { toast } from "sonner";
import { FileSpreadsheet, Upload } from "lucide-react";
import {
  Aviso,
  Boton,
  Cargando,
  Insignia,
  Tabla,
  Tarjeta,
  Td,
  Th,
  Titulo,
} from "@/components/ui";
import { type ResumenImportacion, useHistorialImportaciones, useImportarExcel } from "@/hooks/datos";
import { FalloApi } from "@/lib/api";
import { fechaHora } from "@/lib/formato";

/**
 * Importar el libro de Excel, en dos pasos que no se pueden saltar.
 *
 * 1. "Revisar" sube el archivo y muestra qué haría, sin escribir nada.
 * 2. "Aplicar" vuelve a cruzarlo contra la base en el momento y lo carga.
 *
 * El botón de aplicar solo aparece después de ver el plan de ESE archivo: aplicar a
 * ciegas un libro con 70 ventas es la forma de llenar la base de duplicados que el
 * cruce existe para evitar.
 */

const ETAPAS: [string, string][] = [
  ["ventas", "Ventas"],
  ["pagos", "Pagos"],
  ["egresos", "Gastos y compras"],
  ["costos", "Costos"],
];
const TIPOS: [string, string][] = [
  ["crear", "Nuevos"],
  ["actualizar", "Actualizar"],
  ["corregir", "Corregir"],
  ["igual", "Sin cambios"],
  ["omitir", "No se cargan"],
];

export default function ImportarExcel() {
  const [archivo, setArchivo] = useState<File | null>(null);
  const [plan, setPlan] = useState<{ resumen: ResumenImportacion; reporte: string; yaAplicado: boolean } | null>(null);
  const importar = useImportarExcel();
  const historial = useHistorialImportaciones();

  function elegir(f: File | null) {
    setArchivo(f);
    setPlan(null);
  }

  async function revisar() {
    if (!archivo) return;
    try {
      const r = await importar.mutateAsync({ archivo, modo: "plan" });
      setPlan({ resumen: r.resumen ?? {}, reporte: r.reporte_md, yaAplicado: Boolean(r.ya_aplicado) });
    } catch (err) {
      toast.error(err instanceof FalloApi ? err.mensaje : "No se pudo leer el archivo");
    }
  }

  async function aplicar() {
    if (!archivo) return;
    try {
      const r = await importar.mutateAsync({ archivo, modo: "aplicar" });
      toast.success(`Importación #${r.importacion_id} aplicada`);
      setPlan({ resumen: r.aplicadas ?? {}, reporte: r.reporte_md, yaAplicado: true });
    } catch (err) {
      toast.error(err instanceof FalloApi ? err.mensaje : "No se pudo aplicar", {
        description: "No se escribió nada: la carga es todo o nada.",
      });
    }
  }

  const cambios = plan
    ? Object.values(plan.resumen).reduce(
        (n, t) => n + (t.crear ?? 0) + (t.actualizar ?? 0) + (t.corregir ?? 0),
        0,
      )
    : 0;

  return (
    <>
      <Titulo detalle="Primero se revisa qué haría; recién después se aplica. Lo que ya está en la base no se duplica.">
        Importar Excel
      </Titulo>

      <Tarjeta className="mb-5">
        <div className="flex flex-wrap items-center gap-3">
          <label className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-xl border border-borde px-4 text-sm font-medium hover:border-marca">
            <FileSpreadsheet className="size-4 text-marca" />
            {archivo ? archivo.name : "Elegir el libro (.xlsx)"}
            <input
              type="file"
              accept=".xlsx"
              className="hidden"
              onChange={(e) => elegir(e.target.files?.[0] ?? null)}
            />
          </label>
          <Boton onClick={revisar} disabled={!archivo || importar.isPending}>
            <Upload className="size-4" />
            {importar.isPending && !plan ? "Revisando…" : "Revisar"}
          </Boton>
        </div>
      </Tarjeta>

      {importar.isPending && <Cargando que="Cruzando el libro contra la base" />}

      {plan && (
        <Tarjeta className="mb-5 space-y-4">
          {plan.yaAplicado && cambios === 0 ? (
            <Aviso tono="ok" titulo="Este libro ya está cargado">
              No hay nada nuevo que aplicar.
            </Aviso>
          ) : null}
          <Tabla>
            <thead>
              <tr>
                <Th>Etapa</Th>
                {TIPOS.map(([, nombre]) => <Th key={nombre} className="text-right">{nombre}</Th>)}
              </tr>
            </thead>
            <tbody>
              {ETAPAS.map(([clave, nombre]) => (
                <tr key={clave}>
                  <Td className="font-medium">{nombre}</Td>
                  {TIPOS.map(([tipo]) => (
                    <Td key={tipo} className="text-right tabular">{plan.resumen[clave]?.[tipo] || ""}</Td>
                  ))}
                </tr>
              ))}
            </tbody>
          </Tabla>

          <details>
            <summary className="cursor-pointer text-sm font-medium text-marca">Ver el detalle fila por fila</summary>
            <pre className="mt-3 max-h-[28rem] overflow-auto whitespace-pre-wrap rounded-xl bg-fondo p-4 text-xs leading-relaxed">
              {plan.reporte}
            </pre>
          </details>

          {!plan.yaAplicado && cambios > 0 && (
            <div className="flex flex-wrap items-center gap-3 border-t border-borde pt-4">
              <Boton onClick={aplicar} disabled={importar.isPending}>
                Aplicar {cambios} cambios
              </Boton>
              <p className="text-xs text-texto-suave">
                Se vuelve a cruzar en el momento: si alguien cargó algo después de revisar, no se duplica.
              </p>
            </div>
          )}
        </Tarjeta>
      )}

      <h2 className="mb-2 mt-6 text-sm font-semibold">Importaciones anteriores</h2>
      {historial.isLoading ? (
        <Cargando />
      ) : (
        <Tabla>
          <thead>
            <tr><Th>#</Th><Th>Archivo</Th><Th>Cuándo</Th><Th>Quién</Th><Th className="text-right">Filas ligadas</Th></tr>
          </thead>
          <tbody>
            {(historial.data ?? []).map((i) => (
              <tr key={i.id}>
                <Td>{i.id}</Td>
                <Td>{i.archivo} <Insignia tono="neutro">{i.hash}</Insignia></Td>
                <Td className="text-xs">{fechaHora(i.importado_at)}</Td>
                <Td className="text-xs">{i.importado_por ?? "—"}</Td>
                <Td className="text-right tabular">{i.enlaces} / {i.filas}</Td>
              </tr>
            ))}
          </tbody>
        </Tabla>
      )}
    </>
  );
}
