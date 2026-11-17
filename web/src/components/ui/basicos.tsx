import { cn } from "@/lib/cn";
import { Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, HTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

// ---------- Botón ----------
type Variante = "primario" | "secundario" | "fantasma" | "peligro";
const VARIANTES: Record<Variante, string> = {
  primario: "bg-acento text-[#062520] hover:bg-[#7ff0dc] font-semibold",
  secundario: "bg-panel-2 text-texto border border-borde-fuerte hover:border-texto-3",
  fantasma: "text-texto-2 hover:text-texto hover:bg-panel-2",
  peligro: "bg-transparent text-critico border border-critico/40 hover:bg-critico/10",
};

export function Boton({ variante = "secundario", cargando, className, children, disabled, ...p }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variante?: Variante; cargando?: boolean }) {
  return (
    <button
      {...p}
      disabled={disabled || cargando}
      className={cn("inline-flex h-9 items-center justify-center gap-2 rounded-lg px-3.5 text-sm transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-50", VARIANTES[variante], className)}
    >
      {cargando && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

// ---------- Tarjeta ----------
export function Tarjeta({ className, ...p }: HTMLAttributes<HTMLDivElement>) {
  return <div {...p} className={cn("rounded-tarjeta border border-borde bg-panel", className)} />;
}

export function TituloTarjeta({ titulo, descripcion, accion, className }:
  { titulo: string; descripcion?: ReactNode; accion?: ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-start justify-between gap-4 px-5 pt-4", className)}>
      <div className="min-w-0">
        <h3 className="text-[15px] font-semibold text-texto">{titulo}</h3>
        {descripcion && <p className="mt-0.5 text-[13px] text-texto-3">{descripcion}</p>}
      </div>
      {accion}
    </div>
  );
}

// ---------- Campos ----------
const CAMPO = "h-9 w-full rounded-lg border border-borde-fuerte bg-fondo px-3 text-sm text-texto placeholder:text-texto-3 " +
  "focus:border-acento focus:outline-none disabled:opacity-50";

export function Entrada({ className, ...p }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...p} className={cn(CAMPO, className)} />;
}

export function Selector({ className, children, ...p }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...p} className={cn(CAMPO, "appearance-none bg-[length:16px] bg-[right_10px_center] bg-no-repeat pr-9", className)}
    style={{ backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23a9b1c3' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")" }}>
    {children}</select>;
}

export function Etiqueta({ children, htmlFor, className }: { children: ReactNode; htmlFor?: string; className?: string }) {
  return <label htmlFor={htmlFor} className={cn("mb-1.5 block text-[13px] font-medium text-texto-2", className)}>{children}</label>;
}

// ---------- Insignia ----------
type Tono = "neutro" | "acento" | "ok" | "alerta" | "serio" | "critico";
const TONOS: Record<Tono, string> = {
  neutro: "bg-panel-2 text-texto-2 border-borde-fuerte",
  acento: "bg-acento-tenue text-acento border-acento/30",
  ok: "bg-ok/10 text-ok border-ok/30",
  alerta: "bg-alerta/10 text-alerta border-alerta/30",
  serio: "bg-serio/10 text-serio border-serio/30",
  critico: "bg-critico/10 text-critico border-critico/30",
};
export function Insignia({ tono = "neutro", children, className }: { tono?: Tono; children: ReactNode; className?: string }) {
  return <span className={cn("inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium whitespace-nowrap", TONOS[tono], className)}>{children}</span>;
}

export function tonoRiesgo(nivel: string | null | undefined): Tono {
  switch ((nivel ?? "").toLowerCase()) {
    case "bajo": return "ok";
    case "medio": return "alerta";
    case "alto": return "serio";
    case "muy alto": case "crítico": case "critico": return "critico";
    default: return "neutro";
  }
}

// ---------- Esqueleto y estados ----------
export function Esqueleto({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-panel-2", className)} />;
}

export function Vacio({ icono, titulo, texto, accion }: { icono?: ReactNode; titulo: string; texto?: ReactNode; accion?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-14 text-center">
      {icono && <div className="mb-1 text-texto-3">{icono}</div>}
      <p className="font-medium text-texto">{titulo}</p>
      {texto && <p className="max-w-md text-sm text-texto-3">{texto}</p>}
      {accion && <div className="mt-3">{accion}</div>}
    </div>
  );
}

export function Aviso({ tono = "alerta", icono, titulo, children, className }:
  { tono?: "ok" | "alerta" | "critico" | "acento"; icono?: ReactNode; titulo?: string; children?: ReactNode; className?: string }) {
  const c = { ok: "border-ok/30 bg-ok/5", alerta: "border-alerta/30 bg-alerta/5", critico: "border-critico/30 bg-critico/5", acento: "border-acento/30 bg-acento-tenue" }[tono];
  const t = { ok: "text-ok", alerta: "text-alerta", critico: "text-critico", acento: "text-acento" }[tono];
  return (
    <div role="status" className={cn("flex gap-3 rounded-xl border px-4 py-3 text-sm", c, className)}>
      {icono && <span className={cn("mt-0.5 shrink-0", t)}>{icono}</span>}
      <div className="min-w-0">
        {titulo && <p className={cn("font-medium", t)}>{titulo}</p>}
        {children && <div className="text-texto-2">{children}</div>}
      </div>
    </div>
  );
}
