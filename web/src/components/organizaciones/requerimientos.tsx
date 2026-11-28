"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ClipboardList, ExternalLink, MessageSquarePlus, Pencil, Plus, Save, Search, Send, Trash2, X } from "lucide-react";
import { Aviso, Boton, Entrada, Esqueleto, Etiqueta, Insignia, Selector, Tarjeta, TituloTarjeta, Vacio } from "@/components/ui/basicos";
import { enviar, ErrorApi } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";
import { usePuedeGestionar, useSesion } from "@/lib/sesion";
import { fecha, fechaHora } from "@/lib/formato";
import { cn } from "@/lib/cn";

const area = "w-full rounded-lg border border-borde-fuerte bg-fondo px-3 py-2 text-sm text-texto focus:border-acento focus:outline-none";
type Tono = "neutro" | "acento" | "ok" | "alerta" | "serio" | "critico";

interface Catalogos {
  origenes: Record<string, string>; tipos: Record<string, string>; canales: Record<string, string>;
  prioridades: Record<string, string>; estados: Record<string, string>;
}
export interface BeneficiarioReq { id_beneficiario: string | null; nombre: string; actividad: string | null; notas?: string | null }
export interface Requerimiento {
  id: number; organizacion_id: number; consecutivo: string; dirigido_a: "organizacion" | "cliente"; cliente_id: number | null;
  cliente: string | null; origen: string; relacion_aliado_id: number | null; aliado: string | null; origen_detalle: string | null;
  solicitante: string | null; canal: string | null; tipo: string; asunto: string; descripcion: string | null; referencias_tx: string[];
  fecha_recibido: string; fecha_limite: string | null; prioridad: string; responsable: string | null; estado: string;
  fecha_envio: string | null; resumen_respuesta: string | null; carpeta_evidencias: string | null; organizacion: string;
  beneficiarios: BeneficiarioReq[];
  plazo: "atrasado" | "por_vencer" | "a_tiempo" | "sin_plazo" | "cumplido" | "fuera_de_plazo"; dias: number | null; abierto: boolean;
}
interface Detalle extends Requerimiento {
  eventos: { tipo: string; valor_anterior: string | null; valor_nuevo: string | null; comentario: string | null; usuario: string; fecha: string }[];
}
interface Resumen { abiertos: number; atrasados: number; por_vencer: number; fuera_de_plazo: number; total: number }
interface Opciones { clientes: { id: number; razon_social: string }[]; aliados: { id: number; nombre: string; estado: string }[] }

const TONO_ESTADO: Record<string, Tono> = { recibido: "acento", en_preparacion: "alerta", en_revision: "alerta", enviado: "ok", cerrado: "neutro", seguimiento: "serio" };
const SIGUIENTE: Record<string, string[]> = {
  recibido: ["en_preparacion", "en_revision", "enviado", "cerrado"], en_preparacion: ["en_revision", "enviado", "cerrado"],
  en_revision: ["en_preparacion", "enviado", "cerrado"], enviado: ["cerrado", "seguimiento"],
  seguimiento: ["en_preparacion", "en_revision", "enviado", "cerrado"], cerrado: ["seguimiento"],
};

export function Plazo({ q }: { q: Pick<Requerimiento, "plazo" | "dias" | "fecha_limite"> }) {
  const p = q.plazo;
  if (p === "atrasado") return <Insignia tono="critico">Atrasado {Math.abs(q.dias ?? 0)} d</Insignia>;
  if (p === "por_vencer") return <Insignia tono="alerta">{q.dias === 0 ? "Vence hoy" : `Vence en ${q.dias} d`}</Insignia>;
  if (p === "fuera_de_plazo") return <Insignia tono="serio">Enviado fuera de plazo</Insignia>;
  if (p === "cumplido") return <span className="text-xs text-ok">Cumplido</span>;
  if (p === "sin_plazo") return <span className="text-xs text-texto-3">Sin plazo</span>;
  return <span className="text-xs text-texto-2">{fecha(q.fecha_limite)}</span>;
}

function Metrica({ titulo, valor, tono }: { titulo: string; valor: number; tono?: "alerta" | "critico" }) {
  return (
    <div className="rounded-xl border border-borde bg-panel px-4 py-3">
      <p className="text-xs text-texto-3">{titulo}</p>
      <p className={cn("mt-1 text-2xl font-semibold tabular-nums", valor > 0 && tono === "alerta" && "text-alerta", valor > 0 && tono === "critico" && "text-critico")}>{valor}</p>
    </div>
  );
}

