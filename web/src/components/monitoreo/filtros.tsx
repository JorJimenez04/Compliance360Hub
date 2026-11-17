"use client";

import { CalendarRange, Check } from "lucide-react";
import { Entrada } from "@/components/ui/basicos";
import { fecha, sumarDias } from "@/lib/formato";
import type { Opciones } from "@/lib/tipos";
import { cn } from "@/lib/cn";

export type Periodo = "30d" | "90d" | "12m" | "todo" | "personalizado";

export interface Filtros { periodo: Periodo; desde: string; hasta: string; estados: string[] }

const PERIODOS: { id: Periodo; nombre: string }[] = [
  { id: "30d", nombre: "30 días" }, { id: "90d", nombre: "90 días" }, { id: "12m", nombre: "12 meses" },
  { id: "todo", nombre: "Todo" }, { id: "personalizado", nombre: "Personalizado" },
];

/** Los períodos se cuentan hacia atrás desde el último dato cargado, no desde hoy. */
export function filtrosDesdeUrl(p: URLSearchParams, op: Opciones | null): Filtros | null {
  if (!op?.fecha_min || !op.fecha_max) return null;
  const periodo = (PERIODOS.find((x) => x.id === p.get("periodo"))?.id ?? "90d") as Periodo;
  const max = op.fecha_max, min = op.fecha_min;
  const acotar = (d: string) => (d < min ? min : d > max ? max : d);
  let desde = min, hasta = max;
  if (periodo === "30d") desde = sumarDias(max, -29);
  else if (periodo === "90d") desde = sumarDias(max, -89);
  else if (periodo === "12m") desde = sumarDias(max, -364);
  else if (periodo === "personalizado") { desde = p.get("desde") ?? min; hasta = p.get("hasta") ?? max; }
  desde = acotar(desde); hasta = acotar(hasta);
  if (desde > hasta) [desde, hasta] = [hasta, desde];
  const estados = p.getAll("estado").filter((e) => op.estados.includes(e));
  return { periodo, desde, hasta, estados };
}

export function paramsFiltros(f: Filtros) {
  return { desde: f.desde, hasta: f.hasta, estados: f.estados };
}

export function BarraFiltros({ filtros, opciones, onCambio }:
  { filtros: Filtros | null; opciones: Opciones; onCambio: (f: Partial<Filtros>) => void }) {
  if (!filtros) return null;
  const alternar = (e: string) => onCambio({ ...filtros,
    estados: filtros.estados.includes(e) ? filtros.estados.filter((x) => x !== e) : [...filtros.estados, e] });

  return (
    <div className="flex flex-col gap-3 rounded-tarjeta border border-borde bg-panel px-4 py-3 xl:flex-row xl:items-center xl:justify-between">
      <div className="flex flex-wrap items-center gap-2">
        <CalendarRange className="size-4 text-texto-3" aria-hidden />
        <div className="flex rounded-lg border border-borde-fuerte p-0.5" role="group" aria-label="Período">
          {PERIODOS.map((p) => (
            <button key={p.id} onClick={() => onCambio({ ...filtros, periodo: p.id })} aria-pressed={filtros.periodo === p.id}
              className={cn("rounded-md px-2.5 py-1 text-[13px] transition-colors",
                filtros.periodo === p.id ? "bg-panel-2 font-medium text-texto" : "text-texto-3 hover:text-texto-2")}>
              {p.nombre}
            </button>
          ))}
        </div>
        {filtros.periodo === "personalizado" ? (
          <div className="flex items-center gap-2">
            <Entrada type="date" aria-label="Desde" className="h-8 w-auto" min={opciones.fecha_min!} max={opciones.fecha_max!}
              value={filtros.desde} onChange={(e) => e.target.value && onCambio({ ...filtros, desde: e.target.value })} />
            <span className="text-texto-3">a</span>
            <Entrada type="date" aria-label="Hasta" className="h-8 w-auto" min={opciones.fecha_min!} max={opciones.fecha_max!}
              value={filtros.hasta} onChange={(e) => e.target.value && onCambio({ ...filtros, hasta: e.target.value })} />
          </div>
        ) : (
          <span className="text-[13px] text-texto-3">{fecha(filtros.desde)} – {fecha(filtros.hasta)}</span>
        )}
      </div>

      {opciones.estados.length > 1 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-[13px] text-texto-3">Estado</span>
          {opciones.estados.map((e) => {
            const activo = filtros.estados.includes(e);
            return (
              <button key={e} onClick={() => alternar(e)} aria-pressed={activo}
                className={cn("inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[13px] transition-colors",
                  activo ? "border-acento/40 bg-acento-tenue text-acento" : "border-borde-fuerte text-texto-3 hover:text-texto-2")}>
                {activo && <Check className="size-3" aria-hidden />}{e}
              </button>
            );
          })}
          {filtros.estados.length > 0 && (
            <button onClick={() => onCambio({ ...filtros, estados: [] })} className="ml-1 text-[13px] text-texto-3 underline-offset-2 hover:underline">Todos</button>
          )}
        </div>
      )}
    </div>
  );
}
