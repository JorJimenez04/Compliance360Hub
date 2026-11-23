"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Search, X } from "lucide-react";
import { Esqueleto, Etiqueta } from "@/components/ui/basicos";
import { useDatos } from "@/lib/useDatos";
import type { ActividadCiiu, CatalogoCiiu, ModeloCat } from "@/lib/tipos";
import { cn } from "@/lib/cn";
import SelectorModelos from "./selector-modelos";

const RANURAS = ["Actividad principal", "Actividad secundaria", "Otra actividad 1", "Otra actividad 2"];

/** Lista oficial CIIU (se carga una vez por sesión del navegador). */
let enMemoria: CatalogoCiiu | null = null;
export function useCiiu() {
  const { datos, error } = useDatos<CatalogoCiiu>(enMemoria ? null : "/api/catalogo/ciiu");
  if (datos) enMemoria = datos;
  const cat = enMemoria ?? datos;
  const porCodigo = useMemo(() => Object.fromEntries((cat?.actividades ?? []).map((a) => [a.codigo, a])), [cat]);
  return { catalogo: cat, porCodigo, error };
}

/**
 * Aplica los modelos automáticos al cambiar las actividades:
 *  - una actividad nueva agrega su modelo principal;
 *  - una actividad quitada retira su modelo principal si ninguna otra actividad lo aplica.
 * Los modelos marcados a mano no se tocan.
 */
export function aplicarCiiu(antes: string[], despues: string[], modelos: string[], porCodigo: Record<string, ActividadCiiu>): string[] {
  const principal = (c: string) => porCodigo[c]?.principal ?? null;
  const siguen = new Set(despues.map(principal).filter(Boolean));
  let r = modelos.filter((m) => !antes.filter((c) => !despues.includes(c)).some((c) => principal(c) === m) || siguen.has(m));
  for (const c of despues.filter((c) => !antes.includes(c))) {
    const p = principal(c);
    if (p && !r.includes(p)) r = [...r, p];
  }
  return r;
}

