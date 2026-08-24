import { differenceInCalendarDays, format, parseISO } from "date-fns";
import { es } from "date-fns/locale";

/**
 * Fechas y textos.
 *
 * Todo en español de Venezuela y con `dd/MM/yyyy`, la convención del negocio. Los días
 * de mora se calculan en días CALENDARIO, no en horas: "vencido hace 3 días" tiene que
 * decir lo mismo a las 9 de la mañana que a las 8 de la noche.
 */

export function fecha(valor: string | null | undefined, patron = "dd/MM/yyyy"): string {
  if (!valor) return "—";
  try {
    return format(parseISO(valor), patron, { locale: es });
  } catch {
    return valor;
  }
}

export function fechaCorta(valor: string | null | undefined): string {
  return fecha(valor, "dd/MM");
}

export function fechaHora(valor: string | null | undefined): string {
  return fecha(valor, "dd/MM/yyyy HH:mm");
}

/** "hace 3 días", "hoy", "en 5 días". */
export function relativo(valor: string | null | undefined): string {
  if (!valor) return "—";
  try {
    const dias = differenceInCalendarDays(new Date(), parseISO(valor));
    if (dias === 0) return "hoy";
    if (dias === 1) return "ayer";
    if (dias === -1) return "mañana";
    if (dias > 0) return `hace ${dias} días`;
    return `en ${Math.abs(dias)} días`;
  } catch {
    return valor;
  }
}

export function plural(n: number, singular: string, plural_?: string): string {
  return n === 1 ? singular : (plural_ ?? `${singular}s`);
}

/** "3 ventas", "1 venta". */
export function contar(n: number, singular: string, plural_?: string): string {
  return `${n} ${plural(n, singular, plural_)}`;
}

export function telefonoLegible(e164: string | null | undefined): string {
  if (!e164) return "—";
  const d = e164.replace(/\D/g, "");
  if (d.startsWith("58") && d.length === 12) {
    return `0${d.slice(2, 5)}-${d.slice(5)}`;
  }
  return e164;
}
