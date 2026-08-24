/**
 * Cliente de la API.
 *
 * Dos decisiones que vale la pena leer:
 *
 * 1. **El access token vive en memoria, no en localStorage.** El refresh token está en
 *    una cookie HttpOnly que ningún script puede leer, y el access token se pide de
 *    nuevo al recargar. Guardarlo en localStorage sería regalarle una sesión de 30
 *    minutos a cualquier XSS.
 *
 * 2. **Un 401 dispara UN solo refresh y encola el resto.** Sin eso, cinco consultas
 *    en paralelo al expirar el token disparan cinco refresh, y como el refresh rota
 *    el token, cuatro llegan con uno ya usado: el backend lo lee como reuso y cierra
 *    la sesión entera. El síntoma sería "me echa del sistema al azar".
 */

export type ErrorApi = {
  codigo: string;
  mensaje: string;
  campo?: string;
  sugerencia?: string;
  detalles?: Record<string, unknown>;
};

export class FalloApi extends Error {
  readonly estado: number;
  readonly codigo: string;
  readonly campo?: string;
  readonly sugerencia?: string;
  readonly detalles: Record<string, unknown>;

  constructor(estado: number, cuerpo: Partial<ErrorApi>) {
    super(cuerpo.mensaje ?? "Algo no salió bien.");
    this.name = "FalloApi";
    this.estado = estado;
    this.codigo = cuerpo.codigo ?? "DESCONOCIDO";
    this.campo = cuerpo.campo;
    this.sugerencia = cuerpo.sugerencia;
    this.detalles = cuerpo.detalles ?? {};
  }

  /** Alias en español de `message`, para que el código de UI se lea parejo. */
  get mensaje() {
    return this.message;
  }

  get esSesionVencida() {
    return this.estado === 401;
  }
  get esSoloLectura() {
    return this.codigo === "SOLO_LECTURA";
  }
}

let accessToken: string | null = null;
let refrescando: Promise<boolean> | null = null;
const suscriptores = new Set<(t: string | null) => void>();

export function fijarToken(token: string | null) {
  accessToken = token;
  for (const fn of suscriptores) fn(token);
}
export function tokenActual() {
  return accessToken;
}
export function alCambiarToken(fn: (t: string | null) => void) {
  suscriptores.add(fn);
  return () => suscriptores.delete(fn);
}

async function leerCuerpo(res: Response): Promise<Record<string, unknown>> {
  try {
    return (await res.json()) as Record<string, unknown>;
  } catch {
    return {};
  }
}

/** Un solo refresh a la vez; el resto espera el mismo resultado. */
async function refrescarSesion(): Promise<boolean> {
  if (refrescando) return refrescando;
  refrescando = (async () => {
    try {
      const res = await fetch("/api/v1/auth/refresh", {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) {
        fijarToken(null);
        return false;
      }
      const datos = (await res.json()) as { access_token: string };
      fijarToken(datos.access_token);
      return true;
    } catch {
      fijarToken(null);
      return false;
    } finally {
      refrescando = null;
    }
  })();
  return refrescando;
}

type Opciones = {
  metodo?: "GET" | "POST" | "PUT" | "DELETE";
  cuerpo?: unknown;
  params?: Record<string, string | number | boolean | undefined | null>;
  sinAuth?: boolean;
};

export async function llamar<T>(ruta: string, opciones: Opciones = {}): Promise<T> {
  const { metodo = "GET", cuerpo, params, sinAuth = false } = opciones;

  const url = new URL(`/api/v1${ruta}`, window.location.origin);
  for (const [k, v] of Object.entries(params ?? {})) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  }

  const enviar = async (): Promise<Response> =>
    fetch(url.toString(), {
      method: metodo,
      credentials: "include",
      headers: {
        ...(cuerpo !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(!sinAuth && accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      },
      ...(cuerpo !== undefined ? { body: JSON.stringify(cuerpo) } : {}),
    });

  let res = await enviar();

  if (res.status === 401 && !sinAuth) {
    if (await refrescarSesion()) res = await enviar();
  }

  if (!res.ok) throw new FalloApi(res.status, await leerCuerpo(res));
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Descarga autenticada. Conserva el nombre sugerido por el backend. */
export async function descargar(ruta: string): Promise<{ blob: Blob; nombre: string }> {
  const url = new URL(`/api/v1${ruta}`, window.location.origin);
  const enviar = () =>
    fetch(url.toString(), {
      credentials: "include",
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    });
  let res = await enviar();
  if (res.status === 401 && (await refrescarSesion())) res = await enviar();
  if (!res.ok) throw new FalloApi(res.status, await leerCuerpo(res));
  const disposicion = res.headers.get("content-disposition") ?? "";
  const nombre = disposicion.match(/filename="?([^";]+)"?/i)?.[1] ?? "marfil-descarga";
  return { blob: await res.blob(), nombre };
}

export const api = {
  get: <T>(ruta: string, params?: Opciones["params"]) => llamar<T>(ruta, { params }),
  post: <T>(ruta: string, cuerpo?: unknown, params?: Opciones["params"]) =>
    llamar<T>(ruta, { metodo: "POST", cuerpo, params }),
  put: <T>(ruta: string, cuerpo?: unknown) => llamar<T>(ruta, { metodo: "PUT", cuerpo }),
  descargar,
  publico: {
    post: <T>(ruta: string, cuerpo?: unknown) =>
      llamar<T>(ruta, { metodo: "POST", cuerpo, sinAuth: true }),
  },
  refrescar: refrescarSesion,
};
