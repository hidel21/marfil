"use client";

import clsx from "clsx";
import { bs, usd, type Monto } from "@/lib/dinero";

/**
 * Un monto en pantalla.
 *
 * Existe como componente para que ningún lugar de la app formatee dinero a mano: las
 * dos convenciones (USD `$359.67`, bolívares `Bs. 15.679,22`) conviven en este negocio
 * y mezclarlas es el bug exacto que encontró la auditoría del Excel.
 */
export function Dinero({
  valor,
  moneda = "USD",
  className,
  cero = "—",
}: {
  valor: Monto | null | undefined;
  moneda?: "USD" | "VES";
  className?: string;
  cero?: string;
}) {
  if (valor === null || valor === undefined) {
    return <span className={clsx("text-texto-suave", className)}>{cero}</span>;
  }
  return (
    <span className={clsx("tabular", className)}>
      {moneda === "USD" ? usd(valor) : bs(valor)}
    </span>
  );
}
