"use client";

import { useMemo, useState } from "react";
import { AlertTriangle, ArrowUpRight, Building2, Search } from "lucide-react";
import { Aviso, Entrada, Esqueleto, Insignia, Selector, Tarjeta, TituloTarjeta, Vacio, tonoRiesgo } from "@/components/ui/basicos";
import { query } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";
import { entero, haceCuanto, moneda, monedaCorta, porcentaje } from "@/lib/formato";
import type { Cartera, FilaCartera } from "@/lib/tipos";
import { cn } from "@/lib/cn";
import { paramsFiltros, type Filtros } from "./filtros";
import { BarrasH, GraficoEvolucion, Variacion } from "./graficos";
import { Kpi } from "./tablero";

type Orden = "monto" | "pagos" | "devolucion" | "reciente" | "nombre";
const ORDENES: { id: Orden; nombre: string }[] = [
  { id: "monto", nombre: "Mayor monto pagado" }, { id: "pagos", nombre: "Más pagos" },
  { id: "devolucion", nombre: "Mayor tasa de devolución" }, { id: "reciente", nombre: "Actividad más reciente" },
  { id: "nombre", nombre: "Nombre" },
];

function ordenar(filas: FilaCartera[], orden: Orden) {
  const v = (f: FilaCartera) => f.kpis;
  const copia = [...filas];
  switch (orden) {
    case "pagos": return copia.sort((a, b) => (v(b)?.pagos_exitosos ?? -1) - (v(a)?.pagos_exitosos ?? -1));
    case "devolucion": return copia.sort((a, b) => (v(b)?.tasa_devolucion ?? -1) - (v(a)?.tasa_devolucion ?? -1));
    case "reciente": return copia.sort((a, b) => (b.ultima_operacion ?? "").localeCompare(a.ultima_operacion ?? ""));
    case "nombre": return copia.sort((a, b) => a.nombre.localeCompare(b.nombre, "es"));
    default: return copia.sort((a, b) => (v(b)?.monto_pagado ?? -1) - (v(a)?.monto_pagado ?? -1));
  }
}

