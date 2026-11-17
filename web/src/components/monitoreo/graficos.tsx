"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { diaCorto, entero, fecha, mesCorto, moneda, monedaCorta, porcentaje } from "@/lib/formato";
import { cn } from "@/lib/cn";

const ACENTO = "#5fe9d0";

// ---------- Evolución (una serie: el título la nombra, sin leyenda) ----------
export function GraficoEvolucion({ serie, granularidad }:
  { serie: { periodo: string; monto: number; pagos: number }[]; granularidad: string }) {
  const etiqueta = (p: string) => (granularidad === "Mensual" ? mesCorto(p) : diaCorto(p));
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer>
        <BarChart data={serie} margin={{ top: 8, right: 8, bottom: 0, left: 4 }} barCategoryGap="22%">
          <CartesianGrid vertical={false} stroke="#232a3b" strokeDasharray="0" />
          <XAxis dataKey="periodo" tickFormatter={etiqueta} tick={{ fill: "#737c91", fontSize: 12 }} axisLine={{ stroke: "#2f3850" }}
            tickLine={false} minTickGap={18} />
          <YAxis tickFormatter={(v) => monedaCorta(v)} tick={{ fill: "#737c91", fontSize: 12 }} axisLine={false} tickLine={false} width={78} />
          <Tooltip cursor={{ fill: "#ffffff0a" }} content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const d = payload[0].payload as { periodo: string; monto: number; pagos: number };
            return (
              <div className="rounded-lg border border-borde-fuerte bg-panel-2 px-3 py-2 text-[13px] shadow-xl">
                <p className="mb-1 text-texto-3">{granularidad === "Mensual" ? mesCorto(d.periodo) : fecha(d.periodo)}{granularidad === "Semanal" && " (semana)"}</p>
                <p className="cifra font-medium text-texto">{moneda(d.monto)}</p>
                <p className="text-texto-2">{entero(d.pagos)} pagos exitosos</p>
              </div>
            );
          }} />
          <Bar dataKey="monto" fill={ACENTO} radius={[4, 4, 0, 0]} maxBarSize={44} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ---------- Barras horizontales (HTML): etiqueta, barra, valor ----------
export function BarrasH({ filas, color = ACENTO, formatoValor = entero, max }:
  { filas: { etiqueta: string; valor: number; detalle?: string; pct?: number }[]; color?: string;
    formatoValor?: (v: number) => string; max?: number }) {
  const tope = max ?? Math.max(...filas.map((f) => f.valor), 1);
  return (
    <ul className="space-y-3">
      {filas.map((f) => (
        <li key={f.etiqueta} className="group" title={f.detalle}>
          <div className="mb-1 flex items-baseline justify-between gap-3 text-[13px]">
            <span className="truncate text-texto-2">{f.etiqueta}</span>
            <span className="cifra shrink-0 text-texto">
              {formatoValor(f.valor)}{f.pct != null && <span className="ml-2 text-texto-3">{porcentaje(f.pct)}</span>}
            </span>
          </div>
          <div className="h-2 rounded-full bg-panel-2">
            <div className="h-2 rounded-full transition-[width] duration-500" style={{ width: `${Math.max((f.valor / tope) * 100, f.valor > 0 ? 1.5 : 0)}%`, background: color }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

// ---------- Mapa de calor día × hora (secuencial, un solo tono) ----------
const RAMPA = ["#17233a", "#1c3f70", "#1c5cab", "#3987e5", "#86b6ef"];

export function MapaCalor({ dias, horas, valores }: { dias: string[]; horas: number[]; valores: number[][] }) {
  const max = Math.max(...valores.flat(), 1);
  const color = (v: number) => (v === 0 ? "#141926" : RAMPA[Math.min(RAMPA.length - 1, Math.floor((v / max) * RAMPA.length))]);
  return (
    <div className="overflow-x-auto">
      <div className="min-w-[640px]">
        <div className="grid gap-[3px]" style={{ gridTemplateColumns: `44px repeat(${horas.length}, minmax(0, 1fr))` }}>
          <div />
          {horas.map((h) => <div key={h} className="pb-1 text-center text-[11px] text-texto-3">{h % 3 === 0 ? `${h}h` : ""}</div>)}
          {dias.map((d, i) => (
            <div key={d} className="contents">
              <div className="flex items-center text-[12px] text-texto-3">{d.slice(0, 3)}</div>
              {horas.map((h, j) => {
                const v = valores[i]?.[j] ?? 0;
                return <div key={h} title={`${d}, ${h}:00–${h}:59 · ${entero(v)} pagos`} className="aspect-square rounded-[3px] hover:ring-2 hover:ring-texto/40"
                  style={{ background: color(v) }} />;
              })}
            </div>
          ))}
        </div>
        <div className="mt-3 flex items-center justify-end gap-2 text-[11px] text-texto-3">
          <span>Menos</span>
          {["#141926", ...RAMPA].map((c) => <span key={c} className="size-3 rounded-[3px]" style={{ background: c }} />)}
          <span>Más ({entero(max)} máx.)</span>
        </div>
      </div>
    </div>
  );
}

// ---------- Indicador de variación ----------
export function Variacion({ actual, anterior, sentido = "neutro", className }:
  { actual: number; anterior: number | null | undefined; sentido?: "sube_bueno" | "sube_malo" | "neutro"; className?: string }) {
  if (anterior == null || anterior === 0) return <span className={cn("text-[12px] text-texto-3", className)}>Sin período anterior</span>;
  const d = (actual - anterior) / Math.abs(anterior);
  const igual = Math.abs(d) < 0.0005;
  const bueno = sentido === "neutro" || igual ? null : (d > 0) === (sentido === "sube_bueno");
  return (
    <span className={cn("cifra text-[12px]", bueno === null ? "text-texto-3" : bueno ? "text-ok" : "text-serio", className)}>
      {igual ? "= " : d > 0 ? "▲ " : "▼ "}{porcentaje(Math.abs(d))}
      <span className="font-sans text-texto-3"> vs. período anterior</span>
    </span>
  );
}
