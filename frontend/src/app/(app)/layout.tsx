"use client";

import { Shell } from "@/components/shell";
import { Cargando } from "@/components/ui";
import { useSesionRequerida } from "@/hooks/sesion";

export default function LayoutApp({ children }: { children: React.ReactNode }) {
  const { yo, cargando } = useSesionRequerida();

  if (cargando) return <Cargando que="Abriendo" />;
  if (!yo) return null; // el hook ya redirige a /login

  return <Shell>{children}</Shell>;
}
