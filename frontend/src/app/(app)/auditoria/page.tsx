"use client";

import Link from "next/link";
import { Check, History, TriangleAlert } from "lucide-react";
import { Dinero } from "@/components/dinero";
import {
  Cargando,
  Insignia,
  Tabla,
  Tarjeta,
  Td,
  Th,
  Titulo,
} from "@/components/ui";
import { useCalidad, useConciliacion, useFugaPrecio } from "@/hooks/datos";
import { CLASES_TONO, TONO_SEVERIDAD } from "@/lib/semaforo";
import type { TarjetaCalidad } from "@/lib/tipos";

/**
 * Auditoría.
 *
 * Tres bloques: qué está mal (calidad), si las cifras cuadran (conciliación), y cuánto
 * cuesta el problema más caro (fuga de precio).
 *
 * La conciliación muestra el saldo **almacenado y el calculado uno al lado del otro,
 * siempre**. Es el pedido de "auditar fácilmente" comprimido en una pantalla: el
 * almacenado es sobre el que actúa el negocio, el calculado es la verdad.
 */
export default function Auditoria() {
  const calidad = useCalidad();
  const ventas = useConciliacion("ventas");
  const pagos = useConciliacion("pagos");
  const stock = useConciliacion("stock");
  const fuga = useFugaPrecio();

  return (
    <>
      <Titulo detalle="Qué está mal, si las cifras cuadran, y cuánto cuesta." accion={<Link href="/auditoria/actividad" className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-borde bg-superficie px-4 text-sm font-semibold"><History className="size-4" />Actividad</Link>}>
        Auditoría
      </Titulo>

      <section className="mb-8">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-texto-suave">
          Calidad de los datos
        </h2>
        {calidad.isLoading ? (
          <Cargando />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {(calidad.data ?? []).map((t) => (
              <TarjetaProblema key={t.clave} tarjeta={t} />
            ))}
          </div>
        )}
      </section>

      <section className="mb-8">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-texto-suave">
          Conciliación
        </h2>
        <div className="grid gap-3 sm:grid-cols-3">
          {[
            { titulo: "Ventas", datos: ventas.data, detalle: "Saldo guardado vs. el libro de pagos" },
            { titulo: "Pagos", datos: pagos.data, detalle: "Monto ÷ tasa vs. el monto en dólares" },
            { titulo: "Stock", datos: stock.data, detalle: "Stock guardado vs. sus movimientos" },
          ].map((b) => (
            <Tarjeta key={b.titulo}>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-medium">{b.titulo}</p>
                  <p className="mt-0.5 text-xs text-texto-suave">{b.detalle}</p>
                </div>
                {b.datos && (
                  <Insignia tono={b.datos.ok ? "ok" : "critico"}>
                    {b.datos.ok ? <Check className="size-3" /> : <TriangleAlert className="size-3" />}
                    {b.datos.ok ? "cuadra" : `${b.datos.filas_descuadradas} mal`}
                  </Insignia>
                )}
              </div>
              {b.datos && (
                <p className="mt-2 text-xs text-texto-suave">
                  {b.datos.filas_revisadas} revisadas
                </p>
              )}
            </Tarjeta>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-texto-suave">
          Ventas cobradas bajo la política
        </h2>
        <p className="mb-3 text-xs text-texto-suave">
          Convierte un hallazgo puntual de un informe en un número vivo del que alguien
          es responsable.
        </p>
        {fuga.isLoading ? (
          <Cargando />
        ) : fuga.data ? (
          <>
            <div className="mb-3 flex flex-wrap items-center gap-3">
              <Tarjeta className="min-w-40">
                <p className="text-xs text-texto-suave">Fuga total</p>
                <p className="mt-1 text-2xl font-semibold">
                  <Dinero valor={fuga.data.fuga_total_usd} />
                </p>
                <p className="mt-1 text-xs text-texto-suave">
                  en {fuga.data.total_lineas} líneas
                </p>
              </Tarjeta>
              {fuga.data.por_vendedor.map((v) => (
                <Tarjeta key={v.vendedor} className="min-w-36">
                  <p className="text-xs text-texto-suave">{v.vendedor}</p>
                  <p className="mt-1 text-lg font-semibold">
                    <Dinero valor={v.fuga_usd} />
                  </p>
                  <p className="mt-1 text-xs text-texto-suave">{v.lineas} líneas</p>
                </Tarjeta>
              ))}
            </div>

            <Tabla>
              <thead>
                <tr>
                  <Th>Venta</Th>
                  <Th>Cliente</Th>
                  <Th>Producto</Th>
                  <Th>Nivel</Th>
                  <Th className="text-right">Cobrado</Th>
                  <Th className="text-right">Política</Th>
                  <Th className="text-right">Fuga</Th>
                  <Th>Motivo</Th>
                </tr>
              </thead>
              <tbody>
                {fuga.data.items.slice(0, 40).map((i, idx) => (
                  <tr key={idx}>
                    <Td className="font-mono text-xs">{String(i.codigo)}</Td>
                    <Td>{String(i.cliente)}</Td>
                    <Td className="max-w-40 truncate">{String(i.producto_tecleado)}</Td>
                    <Td>
                      <Insignia>{String(i.moneda_cotizacion)}</Insignia>
                    </Td>
                    <Td className="text-right">
                      <Dinero valor={String(i.cobrado_usd)} />
                    </Td>
                    <Td className="text-right">
                      <Dinero valor={String(i.politica_usd)} />
                    </Td>
                    <Td className="text-right font-medium text-ambar">
                      <Dinero valor={String(i.fuga_usd)} />
                    </Td>
                    <Td className="max-w-48 truncate text-xs text-texto-suave">
                      {i.motivo_desviacion ? String(i.motivo_desviacion) : "—"}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Tabla>
          </>
        ) : null}
      </section>
    </>
  );
}

function TarjetaProblema({ tarjeta: t }: { tarjeta: TarjetaCalidad }) {
  const tono = TONO_SEVERIDAD[t.severidad];
  return (
    <Link href={t.ruta} className="block">
      <div className={`rounded-xl border p-4 transition hover:opacity-90 ${CLASES_TONO[tono]}`}>
        <div className="flex items-baseline justify-between gap-2">
          <p className="text-3xl font-semibold tabular">{t.cantidad}</p>
          {t.monto_usd && (
            <p className="text-sm font-medium">
              <Dinero valor={t.monto_usd} />
            </p>
          )}
        </div>
        <p className="mt-2 font-medium">{t.etiqueta}</p>
        <p className="mt-1 text-xs opacity-90">{t.explicacion}</p>
        <p className="mt-3 text-xs font-medium underline">{t.accion} →</p>
      </div>
    </Link>
  );
}
