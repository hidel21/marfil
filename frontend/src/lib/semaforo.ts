import type { Semaforo, Severidad } from "./tipos";

/**
 * El color significa algo, y significa lo mismo en todas las pantallas.
 *
 * Está en un solo módulo a propósito: si cada componente elige su rojo, el rojo deja
 * de querer decir "esto hay que atenderlo hoy".
 */

export type Tono = "critico" | "ambar" | "ok" | "neutro" | "marca";

export const CLASES_TONO: Record<Tono, string> = {
  critico: "bg-critico-suave text-critico border-critico/30",
  ambar: "bg-ambar-suave text-ambar border-ambar/30",
  ok: "bg-ok-suave text-ok border-ok/30",
  neutro: "bg-fondo text-texto-suave border-borde",
  marca: "bg-marca-suave text-marca border-marca/30",
};

export const TONO_SEMAFORO: Record<Semaforo, Tono> = {
  incobrable: "critico",
  moroso: "critico",
  vencido: "ambar",
  por_vencer: "marca",
  al_dia: "ok",
};

export const ETIQUETA_SEMAFORO: Record<Semaforo, string> = {
  incobrable: "Incobrable",
  moroso: "Moroso",
  vencido: "Vencido",
  por_vencer: "Por vencer",
  al_dia: "Al día",
};

/** Qué significa cada estado, en una frase. Va en el tooltip de la insignia. */
export const EXPLICACION_SEMAFORO: Record<Semaforo, string> = {
  incobrable: "Más de 90 días de atraso. Sale de la cobranza esperada, no del libro.",
  moroso: "Más de 15 días de atraso.",
  vencido: "Entre 1 y 15 días de atraso.",
  por_vencer:
    "Vence en los próximos 3 días. Es el único momento en que avisar evita la mora en vez de perseguirla.",
  al_dia: "Sin saldo, o todavía no vence.",
};

export const TONO_SEVERIDAD: Record<Severidad, Tono> = {
  critica: "critico",
  alta: "ambar",
  media: "neutro",
};

export function tonoPorMora(dias: number): Tono {
  if (dias > 15) return "critico";
  if (dias > 0) return "ambar";
  return "ok";
}
