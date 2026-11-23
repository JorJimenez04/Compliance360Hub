"use client";

import { Fragment, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Plus } from "lucide-react";
import { Entrada, Insignia, tonoRiesgo } from "@/components/ui/basicos";
import type { ActividadCiiu, ModeloCat, Nivel } from "@/lib/tipos";
import { cn } from "@/lib/cn";

const ORDEN: Record<Nivel, number> = { Alto: 2, Medio: 1, Bajo: 0 };

/** Riesgo sugerido de un conjunto de modelos: el más alto de ellos. */
export function riesgoDe(modelos: ModeloCat[], codigos: string[]): Nivel | null {
  return modelos.filter((m) => codigos.includes(m.codigo))
    .reduce<Nivel | null>((max, m) => (!max || ORDEN[m.riesgo_sugerido] > ORDEN[max] ? m.riesgo_sugerido : max), null);
}

/**
 * Modelos de negocio en lista, agrupados, con su clasificación de riesgo y el porqué.
 * Si se pasan las actividades CIIU elegidas, cada modelo marcado muestra su origen
 * («Por CIIU 6619» o «Manual») y arriba aparecen los modelos que esas actividades sugieren.
 */
export default function SelectorModelos({ modelos, valor, onCambio, disabled, actividades, documentos }: {
  modelos: ModeloCat[]; valor: string[]; onCambio: (v: string[]) => void; disabled?: boolean;
  actividades?: ActividadCiiu[]; documentos?: { codigo: string; nombre: string }[];
}) {
  const [filtro, setFiltro] = useState("");
  const [nivel, setNivel] = useState<Nivel | "">("");
  const [soloMarcados, setSoloMarcados] = useState(false);
  const [abierto, setAbierto] = useState<string | null>(null);
  const porCodigo = useMemo(() => Object.fromEntries(modelos.map((m) => [m.codigo, m])), [modelos]);
  const nombreDoc = useMemo(() => Object.fromEntries((documentos ?? []).map((d) => [d.codigo, d.nombre])), [documentos]);

  // Origen: qué actividad elegida aplica (principal) o sugiere cada modelo
  const origen = useMemo(() => {
    const o: Record<string, string[]> = {};
    for (const a of actividades ?? []) if (a.principal) (o[a.principal] ??= []).push(a.codigo);
    return o;
  }, [actividades]);
  const sugeridos = useMemo(() => {
    const s: { codigo: string; ciiu: string }[] = [];
    for (const a of actividades ?? [])
      for (const c of [a.principal, ...a.sugeridos])
        if (c && !valor.includes(c) && !s.some((x) => x.codigo === c) && porCodigo[c]) s.push({ codigo: c, ciiu: a.codigo });
    return s;
  }, [actividades, valor, porCodigo]);

  const grupos = useMemo(() => {
    const f = filtro.trim().toLowerCase();
    const visibles = modelos.filter((m) => (!f || m.nombre.toLowerCase().includes(f) || m.grupo.toLowerCase().includes(f)
      || m.por_que.toLowerCase().includes(f)) && (!nivel || m.riesgo_sugerido === nivel) && (!soloMarcados || valor.includes(m.codigo)));
    return [...new Set(visibles.map((m) => m.grupo))].map((g) => ({ grupo: g, modelos: visibles.filter((m) => m.grupo === g) }));
  }, [modelos, filtro, nivel, soloMarcados, valor]);

  const alternar = (c: string) => onCambio(valor.includes(c) ? valor.filter((x) => x !== c) : [...valor, c]);
  const riesgo = riesgoDe(modelos, valor);
  const chip = (activo: boolean) => cn("rounded-md border px-2.5 py-1 text-xs transition-colors",
    activo ? "border-acento bg-acento-tenue text-texto" : "border-borde-fuerte text-texto-3 hover:text-texto-2");

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Entrada placeholder="Buscar modelo de negocio…" value={filtro} onChange={(e) => setFiltro(e.target.value)} className="max-w-xs" />
        {(["", "Alto", "Medio", "Bajo"] as const).map((n) => (
          <button key={n || "todos"} type="button" className={chip(nivel === n)} onClick={() => setNivel(n)}>{n || "Todos"}</button>
        ))}
        <button type="button" className={chip(soloMarcados)} onClick={() => setSoloMarcados(!soloMarcados)}>Solo seleccionados</button>
        <span className="ml-auto text-sm text-texto-3">
          Seleccionados: <span className="cifra text-texto">{valor.length}</span>
          {riesgo && <> → riesgo sugerido <Insignia tono={tonoRiesgo(riesgo)}>{riesgo}</Insignia></>}
        </span>
      </div>

      {sugeridos.length > 0 && !disabled && (
        <div className="rounded-lg border border-borde bg-fondo/50 px-3 py-2.5">
          <p className="mb-2 text-xs text-texto-3">Otros modelos que sugieren sus actividades CIIU. Márquelos si aplican:</p>
          <div className="flex flex-wrap gap-2">
            {sugeridos.map((s) => (
              <button key={s.codigo} type="button" onClick={() => alternar(s.codigo)}
                className="inline-flex items-center gap-1.5 rounded-md border border-dashed border-borde-fuerte px-2 py-1 text-xs text-texto-2 hover:border-acento hover:text-texto">
                <Plus className="size-3" aria-hidden />{porCodigo[s.codigo].nombre}
                <Insignia tono={tonoRiesgo(porCodigo[s.codigo].riesgo_sugerido)} className="px-1.5 py-0 text-[10px]">{porCodigo[s.codigo].riesgo_sugerido}</Insignia>
                <span className="text-texto-3">CIIU {s.ciiu}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="max-h-[480px] overflow-y-auto rounded-lg border border-borde">
        <table className="w-full text-[13px]">
          <thead className="sticky top-0 z-10 bg-panel">
            <tr className="text-left text-texto-3">
              <th className="w-8 px-3 py-2" /><th className="px-2 py-2 font-medium">Modelo de negocio</th>
              <th className="px-2 py-2 font-medium">Riesgo</th><th className="hidden px-2 py-2 font-medium lg:table-cell">Por qué</th>
              <th className="px-2 py-2 font-medium">Monitoreo</th><th className="px-3 py-2 font-medium">Origen</th>
            </tr>
          </thead>
          <tbody>
            {grupos.map((g) => (
              <Fragment key={g.grupo}>
                <tr><td colSpan={6} className="bg-fondo/60 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-texto-3">{g.grupo}</td></tr>
                {g.modelos.map((m) => {
                  const marcado = valor.includes(m.codigo);
                  const ver = abierto === m.codigo;
                  return (
                    <Fragment key={m.codigo}>
                      <tr className={cn("border-t border-borde/60", marcado && "bg-acento-tenue/40")}>
                        <td className="px-3 py-2">
                          <input type="checkbox" checked={marcado} disabled={disabled} onChange={() => alternar(m.codigo)}
                            aria-label={`Seleccionar ${m.nombre}`} className="size-4 accent-[var(--color-acento)]" />
                        </td>
                        <td className="px-2 py-2">
                          <button type="button" onClick={() => setAbierto(ver ? null : m.codigo)}
                            className="inline-flex items-center gap-1 text-left text-texto hover:text-acento">
                            {ver ? <ChevronDown className="size-3.5 shrink-0" aria-hidden /> : <ChevronRight className="size-3.5 shrink-0" aria-hidden />}
                            {m.nombre}
                          </button>
                        </td>
                        <td className="px-2 py-2"><Insignia tono={tonoRiesgo(m.riesgo_sugerido)}>{m.riesgo_sugerido}</Insignia></td>
                        <td className="hidden max-w-md px-2 py-2 text-texto-3 lg:table-cell"><span className="line-clamp-1" title={m.por_que}>{m.por_que}</span></td>
                        <td className="px-2 py-2 capitalize text-texto-2">{m.monitoreo.join(" · ")}</td>
                        <td className="px-3 py-2 text-xs">
                          {!marcado ? null : origen[m.codigo]
                            ? <span className="text-acento">Por CIIU {origen[m.codigo].join(", ")}</span>
                            : <span className="text-texto-3">Manual</span>}
                        </td>
                      </tr>
                      {ver && (
                        <tr className="bg-fondo/40">
                          <td />
                          <td colSpan={5} className="space-y-2 px-2 pb-3 pt-1 text-[13px] text-texto-2">
                            <p><span className="text-texto-3">Por qué {m.riesgo_sugerido.toLowerCase()}: </span>{m.por_que}</p>
                            {m.senales_alerta.length > 0 && <div><p className="text-texto-3">Señales de alerta:</p>
                              <ul className="ml-4 list-disc">{m.senales_alerta.map((s) => <li key={s}>{s}</li>)}</ul></div>}
                            {m.documentos.length > 0 && <p><span className="text-texto-3">Documentos adicionales: </span>
                              {m.documentos.map((d) => nombreDoc[d] ?? d).join(" · ")}</p>}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </Fragment>
            ))}
            {!grupos.length && <tr><td colSpan={6} className="px-3 py-6 text-center text-texto-3">Ningún modelo coincide con el filtro.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
