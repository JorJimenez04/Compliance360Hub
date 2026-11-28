"use client";

import { Fragment, useMemo, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ChevronDown, ChevronRight, FileText, Landmark, Lightbulb } from "lucide-react";
import { Aviso, Esqueleto, Insignia, Selector, Tarjeta, TituloTarjeta, tonoRiesgo } from "@/components/ui/basicos";
import { GraficoEvolucion } from "@/components/monitoreo/graficos";
import { Plazo, type Requerimiento } from "@/components/organizaciones/requerimientos";
import { useDatos } from "@/lib/useDatos";
import { entero, fecha, moneda, monedaCorta, porcentaje } from "@/lib/formato";
import { cn } from "@/lib/cn";

type Tono = "neutro" | "acento" | "ok" | "alerta" | "serio" | "critico";
interface Kpis { monto_pagado: number; pagos_exitosos: number; pagos_enviados: number; ticket_promedio: number; tasa_exito: number | null;
  devoluciones: number; variacion_monto?: number | null; variacion_pagos?: number | null }
interface Beneficiario { nombre: string; documento: string | null; tipo_persona: string | null; monto: number; pagos: number; ultimo: string | null; participacion: number }
interface Subcliente extends Kpis {
  cliente_id: number | null; nombre: string; empresas: string[]; beneficiarios: number; participacion: number; promedio_mensual: number;
  perfil_mensual: number | null; desviacion_perfil: number | null; nivel_riesgo: string | null;
  documentos: { cargados: number; exigidos: number; listo_para_banco: boolean; carpeta: boolean } | null;
  top_beneficiarios: Beneficiario[]; concentracion_top3: number | null; ultima: string;
}
interface ResumenAliados { activos: number; diligencia_pendiente: number; revision_vencida: number; riesgo_alto: number }
interface Organizacion {
  id: number; nombre: string; kpis: Kpis; subclientes: Subcliente[];
  alertas: { abiertas: number; posible_ros: number; escaladas: number; sin_atender: number };
  aliados: ResumenAliados & { total: number }; aliados_atencion: { id: number; nombre: string; estado: string; avisos: { tono: Tono; texto: string }[] }[];
  ultimo_reporte_uiaf: string | null;
}
type ReqTablero = Requerimiento & { beneficiarios: { id_beneficiario: string | null; nombre: string; actividad: string | null }[] };
interface Datos {
  periodo: { desde: string; hasta: string; meses: number; comparado: boolean; sin_datos: boolean };
  kpis: Kpis; serie: { mes: string; monto_pagado: number; pagos: number }[]; organizaciones: Organizacion[];
  alertas: { abiertas: number; posible_ros: number; escaladas: number; sin_atender: number };
  posible_ros: { id: number; organizacion_id: number; titulo: string; prioridad: string; periodo: string; subcliente: string | null }[];
  requerimientos: ReqTablero[]; resumen_requerimientos: { abiertos: number; atrasados: number; por_vencer: number; fuera_de_plazo: number; total: number };
  aliados: ResumenAliados;
  reportes_uiaf: { ros: number; aros: number; otros: number;
    lista: { id: number; organizacion: string; tipo: string; periodo_desde: string | null; periodo_hasta: string | null; fecha_presentacion: string; radicado: string | null; subcliente: string | null; archivo_nombre: string }[] };
  avisos: { prioridad: "alta" | "media" | "baja"; texto: string; enlace: string | null }[];
}

const hoy = () => new Date();
const iso = (d: Date) => d.toISOString().slice(0, 10);
function rango(p: string): { desde?: string; hasta?: string } {
  const h = hoy(); const y = h.getFullYear(); const m = h.getMonth();
  if (p === "mes") return { desde: iso(new Date(y, m, 1)), hasta: iso(h) };
  if (p === "mes_anterior") return { desde: iso(new Date(y, m - 1, 1)), hasta: iso(new Date(y, m, 0)) };
  if (p === "trimestre") return { desde: iso(new Date(y, m - 2, 1)), hasta: iso(h) };
  if (p === "anio") return { desde: iso(new Date(y, m - 11, 1)), hasta: iso(h) };
  return {};
}
const PERIODOS: [string, string][] = [["todo", "Todo el histórico"], ["anio", "Últimos 12 meses"], ["trimestre", "Últimos 3 meses"],
  ["mes_anterior", "Mes anterior"], ["mes", "Mes en curso"]];