/** Vista de cartera: cifras globales de todas las empresas y una tarjeta por empresa. */
export default function VistaCartera({ filtros, organizacionId, esCliente, onAbrir }: {
  filtros: Filtros; organizacionId: string | null; esCliente: boolean; onAbrir: (empresaId: number) => void;
}) {
  const { datos: c, error, cargando } = useDatos<Cartera>(
    `/api/monitoreo/cartera${query({ ...paramsFiltros(filtros), organizacion_id: organizacionId })}`);
  const [buscar, setBuscar] = useState("");
  const [orden, setOrden] = useState<Orden>("monto");

  const filas = useMemo(() => {
    const f = buscar.trim().toLowerCase();
    return ordenar((c?.empresas ?? []).filter((e) => !f || e.nombre.toLowerCase().includes(f)
      || (e.razon_social ?? "").toLowerCase().includes(f)), orden);
  }, [c, buscar, orden]);

  if (error) return <Aviso tono="critico" icono={<AlertTriangle className="size-4" />} titulo="No se pudo cargar la cartera">{error}</Aviso>;
  if (!c) return <EsqueletoCartera />;
  const g = c.global, a = c.anterior;
  const participacion = (c.empresas.filter((e) => e.kpis?.monto_pagado));
  const top = participacion.slice(0, 7);
  const resto = participacion.slice(7);

  return (
    <div className={cn("space-y-6 transition-opacity", cargando && "opacity-60")}>
      {/* ---------- Visión global ---------- */}
      <section className="space-y-5" aria-labelledby="titulo-global">
        <h2 id="titulo-global" className="text-[15px] font-semibold">Visión global · {entero(c.total_empresas)} empresas</h2>
        {!g ? (
          <Tarjeta><Vacio icono={<Building2 className="size-8" />} titulo="Sin movimientos en este período" texto="Amplíe el rango de fechas o quite los filtros de estado." /></Tarjeta>
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
              <Kpi titulo="Monto pagado" valor={monedaCorta(g.monto_pagado)} detalle={moneda(g.monto_pagado)}
                variacion={<Variacion actual={g.monto_pagado} anterior={a?.monto_pagado} />} />
              <Kpi titulo="Pagos exitosos" valor={entero(g.pagos_exitosos)} detalle={<>ticket promedio {monedaCorta(g.ticket_promedio)}</>}
                variacion={<Variacion actual={g.pagos_exitosos} anterior={a?.pagos_exitosos} />} />
              <Kpi titulo="Tasa de éxito" valor={porcentaje(g.tasa_exito)} detalle={<>{entero(g.pagos_enviados)} pagos enviados</>}
                variacion={<Variacion actual={g.tasa_exito} anterior={a?.tasa_exito} sentido="sube_bueno" />} />
              <Kpi titulo="Devoluciones" valor={entero(g.devoluciones)} detalle={<>{porcentaje(g.tasa_devolucion)} de los pagos · {monedaCorta(g.monto_devuelto)}</>}
                variacion={<Variacion actual={g.tasa_devolucion} anterior={a?.tasa_devolucion} sentido="sube_malo" />} />
              <Kpi titulo="Fondeos recibidos" valor={monedaCorta(g.monto_fondeado)}
                detalle={<>{entero(g.fondeos)} recargas · {entero(c.empresas_con_movimiento)} de {entero(c.total_empresas)} empresas con movimiento</>}
                variacion={<Variacion actual={g.monto_fondeado} anterior={a?.monto_fondeado} />} />
            </div>

            <div className="grid gap-5 xl:grid-cols-5">
              <Tarjeta className="xl:col-span-3">
                <TituloTarjeta titulo="Monto pagado por todas las empresas"
                  descripcion={`Pagos exitosos, agrupados de forma ${c.granularidad.toLowerCase()}`} />
                <div className="px-3 pb-4 pt-2"><GraficoEvolucion serie={c.serie} granularidad={c.granularidad} /></div>
              </Tarjeta>
              <Tarjeta className="xl:col-span-2">
                <TituloTarjeta titulo="Participación por empresa" descripcion="Del monto pagado en el período" />
                <div className="px-5 pb-5 pt-4">
                  <BarrasH formatoValor={monedaCorta} filas={[
                    ...top.map((e) => ({ etiqueta: e.nombre, valor: e.kpis!.monto_pagado, pct: e.participacion,
                      detalle: `${entero(e.kpis!.pagos_exitosos)} pagos · ${moneda(e.kpis!.monto_pagado)}` })),
                    ...(resto.length ? [{ etiqueta: `Otras (${resto.length})`, valor: resto.reduce((s, e) => s + e.kpis!.monto_pagado, 0),
                      pct: resto.reduce((s, e) => s + e.participacion, 0) }] : []),
                  ]} />
                </div>
              </Tarjeta>
            </div>
          </>
        )}
      </section>

      {/* ---------- Tarjetas por empresa ---------- */}
      <section className="space-y-4" aria-labelledby="titulo-empresas">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <h2 id="titulo-empresas" className="text-[15px] font-semibold">Empresas</h2>
            <p className="text-[13px] text-texto-3">Haga clic en una empresa para ver su tablero completo.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-2.5 size-4 text-texto-3" aria-hidden />
              <Entrada aria-label="Buscar empresa" placeholder="Buscar empresa…" className="w-60 pl-9" value={buscar} onChange={(e) => setBuscar(e.target.value)} />
            </div>
            <Selector aria-label="Ordenar empresas" className="w-60" value={orden} onChange={(e) => setOrden(e.target.value as Orden)}>
              {ORDENES.map((o) => <option key={o.id} value={o.id}>{o.nombre}</option>)}
            </Selector>
          </div>
        </div>
        {!filas.length ? <p className="text-sm text-texto-3">Ninguna empresa coincide con la búsqueda.</p> : (
          <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
            {filas.map((e) => <TarjetaEmpresa key={e.id} e={e} esCliente={esCliente} onAbrir={() => onAbrir(e.id)} />)}
          </div>
        )}
      </section>
    </div>
  );
}

