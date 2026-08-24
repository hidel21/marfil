"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Aviso, Boton, Campo, Input, Tarjeta, Titulo } from "@/components/ui";
import { useCambiarPassword, useSesion } from "@/hooks/sesion";
import { FalloApi } from "@/lib/api";

export default function MiClave() {
  const router = useRouter();
  const { yo } = useSesion();
  const cambiar = useCambiarPassword();
  const [actual, setActual] = useState("");
  const [nueva, setNueva] = useState("");
  const [repetir, setRepetir] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (nueva !== repetir) {
      setError("Las contraseñas nuevas no coinciden.");
      return;
    }
    try {
      await cambiar.mutateAsync({ password_actual: actual, password_nueva: nueva });
      toast.success("Contraseña cambiada", {
        description: "Tus otras sesiones se cerraron.",
      });
      router.push("/cobranza");
    } catch (err) {
      const fallo = err instanceof FalloApi ? err : null;
      setError(fallo?.mensaje ?? "No se pudo cambiar.");
    }
  }

  return (
    <>
      <Titulo detalle="Cambiarla cierra tus otras sesiones.">Mi contraseña</Titulo>

      {yo?.debe_cambiar_password && (
        <div className="mb-4">
          <Aviso tono="ambar" titulo="Te toca elegir una contraseña propia">
            La cuenta se creó con un código de un solo uso. Poné la tuya.
          </Aviso>
        </div>
      )}

      <Tarjeta className="max-w-sm">
        <form onSubmit={onSubmit} className="space-y-4">
          <Campo etiqueta="Contraseña actual">
            <Input
              type="password"
              value={actual}
              onChange={(e) => setActual(e.target.value)}
              autoComplete="current-password"
            />
          </Campo>
          <Campo etiqueta="Nueva" requerido ayuda="Al menos 8 caracteres.">
            <Input
              type="password"
              value={nueva}
              onChange={(e) => setNueva(e.target.value)}
              autoComplete="new-password"
              minLength={8}
              required
            />
          </Campo>
          <Campo etiqueta="Repetila" requerido>
            <Input
              type="password"
              value={repetir}
              onChange={(e) => setRepetir(e.target.value)}
              autoComplete="new-password"
              required
            />
          </Campo>
          {error && <Aviso tono="critico" titulo={error} />}
          <Boton type="submit" disabled={cambiar.isPending} className="w-full">
            {cambiar.isPending ? "Cambiando…" : "Cambiar"}
          </Boton>
        </form>
      </Tarjeta>
    </>
  );
}
