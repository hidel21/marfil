"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Toaster } from "sonner";
import { FalloApi } from "@/lib/api";
import { ProveedorSesion } from "@/hooks/sesion";

export function Proveedores({ children }: { children: ReactNode }) {
  const [qc] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Un 401 lo resuelve el cliente de API con un refresh; reintentar acá
            // solo duplicaría el pedido. Un 4xx tampoco mejora reintentando.
            retry: (intentos, error) => {
              if (error instanceof FalloApi && error.estado < 500) return false;
              return intentos < 2;
            },
            refetchOnWindowFocus: false,
          },
        },
      }),
  );
  return (
    <QueryClientProvider client={qc}>
      <ProveedorSesion>
        {children}
        <Toaster position="top-right" richColors closeButton />
      </ProveedorSesion>
    </QueryClientProvider>
  );
}
