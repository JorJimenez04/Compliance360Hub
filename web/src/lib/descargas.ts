import { ErrorApi } from "@/lib/api";

/** Descarga un archivo generado por la API (ZIP, PDF…) y lo guarda con el nombre que indica el servidor. */
export async function descargar(ruta: string, nombrePorDefecto: string): Promise<void> {
  let r: Response;
  try {
    r = await fetch(ruta, { credentials: "same-origin", cache: "no-store" });
  } catch {
    throw new ErrorApi(0, "Sin conexión con el servidor. Revise su red e intente de nuevo.");
  }
  if (!r.ok) {
    let mensaje = "No se pudo descargar.";
    try { const j = await r.json(); mensaje = typeof j.detail === "string" ? j.detail : mensaje; } catch { /* sin cuerpo */ }
    throw new ErrorApi(r.status, mensaje);
  }
  const cd = r.headers.get("Content-Disposition") ?? "";
  const m = /filename\*=UTF-8''([^;]+)/i.exec(cd);
  const nombre = m ? decodeURIComponent(m[1]) : nombrePorDefecto;
  const url = URL.createObjectURL(await r.blob());
  const a = document.createElement("a");
  a.href = url; a.download = nombre; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
