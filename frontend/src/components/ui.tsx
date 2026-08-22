"use client";

import clsx from "clsx";
import type { ReactNode } from "react";
import { CLASES_TONO, type Tono } from "@/lib/semaforo";

/** Piezas de interfaz. Chicas, sin librería: son ocho y se leen enteras. */

export function Tarjeta({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={clsx(
        "rounded-2xl border border-borde/90 bg-superficie p-4 shadow-[0_12px_34px_-28px_rgba(45,52,58,0.55)] sm:p-5",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function Insignia({
  children,
  tono = "neutro",
  titulo,
}: {
  children: ReactNode;
  tono?: Tono;
  titulo?: string;
}) {
  return (
    <span
      title={titulo}
      className={clsx(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        CLASES_TONO[tono],
      )}
    >
      {children}
    </span>
  );
}

type VarianteBoton = "primario" | "secundario" | "peligro" | "fantasma";

const CLASES_BOTON: Record<VarianteBoton, string> = {
  primario: "bg-marca text-white shadow-sm hover:bg-navegacion",
  secundario: "border border-borde bg-superficie hover:border-acento/60 hover:bg-acento-suave/45",
  peligro: "bg-critico text-white hover:opacity-90",
  fantasma: "hover:bg-fondo",
};

export function Boton({
  children,
  variante = "primario",
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variante?: VarianteBoton }) {
  return (
    <button
      {...props}
      className={clsx(
        "inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold",
        "transition duration-150 disabled:cursor-not-allowed disabled:opacity-50 active:scale-[0.985]",
        CLASES_BOTON[variante],
        className,
      )}
    >
      {children}
    </button>
  );
}

export function Campo({
  etiqueta,
  error,
  ayuda,
  children,
  requerido,
}: {
  etiqueta: string;
  error?: string;
  ayuda?: ReactNode;
  children: ReactNode;
  requerido?: boolean;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium">
        {etiqueta}
        {requerido && <span className="text-critico"> *</span>}
      </span>
      {children}
      {ayuda && !error && (
        <span className="mt-1 block text-xs text-texto-suave">{ayuda}</span>
      )}
      {error && <span className="mt-1 block text-xs text-critico">{error}</span>}
    </label>
  );
}

export const claseInput =
  "min-h-11 w-full rounded-xl border border-borde bg-white px-3.5 py-2.5 text-base sm:text-sm " +
  "outline-none transition placeholder:text-texto-suave/70 focus:border-acento focus:ring-3 focus:ring-acento/15";

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={clsx(claseInput, props.className)} />;
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={clsx(claseInput, props.className)} />;
}

/** Un aviso. `tono` decide el color, y el color significa urgencia. */
export function Aviso({
  tono = "ambar",
  titulo,
  children,
  accion,
}: {
  tono?: Tono;
  titulo: string;
  children?: ReactNode;
  accion?: ReactNode;
}) {
  return (
    <div className={clsx("rounded-xl border p-4", CLASES_TONO[tono])}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold">{titulo}</p>
          {children && <div className="mt-1 text-sm opacity-90">{children}</div>}
        </div>
        {accion}
      </div>
    </div>
  );
}

export function Vacio({ titulo, detalle }: { titulo: string; detalle?: string }) {
  return (
    <div className="rounded-xl border border-dashed border-borde p-8 text-center">
      <p className="font-medium">{titulo}</p>
      {detalle && <p className="mt-1 text-sm text-texto-suave">{detalle}</p>}
    </div>
  );
}

export function Cargando({ que = "Cargando" }: { que?: string }) {
  return (
    <div className="flex items-center gap-2 p-6 text-sm text-texto-suave">
      <span className="size-4 animate-spin rounded-full border-2 border-borde border-t-marca" />
      {que}…
    </div>
  );
}

export function Titulo({
  children,
  detalle,
  accion,
}: {
  children: ReactNode;
  detalle?: ReactNode;
  accion?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="marca-serif text-2xl font-semibold tracking-tight sm:text-[1.75rem]">{children}</h1>
        {detalle && <p className="mt-1 text-sm text-texto-suave">{detalle}</p>}
      </div>
      {accion}
    </div>
  );
}

/** Tabla con scroll horizontal propio: el cuerpo de la página nunca se desplaza. */
export function Tabla({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-2xl border border-borde bg-superficie shadow-[0_12px_34px_-30px_rgba(45,52,58,0.5)]">
      <table className="w-full min-w-[40rem] text-sm">{children}</table>
    </div>
  );
}

export function Th({
  children,
  className,
  ...props
}: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      {...props}
      className={clsx(
        "border-b border-borde px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-texto-suave",
        className,
      )}
    >
      {children}
    </th>
  );
}

export function Td({
  children,
  className,
  ...props
}: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td
      {...props}
      className={clsx("border-b border-borde/60 px-3 py-2 align-middle", className)}
    >
      {children}
    </td>
  );
}