const TONO_AVISO = { alta: "critico", media: "alerta", baja: "neutro" } as const;
const NOMBRE_ESTADO_REQ: Record<string, string> = { recibido: "Recibido", en_preparacion: "En preparación", en_revision: "En revisión",
  enviado: "Enviado", cerrado: "Cerrado", seguimiento: "Requiere seguimiento" };
const TONO_REQ: Record<string, Tono> = { recibido: "acento", en_preparacion: "alerta", en_revision: "alerta", enviado: "ok", cerrado: "neutro", seguimiento: "serio" };

function Cifra({ titulo, valor, detalle, tono }: { titulo: string; valor: string; detalle?: React.ReactNode; tono?: "alerta" | "critico" }) {
  return (
    <div className="rounded-xl border border-borde bg-panel px-4 py-3">
      <p className="text-xs text-texto-3">{titulo}</p>
      <p className={cn("cifra mt-1 text-2xl font-semibold", tono === "alerta" && "text-alerta", tono === "critico" && "text-critico")}>{valor}</p>
      {detalle && <p className="mt-0.5 text-xs text-texto-3">{detalle}</p>}
    </div>
  );
}

function Variacion({ v }: { v?: number | null }) {
  if (v == null) return null;
  return <span className={v >= 0 ? "text-ok" : "text-critico"}>{v >= 0 ? "+" : ""}{porcentaje(v)} vs. periodo anterior</span>;
}

