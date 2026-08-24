"use client";

import clsx from "clsx";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import {
  AlertTriangle,
  BadgeDollarSign,
  BarChart3,
  Boxes,
  ClipboardCheck,
  FileText,
  HandCoins,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquare,
  Package,
  ReceiptText,
  Settings,
  ShoppingCart,
  Users,
  WalletCards,
  X,
} from "lucide-react";
import { useCalidad, useDatosPago } from "@/hooks/datos";
import { useSesion } from "@/hooks/sesion";
import type { Rol } from "@/lib/tipos";
import { Insignia } from "./ui";

type Grupo = "Principal" | "Operación" | "Gestión";
type Entrada = {
  ruta: string;
  etiqueta: string;
  icono: ReactNode;
  roles: Rol[];
  grupo: Grupo;
};

const OPERADORES: Rol[] = ["admin", "vendedor"];
const TODOS: Rol[] = ["admin", "vendedor", "afiliado"];

const NAVEGACION: Entrada[] = [
  { ruta: "/dashboard", etiqueta: "Resumen", icono: <LayoutDashboard />, roles: TODOS, grupo: "Principal" },
  { ruta: "/cobranza", etiqueta: "Cobranza", icono: <BadgeDollarSign />, roles: OPERADORES, grupo: "Principal" },
  { ruta: "/ventas/nueva", etiqueta: "Registrar venta", icono: <ShoppingCart />, roles: OPERADORES, grupo: "Principal" },
  { ruta: "/abonos/nuevo", etiqueta: "Registrar abono", icono: <HandCoins />, roles: OPERADORES, grupo: "Principal" },
  { ruta: "/recordatorios", etiqueta: "Recordatorios", icono: <MessageSquare />, roles: OPERADORES, grupo: "Principal" },
  { ruta: "/clientes", etiqueta: "Clientes", icono: <Users />, roles: OPERADORES, grupo: "Operación" },
  { ruta: "/productos", etiqueta: "Productos", icono: <Package />, roles: OPERADORES, grupo: "Operación" },
  { ruta: "/compras", etiqueta: "Compras", icono: <Boxes />, roles: ["admin"], grupo: "Operación" },
  { ruta: "/gastos", etiqueta: "Gastos", icono: <ReceiptText />, roles: ["admin"], grupo: "Operación" },
  { ruta: "/finanzas", etiqueta: "Finanzas", icono: <BarChart3 />, roles: ["admin"], grupo: "Gestión" },
  { ruta: "/socios", etiqueta: "Socios", icono: <WalletCards />, roles: ["admin"], grupo: "Gestión" },
  { ruta: "/reportes", etiqueta: "Reportes", icono: <FileText />, roles: ["admin"], grupo: "Gestión" },
  { ruta: "/auditoria", etiqueta: "Auditoría", icono: <ClipboardCheck />, roles: ["admin"], grupo: "Gestión" },
  { ruta: "/ajustes", etiqueta: "Ajustes", icono: <Settings />, roles: ["admin"], grupo: "Gestión" },
];

const MOVIL = ["/dashboard", "/ventas/nueva", "/cobranza", "/abonos/nuevo"];

function activo(rutaActual: string, ruta: string) {
  return rutaActual === ruta || rutaActual.startsWith(`${ruta}/`);
}

