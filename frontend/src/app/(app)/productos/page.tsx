"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { Ban, RotateCcw } from "lucide-react";
import { Dinero } from "@/components/dinero";
import {
  Cargando,
  Input,
  Insignia,
  Tabla,
  Td,
  Th,
  Titulo,
  Vacio,
} from "@/components/ui";
import { useSesion } from "@/hooks/sesion";
import { FalloApi, api } from "@/lib/api";
import { useCambiarEstadoProducto } from "@/hooks/datos";
import { useQuery } from "@tanstack/react-query";

type ProductoFila = {
  producto_id: number;
  nombre: string;
  linea: string | null;
  estado: string;
  stock: number;
  costo_usd?: string | null;
  precio_divisa_usd: string | null;
  precio_bcv_usd: string | null;
  sin_base_de_precio: boolean;
};

export default function PaginaProductos() {
  return (
    <Suspense fallback={<Cargando />}>
      <Productos />
    </Suspense>
  );
}

function Productos() {
  const params = useSearchParams();
  const { yo } = useSesion();
  const [q, setQ] = useState("");
  const [sinCosto, setSinCosto] = useState(params.get("sin_costo") === "1");
  // Los descatalogados se piden aparte porque el listado ya no los trae: si
  // siguieran apareciendo al vender, descatalogar no serviría de nada.
  const [verDescatalogados, setVerDescatalogados] = useState(false);

  const productos = useQuery({
    queryKey: ["productos", "lista", q, sinCosto, verDescatalogados],
    queryFn: () =>
      api.get<ProductoFila[]>("/productos", {
        q: q.trim() || undefined,
        sin_costo: sinCosto || undefined,
        incluir_descatalogados: verDescatalogados || undefined,
      }),
    staleTime: 60_000,
  });

  const filas = productos.data ?? [];

  return (
    <>
      <Titulo detalle="Los precios se calculan desde el costo y la política, no se teclean." accion={yo?.rol === "admin" ? <Link href="/productos/revision" className="inline-flex min-h-11 items-center rounded-xl bg-marca px-4 text-sm font-semibold text-white">Revisar pendientes</Link> : undefined}>
        Productos
      </Titulo>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Input
          placeholder="Buscar…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="max-w-xs"
        />
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={sinCosto}
            onChange={(e) => setSinCosto(e.target.checked)}
          />
          Sin costo cargado
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={verDescatalogados}
            onChange={(e) => setVerDescatalogados(e.target.checked)}
          />
          Ver descatalogados
        </label>
      </div>

      {productos.isLoading ? (
        <Cargando />
      ) : filas.length === 0 ? (
        <Vacio titulo="Ningún producto coincide" />
      ) : (
        <Tabla>
          <thead>
            <tr>
              <Th>Producto</Th>
              <Th>Línea</Th>
              <Th className="text-right">Stock</Th>
              {yo?.ve_costos && <Th className="text-right">Costo</Th>}
              <Th className="text-right">Divisa (+70 %)</Th>
              <Th className="text-right">BCV (+120 %)</Th>
              <Th>Estado</Th>
              <Th />
            </tr>
          </thead>
          <tbody>
            {filas.slice(0, 200).map((p) => (
              <tr key={p.producto_id}>
                <Td className="font-medium">{p.nombre}</Td>
                <Td className="text-xs text-texto-suave">{p.linea ?? "—"}</Td>
                <Td className="text-right tabular">{p.stock}</Td>
                {yo?.ve_costos && (
                  <Td className="text-right">
                    <Dinero valor={p.costo_usd ?? null} />
                  </Td>
                )}
                <Td className="text-right">
                  <Dinero valor={p.precio_divisa_usd} />
                </Td>
                <Td className="text-right">
                  <Dinero valor={p.precio_bcv_usd} />
                </Td>
                <Td>
                  {p.sin_base_de_precio ? (
                    <Insignia
                      tono="ambar"
                      titulo="Sin costo no hay precio calculable. Un precio en blanco se ve; un $0,00 se cobra."
                    >
                      sin costo
                    </Insignia>
                  ) : p.estado === "borrador_por_revisar" ? (
                    <Insignia tono="neutro">por revisar</Insignia>
                  ) : p.estado === "descatalogado" ? (
                    <Insignia tono="neutro">descatalogado</Insignia>
                  ) : (
                    <Insignia tono="ok">activo</Insignia>
                  )}
                </Td>
                <Td className="text-right">
                  <BotonDescatalogar
                    id={p.producto_id}
                    nombre={p.nombre}
                    estado={p.estado}
                  />
                </Td>
              </tr>
            ))}
          </tbody>
        </Tabla>
      )}
    </>
  );
}


/**
 * Descatalogar y reactivar un producto.
 *
 * No hay borrado real y es deliberado: las ventas históricas apuntan al producto, y
 * eliminarlo dejaría la conciliación sin cuadrar y los reportes con huecos.
 * Descatalogado deja de ofrecerse al vender, que es lo que se quiere en la práctica,
 * y se puede revertir con un clic.
 */
function BotonDescatalogar({
  id,
  nombre,
  estado,
}: {
  id: number;
  nombre: string;
  estado: string;
}) {
  const cambiar = useCambiarEstadoProducto();
  const fuera = estado === "descatalogado";

  async function alternar() {
    try {
      await cambiar.mutateAsync({ id, estado: fuera ? "activo" : "descatalogado" });
      toast.success(fuera ? `${nombre} vuelve a estar activo` : `${nombre} descatalogado`, {
        description: fuera ? undefined : "Deja de ofrecerse al vender. Sus ventas siguen ahí.",
      });
    } catch (err) {
      const fallo = err instanceof FalloApi ? err : null;
      toast.error(fallo?.mensaje ?? "No se pudo cambiar el estado", {
        description: fallo?.sugerencia,
      });
    }
  }

  return (
    <button
      onClick={alternar}
      disabled={cambiar.isPending}
      title={fuera ? `Reactivar ${nombre}` : `Descatalogar ${nombre}`}
      aria-label={fuera ? `Reactivar ${nombre}` : `Descatalogar ${nombre}`}
      className="text-texto-suave hover:text-marca disabled:opacity-40"
    >
      {fuera ? <RotateCcw className="size-4" /> : <Ban className="size-4" />}
    </button>
  );
}
