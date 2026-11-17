"use client";

import { AlertOctagon, AlertTriangle, ArrowUpRight, CalendarClock, CheckCircle2, Info, ShieldAlert, ShieldCheck } from "lucide-react";
import { Aviso, Esqueleto, Insignia, Tarjeta, TituloTarjeta, tonoRiesgo } from "@/components/ui/basicos";
import { query } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";
import { fecha } from "@/lib/formato";
import type { Alerta, Riesgo } from "@/lib/tipos";
import { cn } from "@/lib/cn";
import { paramsFiltros, type Filtros } from "./filtros";

const sinEmoji = (s: string) => s.replace(/[\p{Extended_Pictographic}️]/gu, "").trim();

const PRIORIDAD: Record<string, { tono: "critico" | "serio" | "alerta" | "neutro"; icono: typeof AlertOctagon; orden: number }> = {
  "Crítica": { tono: "critico", icono: AlertOctagon, orden: 0 },
  "Alta": { tono: "serio", icono: AlertTriangle, orden: 1 },
  "Media": { tono: "alerta", icono: Info, orden: 2 },
  "Baja": { tono: "neutro", icono: Info, orden: 3 },
};

const DIMENSIONES: Record<string, string> = { volumen: "Volumen", frecuencia: "Frecuencia", complejidad: "Complejidad", geografia: "Geografía" };

