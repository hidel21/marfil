"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, FalloApi } from "@/lib/api";
import { Aviso, Boton, Campo, Input, Tarjeta } from "@/components/ui";

/**
 * Activación de cuenta.
 *
 * El administrador crea el perfil y entrega un código de un solo uso; acá la persona
 * elige su propia contraseña. Es a propósito que la contraseña no viaje nunca en el
 * otro sentido: así no queda en un chat, ni en un log, ni en la memoria de quien creó
 * la cuenta.
 */
export default function Activar() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [codigo, setCodigo] = useState("");
  const [password, setPassword] = useState("");
  const [repetir, setRepetir] = useState("");
  const [error, setError] = useState<FalloApi | string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== repetir) {
      setError("Las contraseñas no coinciden.");
      return;
    }
    setEnviando(true);
    try {
      await api.publico.post("/usuarios/activar", {
        email,
        codigo,
        password_nueva: password,
      });
      router.push("/login?activada=1");
    } catch (err) {
      setError(err instanceof FalloApi ? err : "No se pudo activar la cuenta.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <main className="grid min-h-dvh place-items-center p-6">
      <Tarjeta className="w-full max-w-sm">
        <h1 className="text-lg font-semibold">Activá tu cuenta</h1>
        <p className="mt-1 mb-5 text-sm text-texto-suave">
          Con el código que te pasaron elegís tu contraseña. Nadie más la conoce.
        </p>

        <form onSubmit={onSubmit} className="space-y-4">
          <Campo etiqueta="Tu correo" requerido>
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </Campo>
          <Campo etiqueta="Código de activación" requerido>
            <Input
              value={codigo}
              onChange={(e) => setCodigo(e.target.value.trim())}
              className="font-mono"
              required
            />
          </Campo>
          <Campo
            etiqueta="Tu contraseña nueva"
            requerido
            ayuda="Al menos 8 caracteres."
          >
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
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

          {error && (
            <Aviso
              tono="critico"
              titulo={typeof error === "string" ? error : error.mensaje}
            >
              {typeof error === "string" ? null : error.sugerencia}
            </Aviso>
          )}

          <Boton type="submit" className="w-full" disabled={enviando}>
            {enviando ? "Activando…" : "Activar y entrar"}
          </Boton>
        </form>

        <p className="mt-4 text-center text-xs text-texto-suave">
          <Link href="/login" className="text-marca underline">
            Ya tengo cuenta
          </Link>
        </p>
      </Tarjeta>
    </main>
  );
}
