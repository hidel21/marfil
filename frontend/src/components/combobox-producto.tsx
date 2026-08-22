"use client";

import { useEffect, useRef, useState } from "react";
import { Plus, Search, TriangleAlert } from "lucide-react";
import { Dinero } from "@/components/dinero";
import { Insignia, claseInput } from "@/components/ui";
import { useAltaRapida, useSugerenciasProducto } from "@/hooks/datos";
import type { SugerenciaProducto } from "@/lib/tipos";

/**
 * El selector de producto que **acepta texto arbitrario**.
 *
 * Es el requerimiento explícito: se tiene que poder registrar una venta de algo que no
 * está en el catálogo. Todo selector cerrado pelea con eso, así que está escrito a
 * mano.
 *
 * Y trae la guardia de similitud: si lo tecleado se parece a algo que ya existe, lo
 * ofrece antes que crear un duplicado. Ataca el problema de las 21 grafías del mismo
 * perfume en la tecla, no en una limpieza un año después.
 */
export function ComboboxProducto({
  moneda,
  onElegir,
}: {
  moneda: string;
  onElegir: (p: { producto_id: number; nombre: string; precio_politica_usd: string | null }) => void;
}) {
  const [texto, setTexto] = useState("");
  const [abierto, setAbierto] = useState(false);
  const contenedor = useRef<HTMLDivElement>(null);
  const sugerencias = useSugerenciasProducto(texto, moneda);
  const alta = useAltaRapida();

  useEffect(() => {
    function fuera(e: MouseEvent) {
      if (!contenedor.current?.contains(e.target as Node)) setAbierto(false);
    }
    document.addEventListener("mousedown", fuera);
    return () => document.removeEventListener("mousedown", fuera);
  }, []);

  const exactos = sugerencias.data?.exactos ?? [];
  const similares = sugerencias.data?.similares ?? [];
  const puedeCrear = Boolean(
    texto.trim().length >= 2 && sugerencias.data && exactos.length === 0,
  );

  function elegir(p: SugerenciaProducto) {
    onElegir({
      producto_id: p.producto_id,
      nombre: p.nombre,
      precio_politica_usd: p.precio_politica_usd,
    });
    setTexto("");
    setAbierto(false);
  }

  async function crear() {
    const nombre = texto.trim();
    const r = await alta.mutateAsync({ nombre });
    onElegir({ producto_id: r.producto_id, nombre: r.nombre, precio_politica_usd: null });
    setTexto("");
    setAbierto(false);
  }

  return (
    <div ref={contenedor} className="relative">
      <div className="relative">
        <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-texto-suave" />
        <input
          className={`${claseInput} pl-9`}
          placeholder="Escribí el nombre del perfume…"
          value={texto}
          onChange={(e) => {
            setTexto(e.target.value);
            setAbierto(true);
          }}
          onFocus={() => setAbierto(true)}
        />
      </div>

      {abierto && texto.trim().length >= 2 && (
        <div className="absolute z-20 mt-1 max-h-80 w-full overflow-y-auto rounded-xl border border-borde bg-superficie shadow-lg">
          {exactos.map((p) => (
            <button
              key={p.producto_id}
              type="button"
              onClick={() => elegir(p)}
              className="flex w-full items-center justify-between gap-3 border-b border-borde/50 px-3 py-2 text-left text-sm hover:bg-fondo"
            >
              <span className="min-w-0">
                <span className="block truncate">{p.nombre}</span>
                <span className="block text-xs text-texto-suave">
                  stock {p.stock}
                  {p.coincide_por_alias && ` · coincide con «${p.coincide_por_alias}»`}
                  {p.estado === "borrador_por_revisar" && " · por revisar"}
                </span>
              </span>
              <span className="shrink-0 text-right text-xs">
                {p.sin_base_de_precio ? (
                  <Insignia tono="ambar">sin costo</Insignia>
                ) : (
                  <Dinero valor={p.precio_politica_usd} />
                )}
              </span>
            </button>
          ))}

          {/* La guardia de similitud, ANTES de la opción de crear. */}
          {puedeCrear && similares.length > 0 && (
            <div className="border-b border-borde/50 bg-ambar-suave px-3 py-2 text-xs text-ambar">
              <p className="flex items-center gap-1 font-medium">
                <TriangleAlert className="size-3" />
                ¿Quisiste decir…?
              </p>
              <div className="mt-1 space-y-1">
                {similares.map((s) => (
                  <button
                    key={s.producto_id}
                    type="button"
                    onClick={() =>
                      onElegir({
                        producto_id: s.producto_id,
                        nombre: s.nombre,
                        precio_politica_usd: null,
                      })
                    }
                    className="block w-full text-left underline"
                  >
                    {s.nombre}
                    {s.ventas > 0 && ` (${s.ventas} ventas)`}
                  </button>
                ))}
              </div>
            </div>
          )}

          {puedeCrear && (
            <button
              type="button"
              onClick={crear}
              disabled={alta.isPending}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-marca hover:bg-marca-suave"
            >
              <Plus className="size-4" />
              Crear «{texto.trim()}»
              <span className="ml-auto text-xs text-texto-suave">
                queda para revisar
              </span>
            </button>
          )}

          {sugerencias.isLoading && (
            <p className="px-3 py-2 text-sm text-texto-suave">Buscando…</p>
          )}
        </div>
      )}
    </div>
  );
}
