"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Activity, AlertTriangle, ArrowLeft, Save } from "lucide-react";
import { Aviso, Boton, Entrada, Esqueleto, Etiqueta, Insignia, Selector, Tarjeta, TituloTarjeta, Vacio, tonoRiesgo } from "@/components/ui/basicos";
import { enviar, ErrorApi } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";
import { entero, fecha, fechaHora, haceCuanto, mesCorto, moneda, monedaCorta, porcentaje } from "@/lib/formato";
import type { Catalogo, FichaCliente, PerfilVsReal } from "@/lib/tipos";
import { cn } from "@/lib/cn";
import { usePuedeGestionar } from "@/lib/sesion";
import { Kpi } from "@/components/monitoreo/tablero";
import ActividadYModelos from "./actividades";
import { riesgoDe } from "./selector-modelos";
import VistaPaquete from "./paquete";
import { ListaAlertas, NOMBRE_ESTADO } from "./alertas";
import MonitoreoCliente from "./monitoreo-cliente";
import BeneficiariosCliente from "./beneficiarios";
import DocumentacionPropia from "./documentacion";

const PESTANAS = [
  { id: "resumen", nombre: "Resumen" },
  { id: "monitoreo", nombre: "Monitoreo" },
  { id: "perfil", nombre: "Perfil vs. comportamiento" },
  { id: "alertas", nombre: "Alertas y casos" },
  { id: "beneficiarios", nombre: "Beneficiarios" },
  { id: "expediente", nombre: "Documentación propia" },
  { id: "bitacora", nombre: "Bitácora" },
] as const;

function Vista({ organizacionId, clienteId }: { organizacionId: number; clienteId: number }) {
  const params = useSearchParams();
  const router = useRouter();
  const ruta = usePathname();
  const ficha = useDatos<FichaCliente>(`/api/clientes/${clienteId}`);
  const cat = useDatos<Catalogo>("/api/catalogo");
  const pestana = PESTANAS.find((p) => p.id === params.get("tab"))?.id ?? "resumen";
  const ir = (t: string) => router.replace(`${ruta}?tab=${t}`, { scroll: false });   // al cambiar de pestaña se limpian los filtros

  if (ficha.error) return <Aviso tono="critico" icono={<AlertTriangle className="size-4" />}>{ficha.error}</Aviso>;
  if (!ficha.datos || !cat.datos) return <Esqueleto className="h-96" />;
  const f = ficha.datos;

  return (
    <div className="space-y-6">
      <div>
        <Link href={`/organizaciones/${organizacionId}?tab=clientes`} className="mb-2 inline-flex items-center gap-1.5 text-sm text-texto-3 hover:text-texto">
          <ArrowLeft className="size-4" aria-hidden />{f.organizacion} · Clientes</Link>
        <h1 className="text-2xl font-semibold tracking-tight">{f.razon_social}</h1>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-texto-3">
          <span>{f.nit ? `NIT ${f.nit}` : <span className="text-alerta">NIT pendiente</span>}</span>
          <Insignia tono={tonoRiesgo(f.nivel_riesgo)}>Riesgo {f.nivel_riesgo}</Insignia>
          <Insignia>{f.estado}</Insignia>
          {f.alertas_resumen.abiertas > 0 && <Insignia tono="serio">{f.alertas_resumen.abiertas} alertas abiertas</Insignia>}
          <span className="text-xs">Uso interno de cumplimiento: no visible para la organización ni para el cliente.</span>
        </div>
      </div>
      <div className="flex gap-1 overflow-x-auto border-b border-borde" role="tablist">
        {PESTANAS.map((p) => (
          <button key={p.id} role="tab" aria-selected={pestana === p.id} onClick={() => ir(p.id)}
            className={cn("-mb-px whitespace-nowrap border-b-2 px-3.5 pb-3 pt-1 text-sm transition-colors",
              pestana === p.id ? "border-acento font-medium text-texto" : "border-transparent text-texto-3 hover:text-texto-2")}>
            {p.nombre}{p.id === "alertas" && f.alertas_resumen.abiertas > 0 && <span className="cifra ml-1.5 text-serio">{f.alertas_resumen.abiertas}</span>}
          </button>
        ))}
      </div>
      {pestana === "resumen" ? <Resumen f={f} cat={cat.datos} organizacionId={organizacionId} onGuardado={ficha.recargar} />
        : pestana === "monitoreo" ? <MonitoreoCliente empresas={f.empresas} />
        : pestana === "beneficiarios" ? <BeneficiariosCliente clienteId={clienteId} />
        : pestana === "perfil" ? <Perfil f={f} onGuardado={ficha.recargar} />
        : pestana === "alertas" ? <ListaAlertas ruta={`/api/clientes/${clienteId}/alertas`} mostrarEmpresa={f.empresas.length > 1} />
        : pestana === "expediente" ? <Expediente f={f} cat={cat.datos} onGuardado={ficha.recargar} />
        : <Bitacora clienteId={clienteId} />}
    </div>
  );
}

