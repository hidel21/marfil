"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api, fijarToken, tokenActual } from "@/lib/api";
import type { Sesion, Yo } from "@/lib/tipos";

/**
 * Estado de la sesión.
 *
 * Al montar se intenta un refresh: el access token vive en memoria y se pierde al
 * recargar, pero la cookie HttpOnly del refresh sobrevive. Sin este paso, recargar la
 * página echaría al usuario aunque su sesión siga válida.
 */

type Contexto = {
  yo: Yo | null;
  cargando: boolean;
  entrar: (email: string, password: string) => Promise<Sesion>;
  salir: () => Promise<void>;
};

const ctx = createContext<Contexto | null>(null);

export function ProveedorSesion({ children }: { children: ReactNode }) {
  const [listoParaConsultar, setListo] = useState(false);
  const qc = useQueryClient();
  const router = useRouter();

  useEffect(() => {
    let vivo = true;
    (async () => {
      if (!tokenActual()) await api.refrescar();
      if (vivo) setListo(true);
    })();
    return () => {
      vivo = false;
    };
  }, []);

  const consulta = useQuery({
    queryKey: ["yo"],
    queryFn: () => api.get<Yo>("/auth/yo"),
    enabled: listoParaConsultar,
    retry: false,
    staleTime: 5 * 60_000,
  });

  const entrar = async (email: string, password: string) => {
    const sesion = await api.publico.post<Sesion>("/auth/login", { email, password });
    fijarToken(sesion.access_token);
    await qc.invalidateQueries({ queryKey: ["yo"] });
    return sesion;
  };

  const salir = async () => {
    try {
      await api.post("/auth/logout");
    } finally {
      fijarToken(null);
      qc.clear();
      router.push("/login");
    }
  };

  return (
    <ctx.Provider
      value={{
        yo: consulta.data ?? null,
        cargando: !listoParaConsultar || consulta.isLoading,
        entrar,
        salir,
      }}
    >
      {children}
    </ctx.Provider>
  );
}

export function useSesion() {
  const valor = useContext(ctx);
  if (!valor) throw new Error("useSesion necesita estar dentro de ProveedorSesion");
  return valor;
}

/** Redirige a /login si no hay sesión. Devuelve `yo` cuando la hay. */
export function useSesionRequerida() {
  const { yo, cargando } = useSesion();
  const router = useRouter();
  useEffect(() => {
    if (!cargando && !yo) router.replace("/login");
  }, [cargando, yo, router]);
  return { yo, cargando };
}

export function useCambiarPassword() {
  return useMutation({
    mutationFn: (datos: { password_actual: string; password_nueva: string }) =>
      api.post("/auth/cambiar-password", datos),
  });
}