function Buscador({ id, actividad, excluir, nombreModelo, lista, onElegir, disabled }: {
  id: string; actividad: ActividadCiiu | null; excluir: string[]; nombreModelo: Record<string, string>;
  lista: ActividadCiiu[]; onElegir: (codigo: string | null) => void; disabled?: boolean;
}) {
  const [texto, setTexto] = useState("");
  const [abierto, setAbierto] = useState(false);
  const [activo, setActivo] = useState(0);
  const caja = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const cerrar = (e: MouseEvent) => { if (!caja.current?.contains(e.target as Node)) setAbierto(false); };
    document.addEventListener("mousedown", cerrar);
    return () => document.removeEventListener("mousedown", cerrar);
  }, []);
  const opciones = useMemo(() => {
    const t = texto.trim().toLowerCase();
    if (!t) return [];
    const norm = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
    const q = norm(t);
    return lista.filter((a) => !excluir.includes(a.codigo) && (a.codigo.startsWith(t) || norm(a.descripcion).includes(q))).slice(0, 12);
  }, [texto, lista, excluir]);
  const elegir = (c: string) => { onElegir(c); setTexto(""); setAbierto(false); };

  if (actividad)
    return (
      <div className="flex min-h-10 items-start gap-2 rounded-lg border border-borde-fuerte bg-fondo px-3 py-2 text-sm">
        <span className="cifra font-medium text-acento">{actividad.codigo}</span>
        <span className="flex-1 text-texto-2">{actividad.descripcion}</span>
        {!disabled && <button type="button" onClick={() => onElegir(null)} aria-label={`Quitar actividad ${actividad.codigo}`}
          className="text-texto-3 hover:text-critico"><X className="size-4" /></button>}
      </div>
    );
  return (
    <div ref={caja} className="relative">
      <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-texto-3" aria-hidden />
      <input id={id} disabled={disabled} value={texto} autoComplete="off" placeholder="Código o descripción (ej. 6619 o pagos)"
        onChange={(e) => { setTexto(e.target.value); setAbierto(true); setActivo(0); }} onFocus={() => setAbierto(true)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setActivo((a) => Math.min(a + 1, opciones.length - 1)); }
          if (e.key === "ArrowUp") { e.preventDefault(); setActivo((a) => Math.max(a - 1, 0)); }
          if (e.key === "Enter" && opciones[activo]) { e.preventDefault(); elegir(opciones[activo].codigo); }
          if (e.key === "Escape") setAbierto(false);
        }}
        className="h-10 w-full rounded-lg border border-borde-fuerte bg-fondo pl-9 pr-3 text-sm text-texto placeholder:text-texto-3 focus:border-acento focus:outline-none disabled:opacity-60" />
      {abierto && texto.trim() && (
        <ul role="listbox" className="absolute z-30 mt-1 max-h-72 w-full overflow-y-auto rounded-lg border border-borde-fuerte bg-panel-2 py-1 shadow-xl">
          {!opciones.length && <li className="px-3 py-2 text-sm text-texto-3">Sin coincidencias en la CIIU.</li>}
          {opciones.map((a, i) => (
            <li key={a.codigo} role="option" aria-selected={i === activo}>
              <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => elegir(a.codigo)} onMouseEnter={() => setActivo(i)}
                className={cn("flex w-full gap-3 px-3 py-2 text-left text-sm", i === activo ? "bg-acento-tenue" : "")}>
                <span className="cifra w-10 shrink-0 font-medium text-acento">{a.codigo}</span>
                <span className="flex-1 text-texto-2">{a.descripcion}</span>
                {a.principal && <span className="max-w-[40%] shrink-0 truncate text-xs text-texto-3">→ {nombreModelo[a.principal]}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Las cuatro actividades del RUT y, debajo, los modelos de negocio (automáticos por CIIU y manuales). */
export default function ActividadYModelos({ modelos, documentos, actividades, modelosNegocio, onCambio, disabled, idBase = "ciiu" }: {
  modelos: ModeloCat[]; documentos?: { codigo: string; nombre: string }[];
  actividades: string[]; modelosNegocio: string[];
  onCambio: (c: { actividades: string[]; modelos: string[] }) => void; disabled?: boolean; idBase?: string;
}) {
  const { catalogo, porCodigo, error } = useCiiu();
  const nombreModelo = useMemo(() => Object.fromEntries(modelos.map((m) => [m.codigo, m.nombre])), [modelos]);
  if (error) return <p className="text-sm text-critico">No se pudo cargar la lista CIIU: {error}</p>;
  if (!catalogo) return <Esqueleto className="h-40" />;

  const poner = (i: number, codigo: string | null) => {
    const nuevas = [...actividades];
    if (codigo) nuevas[i] = codigo; else nuevas.splice(i, 1);
    const limpias = nuevas.filter(Boolean);
    onCambio({ actividades: limpias, modelos: aplicarCiiu(actividades, limpias, modelosNegocio, porCodigo) });
  };
  const elegidas = actividades.map((c) => porCodigo[c]).filter(Boolean);
  const visibles = Math.min(4, actividades.length + (disabled ? 0 : 1));

  return (
    <div className="space-y-5">
      <div>
        <div className="grid gap-3 md:grid-cols-2">
          {RANURAS.slice(0, Math.max(visibles, 1)).map((nombre, i) => {
            const a = actividades[i] ? porCodigo[actividades[i]] ?? null : null;
            return (
              <div key={nombre}>
                <Etiqueta htmlFor={`${idBase}-${i}`}>{nombre} (CIIU)</Etiqueta>
                <Buscador id={`${idBase}-${i}`} actividad={a} excluir={actividades} nombreModelo={nombreModelo}
                  lista={catalogo.actividades} onElegir={(c) => poner(i, c)} disabled={disabled} />
                {a && (a.principal
                  ? <p className="mt-1 text-xs text-texto-3">Aplica: <span className="text-texto-2">{nombreModelo[a.principal]}</span>
                      {a.sugeridos.length > 0 && <> · sugiere {a.sugeridos.length} más</>}</p>
                  : a.sugeridos.length ? <p className="mt-1 text-xs text-texto-3">Actividad amplia: elija entre los modelos sugeridos.</p>
                  : <p className="mt-1 text-xs text-texto-3">Sin modelo asociado: márquelo a mano.</p>)}
              </div>
            );
          })}
        </div>
        <p className="mt-2 text-xs text-texto-3">Fuente: {catalogo.fuente}.</p>
      </div>
      <div>
        <Etiqueta>Modelos de negocio</Etiqueta>
        <SelectorModelos modelos={modelos} documentos={documentos} valor={modelosNegocio} actividades={elegidas}
          onCambio={(m) => onCambio({ actividades, modelos: m })} disabled={disabled} />
      </div>
    </div>
  );
}
