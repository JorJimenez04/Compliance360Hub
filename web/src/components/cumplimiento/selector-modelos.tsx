"use client";

import { useMemo, useState } from "react";
import { Entrada, Insignia, tonoRiesgo } from "@/components/ui/basicos";
import type { ModeloCat } from "@/lib/tipos";
import { cn } from "@/lib/cn";

/** Selección múltiple de modelos de negocio, agrupados y con su riesgo sugerido. */
export default function SelectorModelos({ modelos, valor, onCambio, disabled }: {
  modelos: ModeloCat[]; valor: string[]; onCambio: (v: string[]) => void; disabled?: boolean;
}) {
  const [filtro, setFiltro] = useState("");
  const grupos = useMemo(() => {
    const f = filtro.trim().toLowerCase();
    const visibles = modelos.filter((m) => !f || m.nombre.toLowerCase().includes(f) || m.grupo.toLowerCase().includes(f));
    return [...new Set(visibles.map((m) => m.grupo))].map((g) => ({ grupo: g, modelos: visibles.filter((m) => m.grupo === g) }));
  }, [modelos, filtro]);
  const alternar = (c: string) => onCambio(valor.includes(c) ? valor.filter((x) => x !== c) : [...valor, c]);

  return (
    <div className="space-y-3">
      <Entrada placeholder="Buscar modelo de negocio…" value={filtro} onChange={(e) => setFiltro(e.target.value)} className="max-w-sm" />
      <div className="max-h-[420px] space-y-4 overflow-y-auto pr-1">
        {grupos.map((g) => (
          <fieldset key={g.grupo}>
            <legend className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-texto-3">{g.grupo}</legend>
            <div className="flex flex-wrap gap-2">
              {g.modelos.map((m) => {
                const marcado = valor.includes(m.codigo);
                return (
                  <label key={m.codigo} title={m.por_que}
                    className={cn("inline-flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-1.5 text-sm",
                      marcado ? "border-acento bg-acento-tenue text-texto" : "border-borde-fuerte text-texto-2 hover:border-texto-3",
                      disabled && "pointer-events-none opacity-60")}>
                    <input type="checkbox" className="sr-only" checked={marcado} disabled={disabled} onChange={() => alternar(m.codigo)} />
                    {m.nombre}<Insignia tono={tonoRiesgo(m.riesgo_sugerido)} className="px-1.5 py-0 text-[10px]">{m.riesgo_sugerido}</Insignia>
                  </label>
                );
              })}
            </div>
          </fieldset>
        ))}
      </div>
    </div>
  );
}
