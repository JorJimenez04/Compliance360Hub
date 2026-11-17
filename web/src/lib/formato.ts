// Formatos de presentación (es-CO, hora de Colombia)

const ZONA = "America/Bogota";

const cop = new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 });
const num = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 });
const pct1 = new Intl.NumberFormat("es-CO", { style: "percent", maximumFractionDigits: 1 });

export const moneda = (v: number | null | undefined) => (v == null ? "—" : cop.format(v));
export const entero = (v: number | null | undefined) => (v == null ? "—" : num.format(v));
export const porcentaje = (v: number | null | undefined) => (v == null ? "—" : pct1.format(v));

/** $1,2 mil M · $345 M · $12 mil — para ejes y cifras grandes */
export function monedaCorta(v: number | null | undefined): string {
  if (v == null) return "—";
  const a = Math.abs(v), s = v < 0 ? "-" : "";
  const f = (x: number) => x.toLocaleString("es-CO", { maximumFractionDigits: x < 10 ? 1 : 0 });
  if (a >= 1e12) return `${s}$${f(a / 1e12)} B`;
  if (a >= 1e9) return `${s}$${f(a / 1e9)} mil M`;
  if (a >= 1e6) return `${s}$${f(a / 1e6)} M`;
  if (a >= 1e3) return `${s}$${f(a / 1e3)} mil`;
  return `${s}$${f(a)}`;
}

// Las fechas llegan del servidor ya en hora de Colombia y sin zona: se muestran tal cual.
function partes(iso: string) {
  const [f, h = ""] = iso.replace(" ", "T").split("T");
  const [a, m, d] = f.split("-").map(Number);
  return { a, m, d, h: h.slice(0, 5) };
}
const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

export function fecha(iso: string | null | undefined): string {
  if (!iso) return "—";
  const { a, m, d } = partes(iso);
  return `${d} ${MESES[m - 1]} ${a}`;
}
export function fechaHora(iso: string | null | undefined): string {
  if (!iso) return "—";
  const { h } = partes(iso);
  return h ? `${fecha(iso)}, ${h}` : fecha(iso);
}
export function mesCorto(iso: string): string {
  const { a, m } = partes(iso);
  return `${MESES[m - 1]} ${String(a).slice(2)}`;
}
export function diaCorto(iso: string): string {
  const { m, d } = partes(iso);
  return `${d} ${MESES[m - 1]}`;
}

/** "hace 3 h", "hace 2 días" — a partir de una fecha local de Colombia */
export function haceCuanto(iso: string | null | undefined): string {
  if (!iso) return "—";
  const ahoraCol = new Date(new Date().toLocaleString("en-US", { timeZone: ZONA }));
  const t = new Date(iso.replace(" ", "T"));
  const min = Math.round((ahoraCol.getTime() - t.getTime()) / 60000);
  if (min < 1) return "hace un momento";
  if (min < 60) return `hace ${min} min`;
  const h = Math.round(min / 60);
  if (h < 24) return `hace ${h} h`;
  const d = Math.round(h / 24);
  return d === 1 ? "ayer" : `hace ${d} días`;
}

/** YYYY-MM-DD de una fecha, desplazada n días */
export function sumarDias(iso: string, n: number): string {
  const [a, m, d] = iso.split("-").map(Number);
  const t = new Date(Date.UTC(a, m - 1, d + n));
  return t.toISOString().slice(0, 10);
}