export default function VistaRiesgo({ empresaId, filtros }: { empresaId: number; filtros: Filtros }) {
  const { datos: r, error, cargando } = useDatos<Riesgo>(`/api/monitoreo/empresas/${empresaId}/riesgo${query(paramsFiltros(filtros))}`);

  if (error) return <Aviso tono="critico" icono={<AlertTriangle className="size-4" />} titulo="No se pudo evaluar el riesgo">{error}</Aviso>;
  if (!r) return <div className="grid gap-5 lg:grid-cols-3">{[0, 1, 2].map((i) => <Esqueleto key={i} className="h-56 rounded-tarjeta" />)}</div>;

  const s = r.scoring;
  const alertas = [...r.alertas].sort((a, b) => (PRIORIDAD[a.prioridad]?.orden ?? 9) - (PRIORIDAD[b.prioridad]?.orden ?? 9));

  return (
    <div className={cn("space-y-5 transition-opacity", cargando && "opacity-60")}>
      <p className="text-[13px] text-texto-3">
        Evaluación automática de los movimientos del período con criterios GAFI, UIAF y operativos. Es un apoyo para el análisis del Oficial de Cumplimiento, no un dictamen.
      </p>

      <div className="grid gap-5 lg:grid-cols-3">
        <Tarjeta className="p-5">
          <p className="text-[13px] text-texto-3">Puntaje de riesgo</p>
          <div className="mt-2 flex items-end gap-3">
            <span className="cifra text-5xl font-semibold leading-none">{s.score_total}</span>
            <span className="pb-1 text-texto-3">/ 100</span>
            <Insignia tono={tonoRiesgo(s.nivel_riesgo)} className="mb-1 ml-auto">Riesgo {s.nivel_riesgo}</Insignia>
          </div>
          <div className="mt-5 space-y-3">
            {([["GAFI", s.score_gafi, "40 %"], ["UIAF", s.score_uiaf, "35 %"], ["Operativo", s.score_operativo, "25 %"]] as const).map(([n, v, p]) => (
              <div key={n}>
                <div className="mb-1 flex justify-between text-[13px]"><span className="text-texto-2">{n} <span className="text-texto-3">· pondera {p}</span></span><span className="cifra">{v}</span></div>
                <div className="h-2 rounded-full bg-panel-2"><div className="h-2 rounded-full bg-acento" style={{ width: `${v}%` }} /></div>
              </div>
            ))}
          </div>
        </Tarjeta>

        <Tarjeta className="p-5">
          <p className="text-[13px] text-texto-3">Decisiones sugeridas</p>
          <ul className="mt-3 space-y-3 text-sm">
            <Bandera activa={r.requiere_escalamiento} si="Escalar al Oficial de Cumplimiento" no="No requiere escalamiento" />
            <Bandera activa={r.requiere_due_diligence_reforzada} si="Aplicar debida diligencia reforzada" no="Debida diligencia estándar" />
            <Bandera activa={alertas.some((a) => a.requiere_reporte_uiaf)} si="Evaluar reporte de operación sospechosa (ROS) a la UIAF" no="Sin indicios para ROS" />
            <Bandera activa={r.matriz_riesgo.apetito_riesgo_superado} si="Supera el apetito de riesgo" no="Dentro del apetito de riesgo" />
          </ul>
          <p className="mt-4 flex items-center gap-2 border-t border-borde pt-3 text-[13px] text-texto-2">
            <CalendarClock className="size-4 text-texto-3" aria-hidden />Próxima revisión: {fecha(r.proximo_review)}
          </p>
        </Tarjeta>

        <Tarjeta>
          <TituloTarjeta titulo="Riesgo inherente y residual" descripcion="Antes y después de los controles (0–100)" />
          <div className="space-y-3 px-5 pb-5 pt-4">
            {Object.keys(r.matriz_riesgo.riesgo_inherente).map((k) => {
              const ri = r.matriz_riesgo.riesgo_inherente[k], rr = r.matriz_riesgo.riesgo_residual[k] ?? 0;
              return (
                <div key={k}>
                  <div className="mb-1 flex justify-between text-[13px]"><span className="text-texto-2">{DIMENSIONES[k] ?? k}</span>
                    <span className="cifra text-texto-3">{ri} <ArrowUpRight className="inline size-3 rotate-90" aria-label="a" /> <span className="text-texto">{rr}</span></span></div>
                  <div className="relative h-2 rounded-full bg-panel-2">
                    <div className="absolute inset-y-0 left-0 rounded-full bg-[#2f3850]" style={{ width: `${ri}%` }} />
                    <div className="absolute inset-y-0 left-0 rounded-full bg-[#3987e5]" style={{ width: `${rr}%` }} />
                  </div>
                </div>
              );
            })}
            <div className="flex gap-4 pt-1 text-[12px] text-texto-3">
              <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm bg-[#2f3850]" />Inherente</span>
              <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm bg-[#3987e5]" />Residual</span>
            </div>
          </div>
        </Tarjeta>
      </div>

      <Tarjeta>
        <TituloTarjeta titulo={`Alertas (${alertas.length})`} descripcion="Ordenadas por prioridad" />
        {alertas.length === 0
          ? <p className="flex items-center gap-2 px-5 py-5 text-sm text-texto-2"><CheckCircle2 className="size-4 text-ok" />No se generaron alertas para este período.</p>
          : <ul className="divide-y divide-borde/70 px-5 pb-2 pt-2">{alertas.map((a) => <FilaAlerta key={a.id_alerta} a={a} />)}</ul>}
      </Tarjeta>

      <div className="grid gap-5 lg:grid-cols-2">
        <Tarjeta>
          <TituloTarjeta titulo="Recomendaciones" />
          <ul className="list-disc space-y-1.5 px-5 pb-5 pl-10 pt-3 text-sm text-texto-2 marker:text-texto-3">
            {r.recomendaciones.map((x, i) => <li key={i}>{sinEmoji(x)}</li>)}
          </ul>
        </Tarjeta>
        <Tarjeta>
          <TituloTarjeta titulo="Controles" />
          <div className="space-y-4 px-5 pb-5 pt-3 text-sm">
            <ul className="space-y-1.5">{r.matriz_riesgo.controles_aplicados.map((c) => (
              <li key={c} className="flex items-start gap-2 text-texto-2"><ShieldCheck className="mt-0.5 size-4 shrink-0 text-ok" aria-label="Aplicado" />{c}</li>))}</ul>
            {r.matriz_riesgo.gaps_control.length > 0 && (
              <ul className="space-y-1.5 border-t border-borde pt-3">{r.matriz_riesgo.gaps_control.map((c) => (
                <li key={c} className="flex items-start gap-2 text-texto-2"><ShieldAlert className="mt-0.5 size-4 shrink-0 text-serio" aria-label="Brecha" />{c}</li>))}</ul>
            )}
          </div>
        </Tarjeta>
      </div>
    </div>
  );
}

function Bandera({ activa, si, no }: { activa: boolean; si: string; no: string }) {
  return (
    <li className="flex items-start gap-2.5">
      {activa ? <AlertTriangle className="mt-0.5 size-4 shrink-0 text-serio" aria-label="Sí" /> : <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-texto-3" aria-label="No" />}
      <span className={activa ? "text-texto" : "text-texto-3"}>{activa ? si : no}</span>
    </li>
  );
}

function FilaAlerta({ a }: { a: Alerta }) {
  const p = PRIORIDAD[a.prioridad] ?? PRIORIDAD.Baja;
  return (
    <li className="flex flex-col gap-2 py-4 md:flex-row md:items-start md:gap-5">
      <div className="flex shrink-0 items-center gap-2 md:w-36">
        <Insignia tono={p.tono}><p.icono className="size-3.5" aria-hidden />{a.prioridad}</Insignia>
        <span className="text-[12px] text-texto-3">{a.tipo}</span>
      </div>
      <div className="min-w-0 flex-1">
        <p className="font-medium">{a.titulo}</p>
        <p className="mt-0.5 text-[13px] text-texto-2">{a.descripcion}</p>
        <p className="mt-1.5 text-[13px] text-texto-3"><span className="text-texto-2">Acción:</span> {a.accion_requerida}</p>
      </div>
      <div className="flex shrink-0 flex-wrap gap-2 md:flex-col md:items-end">
        <span className="text-[12px] text-texto-3">Plazo: {a.dias_para_accion} {a.dias_para_accion === 1 ? "día" : "días"}</span>
        {a.requiere_reporte_uiaf && <Insignia tono="critico">Evaluar ROS</Insignia>}
      </div>
    </li>
  );
}
