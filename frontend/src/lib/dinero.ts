import Decimal from "decimal.js";

/**
 * Dinero en el frontend.
 *
 * La API manda los montos como string (`"359.67"`) y acá se parsean con decimal.js,
 * nunca con `Number`. No es purismo: en JavaScript `0.1 + 0.2 !== 0.3`, así que sumar
 * montos como floats produce exactamente los descuadres de un centavo que el panel de
 * conciliación tendría que estar detectando. Un total mal calculado en la pantalla es
 * peor que ninguno, porque se le cree.
 */

export type Monto = string;

export function d(valor: Monto | number | Decimal | null | undefined): Decimal {
  if (valor === null || valor === undefined || valor === "") return new Decimal(0);
  return new Decimal(valor as Decimal.Value);
}

/** Suma una lista de montos sin pasar por float. */
export function sumar(valores: Array<Monto | null | undefined>): Decimal {
  return valores.reduce((acc, v) => acc.plus(d(v)), new Decimal(0));
}

const formatoUsd = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const formatoBs = new Intl.NumberFormat("es-VE", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/**
 * `$359.67`. Convención estadounidense: coma de miles, punto decimal.
 *
 * Las dos convenciones conviven en este negocio y mezclarlas es el bug que encontró
 * la auditoría del Excel, así que cada moneda tiene su formateador.
 */
export function usd(valor: Monto | number | Decimal | null | undefined): string {
  return `$${formatoUsd.format(d(valor).toNumber())}`;
}

/** `Bs. 15.679,22`. Convención venezolana: punto de miles, coma decimal. */
export function bs(valor: Monto | number | Decimal | null | undefined): string {
  return `Bs. ${formatoBs.format(d(valor).toNumber())}`;
}

/** El número sin símbolo, para inputs. */
export function plano(valor: Monto | number | Decimal | null | undefined): string {
  return d(valor).toFixed(2);
}

export function porcentaje(
  valor: Monto | number | null | undefined,
  decimales = 1,
): string {
  return `${d(valor).times(100).toFixed(decimales)}%`;
}

/**
 * Reparte un total en cuotas exactas: el resto va a la última.
 *
 * Es la misma regla que el backend (`repartir` en core/dinero.py) para que el preview
 * del plan y lo que se guarda no puedan discrepar.
 */
export function repartir(total: Monto | Decimal, partes: number): Decimal[] {
  if (partes < 1) throw new Error("Hacen falta al menos 1 parte.");
  const t = d(total);
  const base = t.div(partes).toDecimalPlaces(2, Decimal.ROUND_HALF_UP);
  const cuotas = Array.from({ length: partes - 1 }, () => base);
  cuotas.push(t.minus(base.times(partes - 1)).toDecimalPlaces(2, Decimal.ROUND_HALF_UP));
  return cuotas;
}

export { Decimal };
