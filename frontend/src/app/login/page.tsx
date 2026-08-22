"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useState } from "react";
import Image from "next/image";
import { LockKeyhole } from "lucide-react";
import { FalloApi } from "@/lib/api";
import { useSesion } from "@/hooks/sesion";
import { Aviso, Boton, Campo, Input, Tarjeta } from "@/components/ui";

export default function Login() {
  const { entrar } = useSesion();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<FalloApi | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setEnviando(true);
    try {
      const sesion = await entrar(email, password);
      router.push(sesion.debe_cambiar_password ? "/ajustes/mi-clave" : "/cobranza");
    } catch (err) {
      setError(err instanceof FalloApi ? err : new FalloApi(0, {}));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <main className="relative grid min-h-dvh place-items-center overflow-hidden p-4 sm:p-6">
      <div className="pointer-events-none absolute -left-24 -top-24 size-80 rounded-full bg-acento-suave blur-3xl" />
      <div className="relative w-full max-w-md">
        <div className="mx-auto mb-5 w-64 rounded-3xl bg-[#fffdf2]/90 px-5 py-2 shadow-sm">
          <Image src="/brand/marfil-logo.png" alt="Marfil Parfum de l’Âme" width={320} height={190} className="h-28 w-full object-contain" priority />
        </div>
        <Tarjeta className="w-full p-6 sm:p-7">
        <div className="mb-6 flex items-center gap-3">
          <div className="grid size-11 place-items-center rounded-2xl bg-acento-suave text-acento"><LockKeyhole className="size-5" /></div>
          <div><h1 className="marca-serif text-xl font-semibold">Bienvenido</h1><p className="text-sm text-texto-suave">Ingresá para gestionar el negocio.</p></div>
        </div>

        <form onSubmit={onSubmit} className="space-y-4">
          <Campo etiqueta="Correo" requerido>
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="username"
              required
            />
          </Campo>
          <Campo etiqueta="Contraseña" requerido>
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </Campo>

          {error && (
            <Aviso tono="critico" titulo={error.mensaje}>
              {error.sugerencia}
            </Aviso>
          )}

          <Boton type="submit" className="w-full" disabled={enviando}>
            {enviando ? "Entrando…" : "Entrar"}
          </Boton>
        </form>

        <p className="mt-4 text-center text-xs text-texto-suave">
          ¿Primera vez?{" "}
          <Link href="/activar" className="text-marca underline">
            Activá tu cuenta con el código
          </Link>
        </p>
        </Tarjeta>
        <p className="mt-4 text-center text-xs text-texto-suave">Acceso privado · Marfil Parfum de l’Âme</p>
      </div>
    </main>
  );
}