function useEnvio(onHecho: () => void | Promise<void>) {
  const [guardando, setGuardando] = useState(false);
  const [fallo, setFallo] = useState<string | null>(null);
  async function ejecutar<T = unknown>(ruta: string, cuerpo: unknown, metodo = "POST"): Promise<T | null> {
    setGuardando(true); setFallo(null);
    try { const r = await enviar<T>(ruta, cuerpo, metodo); await onHecho(); return r; }
    catch (e) { setFallo(e instanceof ErrorApi ? e.message : "No se pudo guardar."); return null; }
    finally { setGuardando(false); }
  }
  return { guardando, fallo, ejecutar };
}

// ================= Pestaña de la organización =================
export default function RequerimientosOrganizacion({ organizacionId, nombre, abrir, prellenar }:
  { organizacionId: number; nombre?: string; abrir?: number | null; prellenar?: string | null }) {
  const puede = usePuedeGestionar();
  const ruta = `/api/organizaciones/${organizacionId}/requerimientos`;
  const datos = useDatos<{ requerimientos: Requerimiento[]; resumen: Resumen } & Opciones>(ruta);
  const cat = useDatos<Catalogos>("/api/requerimientos/catalogos");
  const [abierto, setAbierto] = useState<number | null>(abrir ?? null);
  const [nuevo, setNuevo] = useState(Boolean(prellenar));
  const [filtro, setFiltro] = useState("abiertos");
  const [dirigido, setDirigido] = useState("");

  const visibles = useMemo(() => (datos.datos?.requerimientos ?? []).filter((q) =>
    (filtro === "todos" || (filtro === "abiertos" ? q.abierto : filtro === "urgentes" ? ["atrasado", "por_vencer"].includes(q.plazo) : !q.abierto))
    && (!dirigido || (dirigido === "organizacion" ? q.dirigido_a === "organizacion" : String(q.cliente_id) === dirigido))),
  [datos.datos, filtro, dirigido]);

  if (datos.error) return <Aviso tono="critico">{datos.error}</Aviso>;
  if (!datos.datos || !cat.datos) return <Esqueleto className="h-64" />;
  const { resumen } = datos.datos;
  const c = cat.datos;

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Metrica titulo="Abiertos" valor={resumen.abiertos} />
        <Metrica titulo="Atrasados" valor={resumen.atrasados} tono="critico" />
        <Metrica titulo="Vencen en 3 días o menos" valor={resumen.por_vencer} tono="alerta" />
        <Metrica titulo="Enviados fuera de plazo" valor={resumen.fuera_de_plazo} tono="alerta" />
      </div>

      {nuevo && <Formulario ruta={ruta} cat={c} opciones={datos.datos} prellenar={prellenar}
        onCerrar={() => setNuevo(false)} onGuardado={async (id) => { setNuevo(false); await datos.recargar(); setAbierto(id); }} />}

      <Tarjeta>
        <TituloTarjeta titulo={`Requerimientos${nombre ? ` de ${nombre}` : ""} y sus clientes`}
          descripcion="Lo que piden los aliados bancarios, reguladores y auditores, o lo que usted le pide a la organización o a sus clientes."
          accion={puede && !nuevo ? <Boton variante="primario" onClick={() => setNuevo(true)}><Plus className="size-4" aria-hidden />Nuevo requerimiento</Boton> : undefined} />
        <div className="flex flex-wrap items-center gap-1.5 px-5 pt-3">
          {[["abiertos", "Abiertos"], ["urgentes", "Atrasados o por vencer"], ["cerrados", "Enviados y cerrados"], ["todos", `Todos (${resumen.total})`]].map(([k, n]) => (
            <button key={k} onClick={() => setFiltro(k)}
              className={cn("rounded-md border px-2.5 py-1 text-xs", filtro === k ? "border-acento bg-acento-tenue text-acento" : "border-borde-fuerte text-texto-2")}>{n}</button>
          ))}
          <Selector aria-label="Dirigido a" className="ml-auto w-auto py-1 text-xs" value={dirigido} onChange={(e) => setDirigido(e.target.value)}>
            <option value="">Dirigidos a todos</option><option value="organizacion">A {nombre ?? "la organización"}</option>
            {datos.datos.clientes.map((cl) => <option key={cl.id} value={cl.id}>A {cl.razon_social}</option>)}
          </Selector>
        </div>
        <div className="overflow-x-auto px-5 pb-4 pt-3">
          {visibles.length === 0 ? (
            <Vacio icono={<ClipboardList className="size-5" />} titulo={resumen.total === 0 ? "Registre el primer requerimiento" : "Nada en este filtro"}
              texto={resumen.total === 0 ? "Cada solicitud de un banco, regulador o auditor queda con su plazo, responsable y evidencias." : "Pruebe con «Todos»."} />
          ) : (
            <TablaRequerimientos filas={visibles} cat={c} seleccionado={abierto} onElegir={(id) => setAbierto(abierto === id ? null : id)} />
          )}
        </div>
      </Tarjeta>

      {abierto && <DetalleRequerimiento key={abierto} ruta={`${ruta}/${abierto}`} cat={c} opciones={datos.datos}
        onCambio={datos.recargar} onCerrar={() => setAbierto(null)} />}
    </div>
  );
}

