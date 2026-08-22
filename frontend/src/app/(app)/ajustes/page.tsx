"use client";

import Link from "next/link";
import { Bot, CreditCard, KeyRound, Landmark, RefreshCw, Users } from "lucide-react";
import { Insignia, Tarjeta, Titulo } from "@/components/ui";
import { useDatosPago } from "@/hooks/datos";

export default function Ajustes() {
  const datosPago = useDatosPago();
  return (
    <>
      <Titulo>Ajustes</Titulo>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Link href="/ajustes/pagos">
          <Tarjeta className="h-full transition hover:border-marca">
            <div className="flex items-start justify-between">
              <CreditCard className="size-5 text-marca" />
              {datosPago.data && !datosPago.data.completo && (
                <Insignia tono="critico">faltan datos</Insignia>
              )}
            </div>
            <p className="mt-3 font-medium">Datos de pago</p>
            <p className="mt-1 text-xs text-texto-suave">
              Los que se insertan en los recordatorios. Sin ellos no se puede generar
              ninguno.
            </p>
          </Tarjeta>
        </Link>

        <Link href="/ajustes/usuarios">
          <Tarjeta className="h-full transition hover:border-marca">
            <Users className="size-5 text-marca" />
            <p className="mt-3 font-medium">Usuarios</p>
            <p className="mt-1 text-xs text-texto-suave">
              Creá el perfil de un socio o vendedor. Cada uno elige su contraseña al
              entrar.
            </p>
          </Tarjeta>
        </Link>

        <Link href="/ajustes/politica">
          <Tarjeta className="h-full transition hover:border-marca">
            <Landmark className="size-5 text-marca" />
            <p className="mt-3 font-medium">Política de precios</p>
            <p className="mt-1 text-xs text-texto-suave">Márgenes, comisión y vigencias con historial.</p>
          </Tarjeta>
        </Link>

        <Link href="/ajustes/tasas">
          <Tarjeta className="h-full transition hover:border-marca">
            <RefreshCw className="size-5 text-marca" />
            <p className="mt-3 font-medium">Tasas de cambio</p>
            <p className="mt-1 text-xs text-texto-suave">Snapshots diarios y correcciones documentadas.</p>
          </Tarjeta>
        </Link>

        <Link href="/ajustes/automatizaciones">
          <Tarjeta className="h-full transition hover:border-marca">
            <Bot className="size-5 text-marca" />
            <p className="mt-3 font-medium">Automatizaciones</p>
            <p className="mt-1 text-xs text-texto-suave">Conciliación, sesiones y captura de tasa.</p>
          </Tarjeta>
        </Link>

        <Link href="/ajustes/mi-clave">
          <Tarjeta className="h-full transition hover:border-marca">
            <KeyRound className="size-5 text-marca" />
            <p className="mt-3 font-medium">Mi contraseña</p>
            <p className="mt-1 text-xs text-texto-suave">
              Cambiarla cierra tus otras sesiones.
            </p>
          </Tarjeta>
        </Link>
      </div>
    </>
  );
}