function TarjetaEmpresa({ e, esCliente, onAbrir }: { e: FilaCartera; esCliente: boolean; onAbrir: () => void }) {
  const k = e.kpis;
  return (
    <button onClick={onAbrir} aria-label={`Ver tablero de ${e.nombre}`}
      className={cn("group flex flex-col rounded-tarjeta border border-borde bg-panel p-5 text-left transition-colors",
        "hover:border-acento/50 hover:bg-panel-2/40 focus-visible:border-acento focus-visible:outline-none", !k && "opacity-70")}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-semibold text-texto">{e.nombre}</p>
          {!esCliente && e.nit && <p className="text-xs text-texto-3">NIT {e.nit}</p>}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {!esCliente && (e.enlazada
            ? <Insignia tono={tonoRiesgo(e.nivel_riesgo)}>{e.nivel_riesgo ?? "Sin calificar"}</Insignia>
            : <Insignia>Sin enlazar</Insignia>)}
          <ArrowUpRight className="size-4 text-texto-3 transition-colors group-hover:text-acento" aria-hidden />
        </div>
      </div>

      {!k ? <p className="mt-6 text-sm text-texto-3">Sin movimientos en el período.</p> : (
        <>
          <div className="mt-4 flex items-end justify-between gap-4">
            <div>
              <p className="text-[12px] text-texto-3">Monto pagado</p>
              <p className="cifra text-2xl font-semibold leading-tight">{monedaCorta(k.monto_pagado)}</p>
              <Variacion actual={k.monto_pagado} anterior={e.kpis_anterior?.monto_pagado} />
            </div>
            <Tendencia valores={e.tendencia} />
          </div>

          <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2.5 border-t border-borde/70 pt-4 text-[13px]">
            <Dato nombre="Pagos exitosos" valor={entero(k.pagos_exitosos)} />
            <Dato nombre="Tasa de éxito" valor={porcentaje(k.tasa_exito)} />
            <Dato nombre="Devoluciones" valor={`${entero(k.devoluciones)} · ${porcentaje(k.tasa_devolucion)}`}
              alerta={k.tasa_devolucion >= 0.05} />
            <Dato nombre="Fondeado" valor={monedaCorta(k.monto_fondeado)} />
          </dl>

          <div className="mt-4">
            <div className="mb-1 flex justify-between text-[12px] text-texto-3">
              <span>Participación en el total</span><span className="cifra">{porcentaje(e.participacion)}</span>
            </div>
            <div className="h-1.5 rounded-full bg-panel-2">
              <div className="h-1.5 rounded-full bg-acento" style={{ width: `${Math.max(e.participacion * 100, e.participacion > 0 ? 1 : 0)}%` }} />
            </div>
          </div>
        </>
      )}
      <p className="mt-4 text-[12px] text-texto-3">
        {e.ultima_operacion ? <>Última operación {haceCuanto(e.ultima_operacion)}</> : "Sin operaciones cargadas"}
      </p>
    </button>
  );
}

function Dato({ nombre, valor, alerta }: { nombre: string; valor: string; alerta?: boolean }) {
  return (
    <div>
      <dt className="text-texto-3">{nombre}</dt>
      <dd className={cn("cifra font-medium", alerta ? "text-serio" : "text-texto")}>{valor}</dd>
    </div>
  );
}

/** Línea de tendencia del monto pagado en el período (mismos cortes que el gráfico global). */
function Tendencia({ valores }: { valores: number[] }) {
  if (valores.length < 2) return null;
  const w = 120, h = 40, max = Math.max(...valores, 1);
  const pts = valores.map((v, i) => [(i / (valores.length - 1)) * w, h - 2 - (v / max) * (h - 4)]);
  const linea = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden className="shrink-0">
      <polygon points={`0,${h} ${linea} ${w},${h}`} fill="#5fe9d0" opacity="0.12" />
      <polyline points={linea} fill="none" stroke="#5fe9d0" strokeWidth="1.75" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

function EsqueletoCartera() {
  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">{[0, 1, 2, 3, 4].map((i) => <Esqueleto key={i} className="h-32 rounded-tarjeta" />)}</div>
      <Esqueleto className="h-80 rounded-tarjeta" />
      <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">{[0, 1, 2].map((i) => <Esqueleto key={i} className="h-64 rounded-tarjeta" />)}</div>
    </div>
  );
}
