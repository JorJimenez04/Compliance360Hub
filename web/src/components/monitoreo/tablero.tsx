"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle2, Inbox, Undo2 } from "lucide-react";
import { Aviso, Esqueleto, Tarjeta, TituloTarjeta, Vacio } from "@/components/ui/basicos";
import { query } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";
import { entero, fecha, fechaHora, moneda, monedaCorta, porcentaje } from "@/lib/formato";
import type { Continuidad, Kpis, Tablero } from "@/lib/tipos";
import { cn } from "@/lib/cn";
import { paramsFiltros, type Filtros } from "./filtros";
import { BarrasH, GraficoEvolucion, MapaCalor, Variacion } from "./graficos";

const COLOR_COMPOSICION: Record<string, string> = { pago_ok: "#3987e5", devolucion: "#d95926", fondeo: "#199e70" };

export default function VistaTablero({ empresaId, filtros, continuidad }:
  { empresaId: number; filtros: Filtros; continuidad: Continuidad | null }) {
  const { datos: t, error, cargando } = useDatos<Tablero>(
    `/api/monitoreo/empresas/${empresaId}/tablero${query(paramsFiltros(filtros))}`);

  return (
    <div className="space-y-5">
      {continuidad && !continuidad.completa && (
        <Aviso icono={<AlertTriangle className="size-4" />} titulo="El historial cargado tiene huecos">
          {continuidad.resumen}. Las cifras pueden estar incompletas: cargue de nuevo el «Historial de pagos» completo de esta empresa.
        </Aviso>
      )}
      {error && <Aviso tono="critico" icono={<AlertTriangle className="size-4" />} titulo="No se pudo cargar el tablero">{error}</Aviso>}

      {!t && cargando ? <EsqueletoTablero />
        : t?.vacio ? <Tarjeta><Vacio icono={<Inbox className="size-8" />} titulo="Sin movimientos en este período" texto="Amplíe el rango de fechas o quite los filtros de estado." /></Tarjeta>
        : t && (
          <div className={cn("space-y-5 transition-opacity", cargando && "opacity-60")}>
            <FilaKpis k={t.kpis} a={t.kpis_anterior} beneficiarios={t.beneficiarios} pico={t.dia_pico} />

            <Tarjeta>
              <TituloTarjeta titulo="Monto pagado" descripcion={`Pagos exitosos, agrupados de forma ${t.granularidad.toLowerCase()}`} />
              <div className="px-3 pb-4 pt-2"><GraficoEvolucion serie={t.serie} granularidad={t.granularidad} /></div>
            </Tarjeta>

            <div className="grid gap-5 lg:grid-cols-3">
              <Tarjeta>
                <TituloTarjeta titulo="Composición" descripcion="Movimientos del período por tipo" />
                <div className="space-y-4 px-5 pb-5 pt-4">
                  <div className="flex h-2.5 gap-[2px] overflow-hidden rounded-full" aria-hidden>
                    {t.composicion.map((c) => <div key={c.clave} style={{ width: `${c.pct * 100}%`, background: COLOR_COMPOSICION[c.clave] ?? "#737c91" }} />)}
                  </div>
                  <ul className="space-y-3">
                    {t.composicion.map((c) => (
                      <li key={c.clave} className="flex items-start justify-between gap-3 text-[13px]">
                        <span className="flex items-center gap-2 text-texto-2">
                          <span className="size-2.5 rounded-sm" style={{ background: COLOR_COMPOSICION[c.clave] ?? "#737c91" }} />{c.categoria}
                        </span>
                        <span className="text-right">
                          <span className="cifra block text-texto">{entero(c.movimientos)} <span className="text-texto-3">· {porcentaje(c.pct)}</span></span>
                          <span className="cifra block text-texto-3">{monedaCorta(c.monto)}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              </Tarjeta>

              <Tarjeta>
                <TituloTarjeta titulo="Pagos por rango de monto" descripcion="Cantidad de pagos exitosos" />
                <div className="px-5 pb-5 pt-4">
                  <BarrasH filas={t.rangos.map((r) => ({ etiqueta: r.rango, valor: r.pagos, pct: r.pct, detalle: `${entero(r.pagos)} pagos · ${moneda(r.monto)}` }))} />
                </div>
              </Tarjeta>

              <Tarjeta>
                <TituloTarjeta titulo="Bancos de destino" descripcion="Monto pagado por banco" />
                <div className="px-5 pb-5 pt-4">
                  <BarrasH formatoValor={monedaCorta} filas={agruparOtros(t.bancos, 7).map((b) => ({
                    etiqueta: b.banco, valor: b.monto, pct: b.pct, detalle: `${entero(b.pagos)} pagos · ${moneda(b.monto)}` }))} />
                </div>
              </Tarjeta>
            </div>

            <Ranking t={t} />

            <Tarjeta>
              <TituloTarjeta titulo="Actividad por día y hora" descripcion="Pagos exitosos según el momento en que se enviaron" />
              <div className="px-5 pb-5 pt-4"><MapaCalor {...t.actividad} /></div>
            </Tarjeta>

            <Devoluciones t={t} />
          </div>
        )}
    </div>
  );
}

function agruparOtros<T extends { banco: string; pagos: number; monto: number; pct: number }>(filas: T[], n: number) {
  if (filas.length <= n + 1) return filas;
  const resto = filas.slice(n);
  return [...filas.slice(0, n), { banco: `Otros (${resto.length})`, pagos: resto.reduce((s, f) => s + f.pagos, 0),
    monto: resto.reduce((s, f) => s + f.monto, 0), pct: resto.reduce((s, f) => s + f.pct, 0) } as T];
}

function Kpi({ titulo, valor, detalle, variacion }: { titulo: string; valor: string; detalle?: React.ReactNode; variacion?: React.ReactNode }) {
  return (
    <Tarjeta className="px-5 py-4">
      <p className="text-[13px] text-texto-3">{titulo}</p>
      <p className="cifra mt-1.5 text-[26px] font-semibold leading-tight text-texto">{valor}</p>
      {detalle && <p className="mt-1 text-[13px] text-texto-2">{detalle}</p>}
      <div className="mt-2">{variacion}</div>
    </Tarjeta>
  );
}

function FilaKpis({ k, a, beneficiarios, pico }: { k: Kpis; a: Kpis | null; beneficiarios: number; pico: Tablero["dia_pico"] }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Kpi titulo="Monto pagado" valor={monedaCorta(k.monto_pagado)} detalle={moneda(k.monto_pagado)}
        variacion={<Variacion actual={k.monto_pagado} anterior={a?.monto_pagado} />} />
      <Kpi titulo="Pagos exitosos" valor={entero(k.pagos_exitosos)}
        detalle={<>{entero(beneficiarios)} beneficiarios · ticket {monedaCorta(k.ticket_promedio)}</>}
        variacion={<Variacion actual={k.pagos_exitosos} anterior={a?.pagos_exitosos} />} />
      <Kpi titulo="Devoluciones" valor={entero(k.devoluciones)}
        detalle={<>{porcentaje(k.tasa_devolucion)} de los pagos · {monedaCorta(k.monto_devuelto)}</>}
        variacion={<Variacion actual={k.tasa_devolucion} anterior={a?.tasa_devolucion} sentido="sube_malo" />} />
      <Kpi titulo="Fondeos recibidos" valor={monedaCorta(k.monto_fondeado)}
        detalle={<>{entero(k.fondeos)} recargas{pico && <> · día pico {fecha(pico.fecha)}</>}</>}
        variacion={<Variacion actual={k.monto_fondeado} anterior={a?.monto_fondeado} />} />
    </div>
  );
}

function Ranking({ t, className }: { t: Tablero; className?: string }) {
  const [orden, setOrden] = useState<"monto" | "pagos">("monto");
  const filas = (orden === "monto" ? t.ranking_monto : t.ranking_pagos).slice(0, 10);
  return (
    <Tarjeta className={className}>
      <TituloTarjeta titulo="Principales beneficiarios" descripcion="Top 10 del período · documentos enmascarados"
        accion={
          <div className="flex shrink-0 rounded-lg border border-borde-fuerte p-0.5 text-[13px]" role="group" aria-label="Ordenar por">
            {(["monto", "pagos"] as const).map((o) => (
              <button key={o} onClick={() => setOrden(o)} aria-pressed={orden === o}
                className={cn("rounded-md px-2.5 py-1", orden === o ? "bg-panel-2 font-medium text-texto" : "text-texto-3")}>
                {o === "monto" ? "Por monto" : "Por cantidad"}
              </button>
            ))}
          </div>
        } />
      <div className="overflow-x-auto px-2 pb-3 pt-3">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="text-left text-texto-3">
              <th className="px-3 py-2 font-medium">#</th><th className="px-3 py-2 font-medium">Beneficiario</th>
              <th className="px-3 py-2 text-right font-medium">Pagos</th><th className="px-3 py-2 text-right font-medium">Monto</th>
              <th className="px-3 py-2 text-right font-medium">Participación</th><th className="px-3 py-2 text-right font-medium">Último pago</th>
            </tr>
          </thead>
          <tbody>
            {filas.map((f) => (
              <tr key={f.posicion + f.beneficiario} className="border-t border-borde/70 hover:bg-panel-2/60">
                <td className="cifra px-3 py-2.5 text-texto-3">{f.posicion}</td>
                <td className="px-3 py-2.5"><span className="block max-w-[260px] truncate text-texto">{f.beneficiario}</span>
                  <span className="mono text-[12px] text-texto-3">{f.id_beneficiario ?? "—"}</span></td>
                <td className="cifra px-3 py-2.5 text-right">{entero(f.pagos)}</td>
                <td className="cifra px-3 py-2.5 text-right text-texto">{monedaCorta(f.monto)}</td>
                <td className="cifra px-3 py-2.5 text-right text-texto-2">{porcentaje(f.pct)}</td>
                <td className="px-3 py-2.5 text-right text-texto-3">{fecha(f.ultimo_pago)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Tarjeta>
  );
}

function Devoluciones({ t }: { t: Tablero }) {
  if (!t.kpis.devoluciones)
    return <Tarjeta className="flex items-center gap-3 px-5 py-4 text-sm text-texto-2"><CheckCircle2 className="size-4 text-ok" />Sin devoluciones en este período.</Tarjeta>;
  return (
    <div className="grid gap-5 xl:grid-cols-5">
      <Tarjeta className="xl:col-span-2">
        <TituloTarjeta titulo="Motivos de devolución" descripcion={`${entero(t.kpis.devoluciones)} devoluciones · ${moneda(t.kpis.monto_devuelto)}`} />
        <div className="px-5 pb-5 pt-4">
          <BarrasH color="#d95926" filas={t.motivos_devolucion.map((m) => ({ etiqueta: m.motivo, valor: m.devoluciones, pct: m.pct, detalle: moneda(m.monto) }))} />
        </div>
      </Tarjeta>
      <Tarjeta className="xl:col-span-3">
        <TituloTarjeta titulo="Devoluciones recientes" descripcion="Las 10 más recientes del período" />
        <div className="overflow-x-auto px-2 pb-3 pt-3">
          <table className="w-full text-[13px]">
            <thead><tr className="text-left text-texto-3">
              <th className="px-3 py-2 font-medium">Fecha</th><th className="px-3 py-2 font-medium">Beneficiario</th>
              <th className="px-3 py-2 font-medium">Banco</th><th className="px-3 py-2 text-right font-medium">Monto</th>
              <th className="px-3 py-2 font-medium">Motivo</th></tr></thead>
            <tbody>
              {t.devoluciones_recientes.slice(0, 10).map((d, i) => (
                <tr key={i} className="border-t border-borde/70">
                  <td className="whitespace-nowrap px-3 py-2.5 text-texto-3">{fechaHora(d.fecha_hora)}</td>
                  <td className="px-3 py-2.5"><span className="block max-w-[170px] truncate">{d.beneficiario}</span></td>
                  <td className="px-3 py-2.5 text-texto-2">{d.banco ?? "—"}</td>
                  <td className="cifra px-3 py-2.5 text-right">{moneda(d.monto)}</td>
                  <td className="min-w-[210px] px-3 py-2.5 text-texto-2"><span className="inline-flex items-start gap-1.5"><Undo2 className="mt-0.5 size-3.5 shrink-0 text-serio" aria-hidden />{d.motivo}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Tarjeta>
    </div>
  );
}

function EsqueletoTablero() {
  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{[0, 1, 2, 3].map((i) => <Esqueleto key={i} className="h-32 rounded-tarjeta" />)}</div>
      <Esqueleto className="h-80 rounded-tarjeta" />
      <div className="grid gap-5 lg:grid-cols-3">{[0, 1, 2].map((i) => <Esqueleto key={i} className="h-64 rounded-tarjeta" />)}</div>
    </div>
  );
}