export default function Expediente360(props: { organizacionId: number; clienteId: number }) {
  return <Suspense><Vista {...props} /></Suspense>;
}

// ---------- Resumen ----------
type Editable = Pick<FichaCliente, "razon_social" | "nit" | "tipo_persona" | "estado" | "nivel_riesgo" | "actividades_ciiu"
  | "pais_constitucion" | "sitio_web" | "proxima_revision" | "modelos_negocio" | "notas">;
const CAMPOS: (keyof Editable)[] = ["razon_social", "nit", "tipo_persona", "estado", "nivel_riesgo", "actividades_ciiu",
  "pais_constitucion", "sitio_web", "proxima_revision", "modelos_negocio", "notas"];

function useGuardar(clienteId: number, onGuardado: () => void) {
  const [guardando, setGuardando] = useState(false);
  const [fallo, setFallo] = useState<string | null>(null);
  const [ok, setOk] = useState(false);
  async function guardar(cuerpo: Record<string, unknown>) {
    setGuardando(true); setFallo(null); setOk(false);
    try { await enviar(`/api/clientes/${clienteId}`, cuerpo, "PATCH"); setOk(true); onGuardado(); }
    catch (e) { setFallo(e instanceof ErrorApi ? e.message : "No se pudo guardar."); }
    finally { setGuardando(false); }
  }
  return { guardando, fallo, ok, guardar };
}