function TablaRequerimientos({ filas, cat, seleccionado, onElegir, enlace }:
  { filas: Requerimiento[]; cat: Catalogos; seleccionado?: number | null; onElegir?: (id: number) => void; enlace?: (q: Requerimiento) => string }) {
  return (
    <table className="w-full min-w-[900px] text-left text-sm">
      <thead className="text-xs uppercase tracking-wider text-texto-3">
        <tr><th className="py-2 pr-4">Requerimiento</th><th className="pr-4">Dirigido a</th><th className="pr-4">Origen</th>
          <th className="pr-4">Plazo</th><th className="pr-4">Estado</th><th>Responsable</th></tr>
      </thead>
      <tbody className="divide-y divide-borde">
        {filas.map((q) => {
          const titulo = <><p className="font-medium">{q.asunto}</p>
            <p className="text-xs text-texto-3">{q.consecutivo} · {cat.tipos[q.tipo]}{q.prioridad === "alta" && <span className="text-critico"> · prioridad alta</span>}</p></>;
          return (
            <tr key={q.id} onClick={onElegir ? () => onElegir(q.id) : undefined}
              className={cn(onElegir && "cursor-pointer hover:bg-panel-2", seleccionado === q.id && "bg-acento-tenue/40")}>
              <td className="py-3 pr-4">{enlace ? <Link href={enlace(q)} className="hover:underline">{titulo}</Link> : titulo}</td>
              <td className="pr-4 text-texto-2">{q.dirigido_a === "cliente" ? q.cliente : q.organizacion}</td>
              <td className="pr-4 text-texto-2">{q.origen === "aliado" ? q.aliado : q.origen_detalle ?? cat.origenes[q.origen]}</td>
              <td className="pr-4"><Plazo q={q} /></td>
              <td className="pr-4"><Insignia tono={TONO_ESTADO[q.estado]}>{cat.estados[q.estado]}</Insignia></td>
              <td className="text-texto-2">{q.responsable ?? "—"}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

// ================= Lista compacta (perfil del cliente y detalle del aliado) =================
export function RequerimientosRelacionados({ ruta, organizacionId, prellenar, titulo, vacio }:
  { ruta: string; organizacionId: number; prellenar: string; titulo: string; vacio: string }) {
  const puede = usePuedeGestionar();
  const datos = useDatos<{ requerimientos: Requerimiento[]; resumen: Resumen }>(ruta);
  const cat = useDatos<Catalogos>("/api/requerimientos/catalogos");
  const base = `/organizaciones/${organizacionId}?tab=requerimientos`;
  if (datos.error) return <Aviso tono="critico">{datos.error}</Aviso>;
  if (!datos.datos || !cat.datos) return <Esqueleto className="h-24" />;
  const r = datos.datos.resumen;
  return (
    <Tarjeta>
      <TituloTarjeta titulo={titulo}
        descripcion={r.total ? `${r.abiertos} abiertos${r.atrasados ? ` · ${r.atrasados} atrasados` : ""}${r.por_vencer ? ` · ${r.por_vencer} por vencer` : ""}` : undefined}
        accion={puede ? <Link href={`${base}&nuevo=${prellenar}`}><Boton><Plus className="size-4" aria-hidden />Nuevo requerimiento</Boton></Link> : undefined} />
      <div className="overflow-x-auto px-5 pb-4 pt-3">
        {r.total === 0 ? <p className="text-sm text-texto-3">{vacio}</p>
          : <TablaRequerimientos filas={datos.datos.requerimientos} cat={cat.datos} enlace={(q) => `${base}&req=${q.id}`} />}
      </div>
    </Tarjeta>
  );
}

// ================= Alta y edición =================
function Formulario({ ruta, cat, opciones, prellenar, actual, onCerrar, onGuardado }:
  { ruta: string; cat: Catalogos; opciones: Opciones; prellenar?: string | null; actual?: Detalle;
    onCerrar: () => void; onGuardado: (id: number) => void | Promise<void> }) {
  const { username } = useSesion();
  const [tipoPre, idPre] = (prellenar ?? "").split(":");
  const hoy = new Date().toISOString().slice(0, 10);
  const [f, setF] = useState({
    dirigido_a: actual?.dirigido_a ?? (tipoPre === "cliente" ? "cliente" : "organizacion"),
    cliente_id: actual?.cliente_id ? String(actual.cliente_id) : tipoPre === "cliente" ? idPre : "",
    origen: actual?.origen ?? (tipoPre === "aliado" ? "aliado" : ""),
    relacion_aliado_id: actual?.relacion_aliado_id ? String(actual.relacion_aliado_id) : tipoPre === "aliado" ? idPre : "",
    origen_detalle: actual?.origen_detalle ?? "", solicitante: actual?.solicitante ?? "", canal: actual?.canal ?? "correo",
    tipo: actual?.tipo ?? "", asunto: actual?.asunto ?? "", descripcion: actual?.descripcion ?? "",
    referencias_tx: (actual?.referencias_tx ?? []).join(", "), fecha_recibido: actual?.fecha_recibido ?? hoy,
    fecha_limite: actual?.fecha_limite ?? "", prioridad: actual?.prioridad ?? "media", responsable: actual?.responsable ?? username ?? "",
    carpeta_evidencias: actual?.carpeta_evidencias ?? "",
  });
  const [beneficiarios, setBeneficiarios] = useState<BeneficiarioReq[]>(actual?.beneficiarios ?? []);
  const poner = (x: Partial<typeof f>) => setF((v) => ({ ...v, ...x }));
  const { guardando, fallo, ejecutar } = useEnvio(() => undefined);
  const listo = f.asunto.trim().length >= 5 && f.tipo && f.origen && f.fecha_recibido
    && (f.dirigido_a === "organizacion" || f.cliente_id) && (f.origen !== "aliado" || f.relacion_aliado_id);

  async function guardar() {
    const v = (s: string) => s.trim() || null;
    const cuerpo = {
      dirigido_a: f.dirigido_a, cliente_id: f.dirigido_a === "cliente" ? Number(f.cliente_id) : null, origen: f.origen,
      relacion_aliado_id: f.origen === "aliado" ? Number(f.relacion_aliado_id) : null, origen_detalle: v(f.origen_detalle),
      solicitante: v(f.solicitante), canal: f.canal || null, tipo: f.tipo, asunto: f.asunto.trim(), descripcion: v(f.descripcion),
      referencias_tx: f.referencias_tx.split(/[,\n]/).map((x) => x.trim()).filter(Boolean), fecha_recibido: f.fecha_recibido,
      fecha_limite: f.fecha_limite || null, prioridad: f.prioridad, responsable: v(f.responsable), carpeta_evidencias: v(f.carpeta_evidencias),
      beneficiarios: beneficiarios.map((b) => ({ id_beneficiario: b.id_beneficiario?.trim() || null, nombre: b.nombre.trim(),
        actividad: b.actividad?.trim() || null, notas: b.notas ?? null })).filter((b) => b.nombre),
    };
    if (actual) { const r = await ejecutar(ruta, cuerpo, "PATCH"); if (r) await onGuardado(actual.id); }
    else { const r = await ejecutar<{ id: number }>(ruta, cuerpo); if (r?.id) await onGuardado(r.id); }
  }

  const contenido = (
    <div className="space-y-5">
      <fieldset className="grid gap-4 md:grid-cols-3">
        <legend className="mb-2 text-[13px] font-medium text-texto-2">A quién y de quién</legend>
        <div><Etiqueta htmlFor="rq-dir">Dirigido a</Etiqueta>
          <Selector id="rq-dir" value={f.dirigido_a} onChange={(e) => poner({ dirigido_a: e.target.value as "organizacion" | "cliente" })}>
            <option value="organizacion">La organización</option><option value="cliente">Un cliente de la organización</option></Selector></div>
        {f.dirigido_a === "cliente" && <div><Etiqueta htmlFor="rq-cli">Cliente</Etiqueta>
          <Selector id="rq-cli" value={f.cliente_id} onChange={(e) => poner({ cliente_id: e.target.value })}>
            <option value="">Seleccione…</option>{opciones.clientes.map((c) => <option key={c.id} value={c.id}>{c.razon_social}</option>)}</Selector></div>}
        <div><Etiqueta htmlFor="rq-ori">Origen</Etiqueta>
          <Selector id="rq-ori" value={f.origen} onChange={(e) => poner({ origen: e.target.value })}>
            <option value="">Seleccione…</option>{Object.entries(cat.origenes).map(([k, n]) => <option key={k} value={k}>{n}</option>)}</Selector></div>
        {f.origen === "aliado" ? <div><Etiqueta htmlFor="rq-ali">Aliado bancario</Etiqueta>
          <Selector id="rq-ali" value={f.relacion_aliado_id} onChange={(e) => poner({ relacion_aliado_id: e.target.value })}>
            <option value="">Seleccione…</option>{opciones.aliados.map((a) => <option key={a.id} value={a.id}>{a.nombre}</option>)}</Selector></div>
          : f.origen && !["oficial", "director"].includes(f.origen) ? <div><Etiqueta htmlFor="rq-od">¿Quién exactamente?</Etiqueta>
            <Entrada id="rq-od" value={f.origen_detalle} placeholder={f.origen === "regulador" ? "UIAF, Supersociedades…" : "Firma auditora"}
              onChange={(e) => poner({ origen_detalle: e.target.value })} /></div> : null}
        <div><Etiqueta htmlFor="rq-sol">Persona que lo pidió</Etiqueta><Entrada id="rq-sol" value={f.solicitante} onChange={(e) => poner({ solicitante: e.target.value })} /></div>
        <div><Etiqueta htmlFor="rq-can">Canal</Etiqueta>
          <Selector id="rq-can" value={f.canal} onChange={(e) => poner({ canal: e.target.value })}>
            {Object.entries(cat.canales).map(([k, n]) => <option key={k} value={k}>{n}</option>)}</Selector></div>
      </fieldset>
      <fieldset className="grid gap-4 md:grid-cols-3">
        <legend className="mb-2 text-[13px] font-medium text-texto-2">Qué piden y para cuándo</legend>
        <div className="md:col-span-2"><Etiqueta htmlFor="rq-as">Asunto</Etiqueta>
          <Entrada id="rq-as" value={f.asunto} placeholder="KYC actualizado de Paxum" onChange={(e) => poner({ asunto: e.target.value })} /></div>
        <div><Etiqueta htmlFor="rq-tipo">Tipo</Etiqueta>
          <Selector id="rq-tipo" value={f.tipo} onChange={(e) => poner({ tipo: e.target.value })}>
            <option value="">Seleccione…</option>{Object.entries(cat.tipos).map(([k, n]) => <option key={k} value={k}>{n}</option>)}</Selector></div>
        <div className="md:col-span-3"><Etiqueta htmlFor="rq-desc">Descripción</Etiqueta>
          <textarea id="rq-desc" rows={3} className={area} value={f.descripcion} placeholder="Qué pide exactamente, documentos o preguntas"
            onChange={(e) => poner({ descripcion: e.target.value })} /></div>
        <div><Etiqueta htmlFor="rq-rec">Recibido el</Etiqueta><Entrada id="rq-rec" type="date" max={hoy} value={f.fecha_recibido} onChange={(e) => poner({ fecha_recibido: e.target.value })} /></div>
        <div><Etiqueta htmlFor="rq-lim">Fecha límite</Etiqueta><Entrada id="rq-lim" type="date" value={f.fecha_limite} onChange={(e) => poner({ fecha_limite: e.target.value })} /></div>
        <div><Etiqueta htmlFor="rq-pri">Prioridad</Etiqueta>
          <Selector id="rq-pri" value={f.prioridad} onChange={(e) => poner({ prioridad: e.target.value })}>
            {Object.entries(cat.prioridades).map(([k, n]) => <option key={k} value={k}>{n}</option>)}</Selector></div>
        <div><Etiqueta htmlFor="rq-res">Responsable</Etiqueta><Entrada id="rq-res" value={f.responsable} onChange={(e) => poner({ responsable: e.target.value })} /></div>
        <div className="md:col-span-2"><Etiqueta htmlFor="rq-tx">Transacciones relacionadas (separadas por coma)</Etiqueta>
          <Entrada id="rq-tx" value={f.referencias_tx} placeholder="ID de transacción o referencia" onChange={(e) => poner({ referencias_tx: e.target.value })} /></div>
        <div className="md:col-span-3"><Etiqueta htmlFor="rq-carp">Carpeta de evidencias en OneDrive</Etiqueta>
          <Entrada id="rq-carp" value={f.carpeta_evidencias} placeholder="https://… (Requerimientos/REQ-2026-001 - Asunto)" onChange={(e) => poner({ carpeta_evidencias: e.target.value })} /></div>
      </fieldset>
      <EditorBeneficiarios clienteId={f.dirigido_a === "cliente" && f.cliente_id ? Number(f.cliente_id) : null}
        valor={beneficiarios} onCambio={setBeneficiarios} />
      {fallo && <Aviso tono="critico">{fallo}</Aviso>}
      <div className="flex gap-2">
        <Boton variante="primario" cargando={guardando} disabled={!listo} onClick={guardar}><Save className="size-4" aria-hidden />{actual ? "Guardar cambios" : "Registrar requerimiento"}</Boton>
        <Boton variante="fantasma" onClick={onCerrar}>Cancelar</Boton>
      </div>
    </div>
  );

  if (actual) return <div className="rounded-xl border border-borde-fuerte p-4">{contenido}</div>;
  return (
    <Tarjeta>
      <TituloTarjeta titulo="Nuevo requerimiento" descripcion="El consecutivo (REQ-AAAA-NNN) se asigna al guardar."
        accion={<Boton variante="fantasma" onClick={onCerrar}><X className="size-4" aria-hidden />Cancelar</Boton>} />
      <div className="px-5 pb-5 pt-3">{contenido}</div>
    </Tarjeta>
  );
}

// ================= Detalle =================
function Dato({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return <div><p className="text-xs text-texto-3">{titulo}</p><div className="text-sm">{children || <span className="text-texto-3">—</span>}</div></div>;
}

const TIPO_EVENTO: Record<string, string> = { alta: "Registrado", estado: "Estado", nota: "Nota", edicion: "Editado" };

function DetalleRequerimiento({ ruta, cat, opciones, onCambio, onCerrar }:
  { ruta: string; cat: Catalogos; opciones: Opciones; onCambio: () => Promise<void>; onCerrar: () => void }) {
  const puede = usePuedeGestionar();
  const d = useDatos<Detalle>(ruta);
  const [modo, setModo] = useState<"ver" | "editar" | "estado" | "nota">("ver");
  const hecho = async () => { setModo("ver"); await d.recargar(); await onCambio(); };

  if (d.error) return <Aviso tono="critico">{d.error}</Aviso>;
  if (!d.datos) return <Esqueleto className="h-72" />;
  const q = d.datos;

  return (
    <Tarjeta>
      <TituloTarjeta titulo={`${q.consecutivo} · ${q.asunto}`}
        descripcion={`${cat.tipos[q.tipo]} · dirigido a ${q.dirigido_a === "cliente" ? q.cliente : q.organizacion}`}
        accion={<span className="flex flex-wrap gap-2">
          {puede && modo === "ver" && <>
            <Boton variante="primario" onClick={() => setModo("estado")}><Send className="size-4" aria-hidden />Cambiar estado</Boton>
            <Boton onClick={() => setModo("nota")}><MessageSquarePlus className="size-4" aria-hidden />Nota</Boton>
            <Boton onClick={() => setModo("editar")}><Pencil className="size-4" aria-hidden />Editar</Boton></>}
          <Boton variante="fantasma" onClick={onCerrar}><X className="size-4" aria-hidden />Cerrar</Boton></span>} />
      <div className="space-y-5 px-5 pb-5 pt-3">
        <div className="flex flex-wrap items-center gap-2">
          <Insignia tono={TONO_ESTADO[q.estado]}>{cat.estados[q.estado]}</Insignia><Plazo q={q} />
          {q.prioridad === "alta" && <Insignia tono="critico">Prioridad alta</Insignia>}
        </div>

        {modo === "estado" && <CambioEstado ruta={`${ruta}/estado`} q={q} cat={cat} onHecho={hecho} onCancelar={() => setModo("ver")} />}
        {modo === "nota" && <NuevaNota ruta={`${ruta}/notas`} onHecho={hecho} onCancelar={() => setModo("ver")} />}
        {modo === "editar" && <Formulario ruta={ruta} cat={cat} opciones={opciones} actual={q} onCerrar={() => setModo("ver")} onGuardado={hecho} />}

        {modo !== "editar" && (
          <div className="grid gap-6 md:grid-cols-3">
            <section className="space-y-3">
              <Dato titulo="Origen">{q.origen === "aliado" ? `${q.aliado} (aliado bancario)` : [cat.origenes[q.origen], q.origen_detalle].filter(Boolean).join(" · ")}</Dato>
              <Dato titulo="Solicitante · canal">{[q.solicitante, q.canal && cat.canales[q.canal]].filter(Boolean).join(" · ")}</Dato>
              <Dato titulo="Responsable">{q.responsable}</Dato>
            </section>
            <section className="space-y-3">
              <Dato titulo="Recibido · fecha límite">{fecha(q.fecha_recibido)} · {q.fecha_limite ? fecha(q.fecha_limite) : "sin plazo"}</Dato>
              <Dato titulo="Enviado">{q.fecha_envio ? fecha(q.fecha_envio) : null}</Dato>
              <Dato titulo="Transacciones relacionadas">{q.referencias_tx.join(", ")}</Dato>
            </section>
            <section className="space-y-3">
              <Dato titulo="Evidencias">{q.carpeta_evidencias
                ? <a href={q.carpeta_evidencias} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-acento hover:underline">Abrir carpeta en OneDrive<ExternalLink className="size-3.5" aria-hidden /></a>
                : <span className="text-texto-3">Sin carpeta enlazada</span>}</Dato>
              {q.resumen_respuesta && <Dato titulo="Respuesta enviada"><span className="whitespace-pre-line">{q.resumen_respuesta}</span></Dato>}
            </section>
            {q.beneficiarios.length > 0 && <div className="md:col-span-3"><Dato titulo="Beneficiarios involucrados">
              <ul className="mt-1 divide-y divide-borde">{q.beneficiarios.map((b, i) => (
                <li key={i} className="py-1.5"><span className="font-medium">{b.nombre}</span>{b.id_beneficiario && <span className="text-texto-3"> · {b.id_beneficiario}</span>}
                  {b.actividad ? <span className="text-texto-2"> · {b.actividad}</span> : <span className="text-alerta"> · actividad sin registrar</span>}</li>))}</ul></Dato></div>}
            {q.descripcion && <div className="md:col-span-3"><Dato titulo="Descripción"><span className="whitespace-pre-line text-texto-2">{q.descripcion}</span></Dato></div>}
          </div>
        )}

        <div>
          <h3 className="mb-2 text-[13px] font-medium text-texto-2">Bitácora</h3>
          <ul className="divide-y divide-borde text-sm">
            {q.eventos.map((e, i) => (
              <li key={i} className="flex flex-wrap gap-x-3 py-2">
                <span className="w-36 shrink-0 text-xs text-texto-3">{fechaHora(e.fecha)}</span>
                <span className="font-medium">{TIPO_EVENTO[e.tipo] ?? e.tipo}</span>
                <span className="text-texto-2">{e.tipo === "edicion" ? `campos: ${e.valor_nuevo}` : e.valor_anterior ? `${e.valor_anterior} → ${e.valor_nuevo}` : e.valor_nuevo}</span>
                <span className="ml-auto text-xs text-texto-3">{e.usuario}</span>
                {e.comentario && <span className="basis-full whitespace-pre-line pl-[9.75rem] text-xs text-texto-2">{e.comentario}</span>}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Tarjeta>
  );
}

function CambioEstado({ ruta, q, cat, onHecho, onCancelar }:
  { ruta: string; q: Detalle; cat: Catalogos; onHecho: () => Promise<void>; onCancelar: () => void }) {
  const opciones = SIGUIENTE[q.estado] ?? [];
  const [estado, setEstado] = useState(opciones[0] ?? "");
  const [comentario, setComentario] = useState("");
  const [resumen, setResumen] = useState("");
  const [envio, setEnvio] = useState(new Date().toISOString().slice(0, 10));
  const { guardando, fallo, ejecutar } = useEnvio(onHecho);
  const exigeMotivo = estado === "cerrado" || estado === "seguimiento";
  const listo = estado && (estado === "enviado" ? resumen.trim().length >= 10 : !exigeMotivo || comentario.trim().length >= 10);

  return (
    <div className="space-y-4 rounded-xl border border-borde-fuerte p-4">
      <div className="flex flex-wrap gap-1.5">
        {opciones.map((k) => (
          <button key={k} type="button" onClick={() => setEstado(k)}
            className={cn("rounded-md border px-2.5 py-1 text-xs", estado === k ? "border-acento bg-acento-tenue text-acento" : "border-borde-fuerte text-texto-2")}>{cat.estados[k]}</button>
        ))}
      </div>
      {estado === "enviado" && (
        <div className="grid gap-4 md:grid-cols-4">
          <div><Etiqueta htmlFor="ce-env">Fecha de envío</Etiqueta><Entrada id="ce-env" type="date" value={envio} onChange={(e) => setEnvio(e.target.value)} /></div>
          <div className="md:col-span-3"><Etiqueta htmlFor="ce-res">Qué se envió</Etiqueta>
            <textarea id="ce-res" rows={3} className={area} value={resumen} placeholder="Ej.: se envió RUT, cámara de comercio y matriz de beneficiarios finales de Paxum"
              onChange={(e) => setResumen(e.target.value)} /></div>
        </div>
      )}
      <div><Etiqueta htmlFor="ce-com">{exigeMotivo ? "Motivo" : "Comentario (opcional)"}</Etiqueta>
        <textarea id="ce-com" rows={2} className={area} value={comentario}
          placeholder={estado === "seguimiento" ? "Ej.: el banco pidió aclarar el origen de fondos" : estado === "cerrado" ? "Ej.: el banco confirmó que quedó satisfecho" : ""}
          onChange={(e) => setComentario(e.target.value)} /></div>
      {fallo && <Aviso tono="critico">{fallo}</Aviso>}
      <div className="flex gap-2">
        <Boton variante="primario" cargando={guardando} disabled={!listo}
          onClick={() => ejecutar(ruta, { estado, comentario: comentario.trim() || null, ...(estado === "enviado" ? { resumen_respuesta: resumen, fecha_envio: envio } : {}) })}>
          <Save className="size-4" aria-hidden />Pasar a «{cat.estados[estado] ?? "…"}»</Boton>
        <Boton variante="fantasma" onClick={onCancelar}>Cancelar</Boton>
      </div>
    </div>
  );
}

function NuevaNota({ ruta, onHecho, onCancelar }: { ruta: string; onHecho: () => Promise<void>; onCancelar: () => void }) {
  const [texto, setTexto] = useState("");
  const { guardando, fallo, ejecutar } = useEnvio(onHecho);
  return (
    <div className="space-y-3 rounded-xl border border-borde-fuerte p-4">
      <textarea rows={3} className={area} value={texto} aria-label="Nota" placeholder="Ej.: se le pidieron los estados financieros al cliente por correo"
        onChange={(e) => setTexto(e.target.value)} />
      {fallo && <Aviso tono="critico">{fallo}</Aviso>}
      <div className="flex gap-2">
        <Boton variante="primario" cargando={guardando} disabled={texto.trim().length < 3} onClick={() => ejecutar(ruta, { comentario: texto })}>
          <Save className="size-4" aria-hidden />Guardar nota</Boton>
        <Boton variante="fantasma" onClick={onCancelar}>Cancelar</Boton>
      </div>
    </div>
  );
}

// ================= Beneficiarios involucrados =================
function EditorBeneficiarios({ clienteId, valor, onCambio }:
  { clienteId: number | null; valor: BeneficiarioReq[]; onCambio: (v: BeneficiarioReq[]) => void }) {
  const [q, setQ] = useState("");
  const busqueda = useDatos<{ beneficiarios: { id_beneficiario: string | null; nombre: string; pagos: number; monto: number }[] }>(
    clienteId && q.trim().length >= 2 ? `/api/clientes/${clienteId}/beneficiarios/buscar?q=${encodeURIComponent(q.trim())}` : null);
  const poner = (i: number, x: Partial<BeneficiarioReq>) => onCambio(valor.map((b, j) => (j === i ? { ...b, ...x } : b)));
  const agregar = (b: BeneficiarioReq) => {
    const clave = (b.id_beneficiario || b.nombre).toLowerCase();
    if (!valor.some((x) => (x.id_beneficiario || x.nombre).toLowerCase() === clave)) onCambio([...valor, b]);
    setQ("");
  };
  return (
    <fieldset className="space-y-3">
      <legend className="mb-1 text-[13px] font-medium text-texto-2">Beneficiarios involucrados</legend>
      {clienteId ? (
        <div className="relative max-w-md">
          <Search className="pointer-events-none absolute left-3 top-2.5 size-4 text-texto-3" aria-hidden />
          <Entrada className="pl-9" placeholder="Buscar entre los beneficiarios del subcliente" value={q} onChange={(e) => setQ(e.target.value)} />
          {q.trim().length >= 2 && (busqueda.datos?.beneficiarios.length ?? 0) > 0 && (
            <div className="mt-1 rounded-lg border border-borde-fuerte bg-panel">
              {busqueda.datos!.beneficiarios.map((b) => (
                <button key={`${b.id_beneficiario}-${b.nombre}`} type="button" className="block w-full px-3 py-2 text-left text-sm hover:bg-panel-2"
                  onClick={() => agregar({ id_beneficiario: b.id_beneficiario, nombre: b.nombre, actividad: null })}>
                  <span className="font-medium">{b.nombre}</span> <span className="text-texto-3">{b.id_beneficiario} · {b.pagos} pagos</span>
                </button>
              ))}
            </div>
          )}
        </div>
      ) : <p className="text-xs text-texto-3">Para buscar entre los beneficiarios, dirija el requerimiento a un subcliente. También puede agregarlos a mano.</p>}
      {valor.length > 0 && (
        <div className="space-y-2">
          {valor.map((b, i) => (
            <div key={i} className="grid gap-2 md:grid-cols-[1.2fr_0.8fr_1.6fr_auto]">
              <Entrada aria-label="Nombre del beneficiario" value={b.nombre} onChange={(e) => poner(i, { nombre: e.target.value })} />
              <Entrada aria-label="Documento" placeholder="Documento" value={b.id_beneficiario ?? ""} onChange={(e) => poner(i, { id_beneficiario: e.target.value })} />
              <Entrada aria-label="Actividad del beneficiario" placeholder="Actividad (ej.: comercio de ropa)" value={b.actividad ?? ""} onChange={(e) => poner(i, { actividad: e.target.value })} />
              <Boton variante="fantasma" aria-label="Quitar" onClick={() => onCambio(valor.filter((_, j) => j !== i))}><Trash2 className="size-4" aria-hidden /></Boton>
            </div>
          ))}
        </div>
      )}
      <button type="button" className="text-xs text-acento hover:underline" onClick={() => onCambio([...valor, { id_beneficiario: null, nombre: "", actividad: null }])}>
        + Agregar beneficiario a mano</button>
    </fieldset>
  );
}
