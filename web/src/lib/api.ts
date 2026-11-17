// Cliente de la API. La sesión viaja en una cookie HttpOnly; los cambios llevan la cabecera X-C360.

export class ErrorApi extends Error {
  constructor(public estado: number, mensaje: string) {
    super(mensaje);
  }
}

type Params = Record<string, string | number | boolean | string[] | null | undefined>;

export function query(params: Params = {}): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => q.append(k, x));
    else q.append(k, String(v));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

async function leerError(r: Response): Promise<string> {
  try {
    const d = await r.json();
    if (typeof d?.detail === "string") return d.detail;
  } catch {}
  if (r.status === 401) return "Su sesión terminó. Ingrese de nuevo.";
  if (r.status === 403) return "No tiene permiso para esta acción.";
  if (r.status >= 500) return "El servidor no pudo completar la solicitud. Intente de nuevo en unos minutos.";
  return "No se pudo completar la solicitud.";
}

export async function api<T>(ruta: string, opciones: RequestInit = {}): Promise<T> {
  const metodo = (opciones.method ?? "GET").toUpperCase();
  const cabeceras = new Headers(opciones.headers);
  if (metodo !== "GET") cabeceras.set("X-C360", "1");
  if (opciones.body && !(opciones.body instanceof FormData) && !cabeceras.has("Content-Type"))
    cabeceras.set("Content-Type", "application/json");

  let r: Response;
  try {
    r = await fetch(ruta, { ...opciones, headers: cabeceras, credentials: "same-origin", cache: "no-store" });
  } catch {
    throw new ErrorApi(0, "Sin conexión con el servidor. Revise su red e intente de nuevo.");
  }
  if (r.status === 401 && typeof window !== "undefined" && !ruta.startsWith("/api/auth/")) {
    window.location.href = `/login?siguiente=${encodeURIComponent(window.location.pathname + window.location.search)}`;
  }
  if (!r.ok) throw new ErrorApi(r.status, await leerError(r));
  return (await r.json()) as T;
}

export const enviar = <T,>(ruta: string, cuerpo?: unknown, metodo = "POST") =>
  api<T>(ruta, { method: metodo, body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo) });