function Resumen({ f, cat, organizacionId, onGuardado }: { f: FichaCliente; cat: Catalogo; organizacionId: number; onGuardado: () => void }) {
  const [ed, setEd] = useState<Editable>(() => Object.fromEntries(CAMPOS.map((c) => [c, f[c]])) as unknown as Editable);
  useEffect(() => setEd(Object.fromEntries(CAMPOS.map((c) => [c, f[c]])) as unknown as Editable), [f]);
  const { guardando, fallo, ok, guardar } = useGuardar(f.id, onGuardado);
  const puede = usePuedeGestionar();
  const k = f.operacion.kpis;
  const poner = (c: Partial<Editable>) => setEd({ ...ed, ...c });
  const r = f.alertas_resumen;
  const sugerido = riesgoDe(cat.modelos, ed.modelos_negocio);

  return (
    <div className="space-y-6">
      <section className="space-y-3">
        <h2 className="text-[15px] font-semibold">Operación · últimos 90 días con datos
          {f.operacion.desde && <span className="ml-2 text-[13px] font-normal text-texto-3">{fecha(f.operacion.desde)} – {fecha(f.operacion.hasta)}</span>}</h2>
        {!k ? <Tarjeta><Vacio icono={<Activity className="size-8" />} titulo="Sin transacciones enlazadas"
          texto="Este cliente aún no tiene movimientos cargados en el monitoreo." /></Tarjeta> : (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Kpi titulo="Monto pagado" valor={monedaCorta(k.monto_pagado)} detalle={moneda(k.monto_pagado)} />
            <Kpi titulo="Pagos exitosos" valor={entero(k.pagos_exitosos)} detalle={<>ticket {monedaCorta(k.ticket_promedio)} · éxito {porcentaje(k.tasa_exito)}</>} />
            <Kpi titulo="Devoluciones" valor={entero(k.devoluciones)} detalle={<>{porcentaje(k.tasa_devolucion)} de los pagos</>} />
            <Kpi titulo="Última operación" valor={haceCuanto(f.operacion.ultima_operacion)} detalle={fechaHora(f.operacion.ultima_operacion)} />
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-texto-3">Empresas monitoreadas:</span>
          {f.empresas.length ? f.empresas.map((e) => (
            <Link key={e.id} href={`?tab=monitoreo&empresa=${e.id}`} className="rounded-md border border-borde-fuerte px-2 py-0.5 text-texto-2 hover:border-acento hover:text-acento">{e.nombre}</Link>
          )) : <span className="text-texto-3">ninguna</span>}
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-4">
        {(["Crítica", "Alta", "Media", "Baja"] as const).map((p) => (
          <Tarjeta key={p} className="px-5 py-4">
            <p className="text-[13px] text-texto-3">Alertas abiertas · {p}</p>
            <p className={cn("cifra mt-1 text-2xl font-semibold", r.por_prioridad[p] && (p === "Crítica" || p === "Alta") ? "text-serio" : "text-texto")}>{entero(r.por_prioridad[p])}</p>
          </Tarjeta>
        ))}
      </section>
      {r.posible_ros > 0 && <Aviso tono="critico" titulo={`${r.posible_ros} casos marcados como ${NOMBRE_ESTADO.posible_ros}`}>Pasan a la reportería UIAF de la organización.</Aviso>}

      <Tarjeta>
        <TituloTarjeta titulo="Ficha del cliente (KYC/KYB)"
          accion={puede && <Boton variante="primario" cargando={guardando} onClick={() => guardar({ ...ed })}><Save className="size-4" aria-hidden />Guardar</Boton>} />
        <fieldset disabled={!puede} className="space-y-5 px-5 pb-5 pt-3">
          {fallo && <Aviso tono="critico">{fallo}</Aviso>}
          {ok && <Aviso tono="ok">Ficha guardada.</Aviso>}
          <div className="grid gap-4 md:grid-cols-3">
            <div><Etiqueta htmlFor="c-rs">Razón social</Etiqueta><Entrada id="c-rs" value={ed.razon_social} onChange={(e) => poner({ razon_social: e.target.value })} /></div>
            <div><Etiqueta htmlFor="c-nit">NIT</Etiqueta><Entrada id="c-nit" value={ed.nit ?? ""} onChange={(e) => poner({ nit: e.target.value })} /></div>
            <div><Etiqueta htmlFor="c-tp">Tipo de persona</Etiqueta>
              <Selector id="c-tp" value={ed.tipo_persona} onChange={(e) => poner({ tipo_persona: e.target.value as Editable["tipo_persona"] })}>
                <option value="juridica">Persona jurídica</option><option value="natural">Persona natural</option></Selector></div>
            <div><Etiqueta htmlFor="c-riesgo">Nivel de riesgo</Etiqueta>
              <Selector id="c-riesgo" value={ed.nivel_riesgo} onChange={(e) => poner({ nivel_riesgo: e.target.value })}>
                {["Sin calificar", "Alto", "Medio", "Bajo"].map((n) => <option key={n} value={n}>{n}</option>)}
                {!["Sin calificar", "Alto", "Medio", "Bajo"].includes(ed.nivel_riesgo) && <option value={ed.nivel_riesgo}>{ed.nivel_riesgo} (anterior)</option>}
              </Selector>
              {sugerido && <p className="mt-1 text-xs text-texto-3">Sugerido por sus modelos: {sugerido}
                {sugerido !== ed.nivel_riesgo && <button type="button" className="ml-2 text-acento hover:underline" onClick={() => poner({ nivel_riesgo: sugerido })}>Usar</button>}</p>}</div>
            <div><Etiqueta htmlFor="c-est">Estado</Etiqueta>
              <Selector id="c-est" value={ed.estado} onChange={(e) => poner({ estado: e.target.value })}>
                {["Prospecto", "Activo", "Suspendido", "Terminado"].map((n) => <option key={n} value={n}>{n}</option>)}</Selector></div>
            <div><Etiqueta htmlFor="c-rev">Próxima revisión</Etiqueta>
              <Entrada id="c-rev" type="date" value={ed.proxima_revision ?? ""} onChange={(e) => poner({ proxima_revision: e.target.value || null })} /></div>
            <div><Etiqueta htmlFor="c-pais">País de constitución</Etiqueta><Entrada id="c-pais" value={ed.pais_constitucion ?? ""} onChange={(e) => poner({ pais_constitucion: e.target.value })} /></div>
            <div><Etiqueta htmlFor="c-web">Sitio web</Etiqueta><Entrada id="c-web" value={ed.sitio_web ?? ""} onChange={(e) => poner({ sitio_web: e.target.value })} /></div>
          </div>
          <ActividadYModelos modelos={cat.modelos} documentos={cat.documentos} actividades={ed.actividades_ciiu}
            modelosNegocio={ed.modelos_negocio} onCambio={({ actividades, modelos }) => poner({ actividades_ciiu: actividades, modelos_negocio: modelos })} />
          <div><Etiqueta htmlFor="c-notas">Notas internas</Etiqueta>
            <textarea id="c-notas" rows={3} value={ed.notas ?? ""} onChange={(e) => poner({ notas: e.target.value })}
              className="w-full rounded-lg border border-borde-fuerte bg-fondo px-3 py-2 text-sm text-texto focus:border-acento focus:outline-none" /></div>
        </fieldset>
      </Tarjeta>
    </div>
  );
}

// ---------- Perfil declarado vs. real ----------
function Perfil({ f, onGuardado }: { f: FichaCliente; onGuardado: () => void }) {
  const datos = useDatos<PerfilVsReal>(`/api/clientes/${f.id}/perfil?meses=6&v=${f.perfil_actualizado ?? ""}`);
  const [vol, setVol] = useState(f.perfil_volumen_mensual?.toString() ?? "");
  const [ops, setOps] = useState(f.perfil_operaciones_mes?.toString() ?? "");
  const [tkt, setTkt] = useState(f.perfil_ticket_promedio?.toString() ?? "");
  const [paises, setPaises] = useState(f.perfil_paises.join(", "));
  const { guardando, fallo, ok, guardar } = useGuardar(f.id, () => { onGuardado(); datos.recargar(); });
  const puede = usePuedeGestionar();
  const num = (s: string) => (s.trim() === "" ? null : Number(s));

  const celda = (v: number | null) => v == null ? <span className="text-texto-3">—</span>
    : <span className={cn("cifra", v > 1.5 ? "font-medium text-serio" : v < 0.5 ? "text-alerta" : "text-texto-2")}>{v.toFixed(1)}×</span>;

  return (
    <div className="space-y-5">
      <Tarjeta>
        <TituloTarjeta titulo="Perfil transaccional declarado" descripcion={f.perfil_actualizado ? `Actualizado el ${fecha(f.perfil_actualizado)}` : "Lo que el cliente informó al vincularse. Se compara mes a mes con lo que realmente transa."}
          accion={puede && <Boton variante="primario" cargando={guardando} onClick={() => guardar({ perfil_volumen_mensual: num(vol), perfil_operaciones_mes: num(ops),
            perfil_ticket_promedio: num(tkt), perfil_paises: paises.split(",").map((p) => p.trim()).filter(Boolean) })}><Save className="size-4" aria-hidden />Guardar perfil</Boton>} />
        <fieldset disabled={!puede} className="space-y-3 px-5 pb-5 pt-3">
          {fallo && <Aviso tono="critico">{fallo}</Aviso>}
          {ok && <Aviso tono="ok">Perfil guardado. Las próximas evaluaciones del monitoreo lo usan para alertar desviaciones.</Aviso>}
          <div className="grid gap-4 md:grid-cols-4">
            <div><Etiqueta htmlFor="p-vol">Volumen mensual (COP)</Etiqueta><Entrada id="p-vol" type="number" min={0} value={vol} onChange={(e) => setVol(e.target.value)} /></div>
            <div><Etiqueta htmlFor="p-ops">Operaciones al mes</Etiqueta><Entrada id="p-ops" type="number" min={0} value={ops} onChange={(e) => setOps(e.target.value)} /></div>
            <div><Etiqueta htmlFor="p-tkt">Ticket promedio (COP)</Etiqueta><Entrada id="p-tkt" type="number" min={0} value={tkt} onChange={(e) => setTkt(e.target.value)} /></div>
            <div><Etiqueta htmlFor="p-pais">Países (separados por coma)</Etiqueta><Entrada id="p-pais" value={paises} onChange={(e) => setPaises(e.target.value)} /></div>
          </div>
        </fieldset>
      </Tarjeta>
      <Tarjeta>
        <TituloTarjeta titulo="Comportamiento real frente al declarado" descripcion="Veces el valor declarado. Más de 1,5× genera una alerta de desviación de perfil." />
        {!datos.datos ? <Esqueleto className="m-5 h-40" /> : !datos.datos.meses.length ? <Vacio titulo="Sin transacciones en los últimos meses" /> : (
          <div className="overflow-x-auto px-2 pb-3 pt-3">
            <table className="w-full min-w-[720px] text-[13px]">
              <thead><tr className="text-left text-texto-3">
                <th className="px-3 py-2 font-medium">Mes</th><th className="px-3 py-2 text-right font-medium">Monto pagado</th><th className="px-3 py-2 text-right font-medium">vs. declarado</th>
                <th className="px-3 py-2 text-right font-medium">Operaciones</th><th className="px-3 py-2 text-right font-medium">vs. declarado</th>
                <th className="px-3 py-2 text-right font-medium">Ticket</th><th className="px-3 py-2 text-right font-medium">vs. declarado</th></tr></thead>
              <tbody>
                {datos.datos.meses.map((m) => (
                  <tr key={m.periodo} className="border-t border-borde/70">
                    <td className="px-3 py-2.5">{mesCorto(m.periodo)}</td>
                    <td className="cifra px-3 py-2.5 text-right">{monedaCorta(m.monto_pagado)}</td><td className="px-3 py-2.5 text-right">{celda(m.desv_volumen)}</td>
                    <td className="cifra px-3 py-2.5 text-right">{entero(m.operaciones)}</td><td className="px-3 py-2.5 text-right">{celda(m.desv_operaciones)}</td>
                    <td className="cifra px-3 py-2.5 text-right">{monedaCorta(m.ticket_promedio)}</td><td className="px-3 py-2.5 text-right">{celda(m.desv_ticket)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Tarjeta>
    </div>
  );
}

// ---------- Expediente documental ----------
function Expediente({ f, cat, onGuardado }: { f: FichaCliente; cat: Catalogo; onGuardado: () => void }) {
  const [verCatalogo, setVerCatalogo] = useState(false);
  const senales = [...new Set(cat.modelos.filter((m) => f.modelos_negocio.includes(m.codigo)).flatMap((m) => m.senales_alerta))];
  return (
    <div className="space-y-5">
      <DocumentacionPropia clienteId={f.id} enlace={f.carpeta_onedrive} onGuardado={onGuardado} />
      <div>
        <button type="button" onClick={() => setVerCatalogo(!verCatalogo)} className="text-sm text-acento hover:underline">
          {verCatalogo ? "Ocultar" : "Ver"} la referencia del catálogo (paquete completo según modelo de negocio y riesgo)</button>
        {verCatalogo && (f.modelos_negocio.length
          ? <div className="mt-3"><VistaPaquete modelos={cat.modelos} paquete={{ nivel: f.paquete.nivel, nivel_es_provisional: f.paquete.nivel_es_provisional,
              tipo_persona: f.tipo_persona, modelos: f.modelos_negocio, riesgo_sugerido: f.riesgo_sugerido, monitoreo_sugerido: [],
              regimen: null, senales_alerta: senales, documentos: f.paquete.documentos }} /></div>
          : <p className="mt-2 text-sm text-texto-3">Defina el modelo de negocio en Resumen para ver el paquete de referencia.</p>)}
      </div>
    </div>
  );
}

// ---------- Bitácora ----------
interface EventoBitacora { origen: "alerta" | "ficha"; fecha: string; usuario: string; accion: string; nota: string | null;
  estado_anterior?: string | null; estado_nuevo?: string | null; titulo?: string; periodo?: string }

function Bitacora({ clienteId }: { clienteId: number }) {
  const { datos } = useDatos<{ eventos: EventoBitacora[] }>(`/api/clientes/${clienteId}/bitacora`);
  if (!datos) return <Esqueleto className="h-64" />;
  if (!datos.eventos.length) return <Tarjeta><Vacio titulo="Sin actividad registrada" /></Tarjeta>;
  return (
    <Tarjeta className="px-5 py-4">
      <ol className="space-y-3 border-l border-borde pl-4">
        {datos.eventos.map((e, i) => (
          <li key={i} className="text-[13px]">
            <p className="text-texto-3">{fechaHora(e.fecha)} · {e.usuario}</p>
            <p className="text-texto">
              {e.origen === "ficha" ? "Ficha del cliente"
                : <>{e.titulo} <span className="text-texto-3">({mesCorto(e.periodo!)})</span>: {e.accion === "detectada" ? "detectada"
                  : e.accion === "estado" ? `${NOMBRE_ESTADO[e.estado_anterior as keyof typeof NOMBRE_ESTADO] ?? e.estado_anterior} → ${NOMBRE_ESTADO[e.estado_nuevo as keyof typeof NOMBRE_ESTADO] ?? e.estado_nuevo}`
                  : e.accion === "asignacion" ? "cambio de analista" : "nota"}</>}
            </p>
            {e.nota && <p className="text-texto-2">{e.nota}</p>}
          </li>
        ))}
      </ol>
    </Tarjeta>
  );
}