export function Shell({ children }: { children: ReactNode }) {
  const { yo, salir } = useSesion();
  const ruta = usePathname();
  const [menuAbierto, setMenuAbierto] = useState(false);
  const calidad = useCalidad(yo?.rol === "admin");
  const datosPago = useDatosPago(yo?.rol === "admin");

  const criticas = (calidad.data ?? []).filter((t) => t.severidad === "critica");
  const entradas = NAVEGACION.filter((e) => yo && e.roles.includes(yo.rol));
  const accesosMoviles = entradas.filter((e) => MOVIL.includes(e.ruta));

  return (
    <div className="min-h-dvh md:grid md:grid-cols-[16rem_minmax(0,1fr)]">
      <aside className="sticky top-0 hidden h-dvh flex-col border-r border-white/10 bg-navegacion text-white md:flex">
        <Link href="/dashboard" className="mx-4 mt-4 rounded-2xl bg-[#fffdf2] px-4 py-2.5">
          <Image src="/brand/marfil-logo.png" alt="Marfil Parfum de l’Âme" width={220} height={132} className="mx-auto h-16 w-full object-contain" priority />
        </Link>
        <p className="px-6 pt-3 text-[10px] font-semibold uppercase tracking-[0.22em] text-white/45">Gestión del negocio</p>

        <nav className="mt-4 flex-1 overflow-y-auto px-3 pb-5">
          {(["Principal", "Operación", "Gestión"] as Grupo[]).map((grupo) => {
            const delGrupo = entradas.filter((e) => e.grupo === grupo);
            if (!delGrupo.length) return null;
            return (
              <div key={grupo} className="mb-5">
                <p className="mb-1.5 px-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-white/40">{grupo}</p>
                <div className="space-y-1">
                  {delGrupo.map((e) => <EntradaNavegacion key={e.ruta} entrada={e} activa={activo(ruta, e.ruta)} criticas={criticas.length} />)}
                </div>
              </div>
            );
          })}
        </nav>

        {yo && (
          <div className="border-t border-white/10 p-4">
            <div className="flex items-center gap-3">
              <div className="grid size-9 place-items-center rounded-full bg-acento text-sm font-bold text-white">{yo.nombre.slice(0, 1).toUpperCase()}</div>
              <div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold">{yo.nombre}</p><p className="text-xs capitalize text-white/55">{yo.rol}</p></div>
              <button onClick={salir} title="Cerrar sesión" className="rounded-xl p-2 text-white/60 hover:bg-white/10 hover:text-white"><LogOut className="size-4" /></button>
            </div>
          </div>
        )}
      </aside>

      <div className="min-w-0">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-borde bg-superficie/95 px-4 backdrop-blur md:hidden">
          <Link href="/dashboard" aria-label="Ir al resumen"><Image src="/brand/marfil-logo.png" alt="Marfil" width={132} height={52} className="h-11 w-28 object-contain" priority /></Link>
          <button onClick={() => setMenuAbierto(true)} className="grid size-11 place-items-center rounded-xl border border-borde bg-white" aria-label="Abrir menú"><Menu className="size-5" /></button>
        </header>

        <main className="safe-bottom mx-auto w-full max-w-[92rem] p-4 sm:p-6 lg:p-8">
          {datosPago.data && !datosPago.data.completo && yo?.rol === "admin" && (
            <Link href="/ajustes/pagos" className="mb-5 block">
              <div className="flex items-center gap-2 rounded-2xl border border-critico/25 bg-critico-suave p-3 text-sm text-critico shadow-sm">
                <AlertTriangle className="size-4 shrink-0" /><span className="min-w-0 flex-1"><strong>Faltan datos de pago.</strong> Sin ellos no se generan recordatorios.</span><Insignia tono="critico">Completar</Insignia>
              </div>
            </Link>
          )}
          {children}
        </main>
      </div>

      <nav className="fixed inset-x-0 bottom-0 z-30 grid border-t border-borde bg-superficie/97 px-2 pt-1.5 backdrop-blur md:hidden" style={{ gridTemplateColumns: `repeat(${accesosMoviles.length + 1}, minmax(0, 1fr))`, paddingBottom: "max(.4rem, env(safe-area-inset-bottom))" }}>
        {accesosMoviles.map((e) => (
          <Link key={e.ruta} href={e.ruta} className={clsx("flex min-h-14 flex-col items-center justify-center gap-1 rounded-xl text-[10px] font-medium", activo(ruta, e.ruta) ? "text-acento" : "text-texto-suave")}>
            <span className="[&>svg]:size-5">{e.icono}</span><span className="max-w-full truncate">{e.etiqueta.replace("Registrar ", "")}</span>
          </Link>
        ))}
        <button onClick={() => setMenuAbierto(true)} className="flex min-h-14 flex-col items-center justify-center gap-1 rounded-xl text-[10px] font-medium text-texto-suave"><Menu className="size-5" />Más</button>
      </nav>

      {menuAbierto && (
        <div className="fixed inset-0 z-50 bg-navegacion/45 backdrop-blur-sm md:hidden" onClick={() => setMenuAbierto(false)}>
          <div className="absolute inset-y-0 right-0 w-[min(22rem,88vw)] overflow-y-auto bg-superficie p-4 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b border-borde pb-4"><div><p className="marca-serif text-lg font-semibold">Marfil</p><p className="text-xs text-texto-suave">{yo?.nombre}</p></div><button onClick={() => setMenuAbierto(false)} className="grid size-11 place-items-center rounded-xl border border-borde" aria-label="Cerrar menú"><X className="size-5" /></button></div>
            <nav className="py-4">
              {entradas.map((e) => (
                <Link key={e.ruta} href={e.ruta} onClick={() => setMenuAbierto(false)} className={clsx("mb-1 flex min-h-12 items-center gap-3 rounded-xl px-3 text-sm font-medium [&>svg]:size-5", activo(ruta, e.ruta) ? "bg-acento-suave text-marca" : "text-texto-suave hover:bg-fondo")}>
                  {e.icono}<span className="flex-1">{e.etiqueta}</span>{e.ruta === "/auditoria" && criticas.length > 0 && <Insignia tono="critico">{criticas.length}</Insignia>}
                </Link>
              ))}
            </nav>
            <button onClick={salir} className="flex min-h-12 w-full items-center gap-3 rounded-xl border border-borde px-3 text-sm font-medium text-texto-suave"><LogOut className="size-5" />Cerrar sesión</button>
          </div>
        </div>
      )}
    </div>
  );
}

function EntradaNavegacion({ entrada: e, activa, criticas }: { entrada: Entrada; activa: boolean; criticas: number }) {
  return (
    <Link href={e.ruta} className={clsx("flex min-h-10 items-center gap-3 rounded-xl px-3 text-sm transition [&>svg]:size-[1.1rem]", activa ? "bg-white/12 font-semibold text-[#fff7df]" : "text-white/65 hover:bg-white/7 hover:text-white")}>
      {e.icono}<span className="flex-1">{e.etiqueta}</span>{e.ruta === "/auditoria" && criticas > 0 && <span className="grid min-w-5 place-items-center rounded-full bg-critico px-1 text-[10px] font-bold text-white">{criticas}</span>}
    </Link>
  );
}