export default function TableroCumplimiento() {
  const [periodo, setPeriodo] = useState("todo");
  const [org, setOrg] = useState("");
  const [todosAvisos, setTodosAvisos] = useState(false);
  const ruta = useMemo(() => {
    const p = new URLSearchParams(Object.entries(rango(periodo)).filter(([, v]) => v) as [string, string][]);
    if (org) p.set("organizacion_id", org);
    return `/api/tablero${p.toString() ? `?${p}` : ""}`;
  }, [periodo, org]);
  const datos = useDatos<Datos>(ruta);
  const orgs = useDatos<{ organizaciones: { id: number; nombre: string; activa: boolean }[] }>("/api/organizaciones");

  const t = datos.datos;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Tablero de cumplimiento</h1>
          <p className="text-sm text-texto-3">Toda la operación: clientes, subclientes, beneficiarios, alertas, reportes UIAF, requerimientos y aliados.
            {t && <> Periodo: {fecha(t.periodo.desde)} – {fecha(t.periodo.hasta)}.</>}</p>
        </div>
        <div className="flex gap-2">
          <Selector aria-label="Periodo" className="w-auto" value={periodo} onChange={(e) => setPeriodo(e.target.value)}>
            {PERIODOS.map(([k, n]) => <option key={k} value={k}>{n}</option>)}</Selector>
          <Selector aria-label="Cliente" className="w-auto" value={org} onChange={(e) => setOrg(e.target.value)}>
            <option value="">Todos los clientes</option>
            {orgs.datos?.organizaciones.filter((o) => o.activa).map((o) => <option key={o.id} value={o.id}>{o.nombre}</option>)}
          </Selector>
        </div>
      </div>

      {datos.error && <Aviso tono="critico">{datos.error}</Aviso>}
      {!t ? <Esqueleto className="h-[32rem]" /> : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <Cifra titulo="Monto pagado" valor={monedaCorta(t.kpis.monto_pagado)} detalle={t.periodo.comparado ? <Variacion v={t.kpis.variacion_monto} /> : `${t.periodo.meses} meses`} />
            <Cifra titulo="Pagos exitosos" valor={entero(t.kpis.pagos_exitosos)}
              detalle={t.kpis.tasa_exito != null ? `${porcentaje(t.kpis.tasa_exito)} de éxito · ticket ${monedaCorta(t.kpis.ticket_promedio)}` : undefined} />
            <Cifra titulo="Alertas abiertas" valor={entero(t.alertas.abiertas)} tono={t.alertas.posible_ros ? "critico" : undefined}
              detalle={<>{t.alertas.posible_ros} en posible ROS · {t.alertas.escaladas} escaladas</>} />
            <Cifra titulo="Requerimientos abiertos" valor={entero(t.resumen_requerimientos.abiertos)} tono={t.resumen_requerimientos.atrasados ? "critico" : undefined}
              detalle={<>{t.resumen_requerimientos.atrasados} atrasados · {t.resumen_requerimientos.por_vencer} por vencer</>} />
            <Cifra titulo="Aliados bancarios activos" valor={entero(t.aliados.activos)} tono={t.aliados.diligencia_pendiente ? "alerta" : undefined}
              detalle={<>{t.aliados.diligencia_pendiente} sin diligencia · {t.aliados.revision_vencida} revisión vencida</>} />
          </div>

          {t.avisos.length > 0 && (
            <Tarjeta>
              <TituloTarjeta titulo="Recomendaciones" descripcion="Generadas con los datos del periodo. Indican qué atender primero." />
              <ul className="divide-y divide-borde px-5 pb-3 pt-1 text-sm">
                {(todosAvisos ? t.avisos : t.avisos.slice(0, 6)).map((a, i) => (
                  <li key={i} className="flex items-start gap-3 py-2.5">
                    <Lightbulb className={cn("mt-0.5 size-4 shrink-0", a.prioridad === "alta" ? "text-critico" : a.prioridad === "media" ? "text-alerta" : "text-texto-3")} aria-hidden />
                    <span className="flex-1">{a.texto}</span>
                    <Insignia tono={TONO_AVISO[a.prioridad]}>{a.prioridad === "alta" ? "Alta" : a.prioridad === "media" ? "Media" : "Baja"}</Insignia>
                    {a.enlace && <Link href={a.enlace} className="text-xs text-acento hover:underline">Ver</Link>}
                  </li>
                ))}
              </ul>
              {t.avisos.length > 6 && <button className="px-5 pb-4 text-xs text-acento hover:underline" onClick={() => setTodosAvisos(!todosAvisos)}>
                {todosAvisos ? "Ver menos" : `Ver las ${t.avisos.length} recomendaciones`}</button>}
            </Tarjeta>
          )}

          {t.serie.length > 1 && (
            <Tarjeta>
              <TituloTarjeta titulo="Monto pagado por mes" descripcion="Pagos exitosos de todos los subclientes del periodo." />
              <div className="px-3 pb-4 pt-2">
                <GraficoEvolucion granularidad="Mensual" serie={t.serie.map((s) => ({ periodo: s.mes, monto: s.monto_pagado, pagos: s.pagos }))} />
              </div>
            </Tarjeta>
          )}

          {t.organizaciones.map((o) => <Cliente key={o.id} o={o} />)}

          <div className="grid gap-6 2xl:grid-cols-[2fr_3fr]">
            <Tarjeta>
              <TituloTarjeta titulo="Alertas y reportes UIAF" descripcion="Reportes cargados por el oficial y alertas que pueden terminar en un ROS." />
              <div className="space-y-4 px-5 pb-5 pt-3 text-sm">
                <div className="grid grid-cols-3 gap-3">
                  <Cifra titulo="ROS presentados" valor={entero(t.reportes_uiaf.ros)} />
                  <Cifra titulo="AROS presentados" valor={entero(t.reportes_uiaf.aros)} />
                  <Cifra titulo="Alertas críticas sin atender" valor={entero(t.alertas.sin_atender)} tono={t.alertas.sin_atender ? "alerta" : undefined} />
                </div>
                {t.posible_ros.length > 0 && (
                  <div><p className="mb-1 text-xs font-medium text-texto-2">En posible ROS</p>
                    <ul className="divide-y divide-borde">{t.posible_ros.map((a) => (
                      <li key={a.id} className="flex justify-between gap-3 py-2"><span>{a.titulo}{a.subcliente && <span className="text-texto-3"> · {a.subcliente}</span>}</span>
                        <span className="text-xs text-texto-3">{fecha(a.periodo)}</span></li>))}</ul></div>
                )}
                <div><p className="mb-1 text-xs font-medium text-texto-2">Reportes cargados</p>
                  {t.reportes_uiaf.lista.length === 0 ? <p className="text-texto-3">No hay reportes UIAF cargados en el periodo.</p> : (
                    <ul className="divide-y divide-borde">{t.reportes_uiaf.lista.slice(0, 8).map((r) => (
                      <li key={r.id} className="flex items-center justify-between gap-3 py-2">
                        <span><Insignia tono={r.tipo === "ROS" ? "critico" : "acento"}>{r.tipo}</Insignia>{" "}
                          {r.organizacion}{r.subcliente && ` · ${r.subcliente}`}{r.radicado && <span className="text-texto-3"> · rad. {r.radicado}</span>}</span>
                        <a href={`/api/reportes-uiaf/${r.id}/archivo`} target="_blank" rel="noreferrer" className="inline-flex shrink-0 items-center gap-1 text-xs text-acento hover:underline">
                          <FileText className="size-3.5" aria-hidden />{fecha(r.fecha_presentacion)}</a>
                      </li>))}</ul>)}
                </div>
              </div>
            </Tarjeta>

            <Tarjeta>
              <TituloTarjeta titulo="Requerimientos" descripcion="Los abiertos y los recibidos en el periodo: de aliados bancarios, del director y otros." />
              <div className="overflow-x-auto px-5 pb-5 pt-3">
                {t.requerimientos.length === 0 ? <p className="text-sm text-texto-3">No hay requerimientos en el periodo.</p> : (
                  <table className="w-full min-w-[640px] text-left text-sm">
                    <thead className="text-xs uppercase tracking-wider text-texto-3">
                      <tr><th className="py-2 pr-3">Recibido</th><th className="pr-3">Requerimiento</th><th className="pr-3">Beneficiario y actividad</th><th className="pr-3">Estado</th><th>Plazo</th></tr>
                    </thead>
                    <tbody className="divide-y divide-borde">
                      {t.requerimientos.slice(0, 12).map((q) => (
                        <tr key={q.id} className="align-top">
                          <td className="py-2.5 pr-3 text-texto-2">{fecha(q.fecha_recibido)}</td>
                          <td className="pr-3"><Link href={`/organizaciones/${q.organizacion_id}?tab=requerimientos&req=${q.id}`} className="font-medium hover:underline">{q.asunto}</Link>
                            <p className="text-xs text-texto-3">{q.consecutivo} · {q.origen === "aliado" ? q.aliado : q.origen === "director" ? "Director de cumplimiento" : q.origen_detalle ?? q.origen}
                              {" → "}{q.dirigido_a === "cliente" ? q.cliente : q.organizacion}</p></td>
                          <td className="pr-3 text-xs">{q.beneficiarios.length === 0 ? <span className="text-texto-3">—</span> : q.beneficiarios.map((b, i) => (
                            <p key={i}><span className="text-texto">{b.nombre}</span>{b.id_beneficiario && <span className="text-texto-3"> {b.id_beneficiario}</span>}
                              {b.actividad && <span className="text-texto-2"> · {b.actividad}</span>}</p>))}</td>
                          <td className="pr-3"><Insignia tono={TONO_REQ[q.estado]}>{NOMBRE_ESTADO_REQ[q.estado]}</Insignia></td>
                          <td><Plazo q={q} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>)}
              </div>
            </Tarjeta>
          </div>

          {t.periodo.sin_datos && <Aviso tono="acento">Aún no hay transacciones cargadas para este filtro.</Aviso>}
        </>
      )}
    </div>
  );
}

function Cliente({ o }: { o: Organizacion }) {
  const [abierto, setAbierto] = useState<number | string | null>(null);
  return (
    <Tarjeta>
      <TituloTarjeta titulo={<Link href={`/organizaciones/${o.id}`} className="hover:underline">{o.nombre}</Link>}
        descripcion={<>{monedaCorta(o.kpis.monto_pagado)} pagados · {entero(o.kpis.pagos_exitosos)} pagos · {o.subclientes.length} subclientes
          {o.ultimo_reporte_uiaf && <> · último reporte UIAF {fecha(o.ultimo_reporte_uiaf)}</>}</>}
        accion={<span className="flex flex-wrap gap-1.5 text-xs">
          {o.alertas.posible_ros > 0 && <Insignia tono="critico">{o.alertas.posible_ros} posible ROS</Insignia>}
          <Insignia tono={o.alertas.abiertas ? "alerta" : "neutro"}>{o.alertas.abiertas} alertas abiertas</Insignia>
          <Link href={`/organizaciones/${o.id}?tab=aliados`}><Insignia tono={o.aliados.diligencia_pendiente ? "alerta" : "ok"}>
            <Landmark className="size-3" aria-hidden />{o.aliados.activos} aliados activos</Insignia></Link></span>} />
      <div className="overflow-x-auto px-5 pb-4 pt-2">
        {o.subclientes.length === 0 ? <p className="text-sm text-texto-3">Sin movimientos en el periodo.</p> : (
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wider text-texto-3">
              <tr><th className="py-2 pr-3">Subcliente</th><th className="pr-3 text-right">Monto pagado</th><th className="pr-3 text-right">Pagos</th>
                <th className="pr-3">Participación</th><th className="pr-3">Vs. perfil declarado</th><th className="pr-3">Riesgo</th><th className="pr-3">Documentos</th><th className="text-right">Beneficiarios</th></tr>
            </thead>
            <tbody className="divide-y divide-borde">
              {o.subclientes.map((s) => {
                const clave = s.cliente_id ?? s.nombre;
                const visto = abierto === clave;
                return (
                  <Fragment key={clave}>
                    <tr className="cursor-pointer hover:bg-panel-2" onClick={() => setAbierto(visto ? null : clave)}>
                      <td className="py-2.5 pr-3"><span className="inline-flex items-center gap-1 font-medium">
                        {visto ? <ChevronDown className="size-3.5" aria-hidden /> : <ChevronRight className="size-3.5" aria-hidden />}{s.nombre}</span></td>
                      <td className="cifra pr-3 text-right">{moneda(s.monto_pagado)}</td>
                      <td className="cifra pr-3 text-right">{entero(s.pagos_exitosos)}</td>
                      <td className="pr-3"><div className="flex items-center gap-2"><div className="h-1.5 w-20 rounded-full bg-panel-2">
                        <div className="h-1.5 rounded-full bg-acento" style={{ width: `${Math.max(s.participacion * 100, 2)}%` }} /></div>
                        <span className="text-xs text-texto-2">{porcentaje(s.participacion)}</span></div></td>
                      <td className="pr-3 text-xs">{s.desviacion_perfil == null ? <span className="text-texto-3">Sin perfil declarado</span>
                        : s.desviacion_perfil > 0.2 ? <span className="text-critico">{porcentaje(s.desviacion_perfil)} sobre el perfil</span>
                        : <span className="text-ok">Dentro del perfil</span>}</td>
                      <td className="pr-3">{s.nivel_riesgo ? <Insignia tono={tonoRiesgo(s.nivel_riesgo)}>{s.nivel_riesgo}</Insignia> : <span className="text-xs text-texto-3">Sin calificar</span>}</td>
                      <td className="pr-3 text-xs">{s.documentos ? <span className={s.documentos.listo_para_banco ? "text-ok" : "text-alerta"}>
                        {s.documentos.cargados} de {s.documentos.exigidos}</span> : "—"}</td>
                      <td className="cifra text-right">{entero(s.beneficiarios)}</td>
                    </tr>
                    {visto && (
                      <tr><td colSpan={8} className="bg-panel-2/50 px-4 py-3">
                        <div className="flex flex-wrap items-start justify-between gap-4">
                          <div className="min-w-[340px] flex-1">
                            <p className="mb-1 text-xs font-medium text-texto-2">Beneficiarios representativos</p>
                            {s.top_beneficiarios.length === 0 ? <p className="text-xs text-texto-3">—</p> : (
                              <ul className="divide-y divide-borde text-[13px]">{s.top_beneficiarios.map((b, i) => (
                                <li key={i} className="flex justify-between gap-3 py-1.5">
                                  <span>{b.nombre}{b.documento && <span className="text-texto-3"> · {b.documento}</span>}</span>
                                  <span className="cifra shrink-0">{moneda(b.monto)} <span className="text-texto-3">· {porcentaje(b.participacion)} · {entero(b.pagos)} pagos</span></span>
                                </li>))}</ul>)}
                            {s.concentracion_top3 != null && s.concentracion_top3 > 0.4 && <p className="mt-1 inline-flex items-center gap-1 text-xs text-alerta">
                              <AlertTriangle className="size-3.5" aria-hidden />Los 3 primeros concentran el {porcentaje(s.concentracion_top3)} de lo pagado</p>}
                          </div>
                          <div className="space-y-1 text-xs text-texto-2">
                            <p>Promedio mensual: <span className="cifra text-texto">{moneda(s.promedio_mensual)}</span>{s.perfil_mensual != null && <> · perfil {moneda(s.perfil_mensual)}</>}</p>
                            <p>Ticket promedio: <span className="cifra text-texto">{moneda(s.ticket_promedio)}</span> · éxito {s.tasa_exito != null ? porcentaje(s.tasa_exito) : "—"}</p>
                            <p>Último movimiento: {fecha(s.ultima)} · cuentas del reporte: {s.empresas.join(", ")}</p>
                            {s.cliente_id && <p><Link href={`/organizaciones/${o.id}/clientes/${s.cliente_id}`} className="text-acento hover:underline">Abrir perfil 360</Link></p>}
                          </div>
                        </div>
                      </td></tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        )}
        {o.aliados_atencion.length > 0 && (
          <div className="mt-3 border-t border-borde pt-3 text-xs">
            <p className="mb-1 font-medium text-texto-2">Aliados bancarios que requieren atención</p>
            <ul className="space-y-1">{o.aliados_atencion.map((a) => (
              <li key={a.id}><Link href={`/organizaciones/${o.id}?tab=aliados`} className="font-medium hover:underline">{a.nombre}</Link>
                <span className="text-texto-3"> · {a.avisos.map((v) => v.texto).join(" · ")}</span></li>))}</ul>
          </div>
        )}
      </div>
    </Tarjeta>
  );
}
