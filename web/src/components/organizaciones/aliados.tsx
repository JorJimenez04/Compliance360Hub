"use client";

import { useMemo, useState } from "react";
import { AlertTriangle, ArrowRightLeft, Building2, Check, ExternalLink, FileText, Landmark, Pencil, Plus, Save, Search, X } from "lucide-react";
import { Aviso, Boton, Entrada, Esqueleto, Etiqueta, Insignia, Selector, Tarjeta, TituloTarjeta, Vacio, tonoRiesgo } from "@/components/ui/basicos";
import { enviar, ErrorApi } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";
import { usePuedeGestionar } from "@/lib/sesion";
import { fecha, fechaHora } from "@/lib/formato";
import { cn } from "@/lib/cn";
import { RequerimientosRelacionados } from "./requerimientos";

const area = "w-full rounded-lg border border-borde-fuerte bg-fondo px-3 py-2 text-sm text-texto focus:border-acento focus:outline-none";

type Tono = "neutro" | "acento" | "ok" | "alerta" | "serio" | "critico";
interface AvisoAliado { tono: Tono; texto: string }
interface Catalogos {
  tipos_entidad: Record<string, string>; estados: Record<string, string>; servicios: Record<string, string>;
  niveles: string[]; dd_estados: Record<string, string>; dd_niveles: Record<string, string>;
}
interface Aliado {
  id: number; aliado_id: number; nombre: string; razon_social: string | null; identificacion: string | null; pais: string | null;
  tipo_entidad: string | null; regulado: boolean; regulador: string | null; licencia: string | null; sitio_web: string | null;
  notas_entidad: string | null; organizaciones: number;
  estado: string; fecha_estado: string; fecha_inicio: string | null; servicios: string[]; monedas: string[];
  nivel_riesgo: string | null; proxima_revision: string | null; dd_estado: string; dd_fecha: string | null; dd_nivel: string | null;
  exigencias: string[]; contacto_cumplimiento: string | null; correo_cumplimiento: string | null; telefono_cumplimiento: string | null;
  contacto_comercial: string | null; correo_comercial: string | null; notas: string | null; avisos: AvisoAliado[];
  vence_contrato: string | null; vence_poliza: string | null; vence_licencia: string | null;
  carpeta_web_url: string | null; carpeta_nombre: string | null; carpeta_revisada_en: string | null;
  documentos: DocumentosAliado;
}
interface ArchivoAliado { id: number; codigo: string | null; nombre_archivo: string; ruta: string | null; web_url: string | null; asignacion: string }
interface DocumentosAliado {
  filas: { codigo: string; nombre: string; exigido: boolean; cargado: boolean; archivos: ArchivoAliado[]; vence: string | null;
    estado_vence: "vencido" | "por_vencer" | "vigente" | null }[];
  sin_reconocer: ArchivoAliado[]; completo: boolean; carpeta: boolean;
}
interface Detalle extends Aliado {
  historial: { campo: string; valor_anterior: string | null; valor_nuevo: string | null; motivo: string | null; usuario: string; fecha: string }[];
  otras_organizaciones: { nombre: string; estado: string }[];
}
interface Resumen { total: number; activos: number; diligencia_pendiente: number; revision_vencida: number; riesgo_alto: number }

const TONO_ESTADO: Record<string, Tono> = { activo: "ok", onboarding: "acento", prospecto: "neutro", suspendido: "alerta", terminado: "neutro" };
const TONO_DD: Record<string, Tono> = { completa: "ok", en_proceso: "alerta", no_iniciada: "critico", rechazada: "critico" };
const CAMPOS_BITACORA: Record<string, string> = { alta: "Alta", estado: "Estado", riesgo: "Riesgo", diligencia: "Diligencia", revision: "Próxima revisión" };
const lista = (t: string) => t.split(/[,\n]/).map((x) => x.trim()).filter(Boolean);

function useEnvio(onHecho: () => void | Promise<void>) {
  const [guardando, setGuardando] = useState(false);
  const [fallo, setFallo] = useState<string | null>(null);
  async function ejecutar(ruta: string, cuerpo: unknown, metodo = "POST") {
    setGuardando(true); setFallo(null);
    try { const r = await enviar<{ id?: number }>(ruta, cuerpo, metodo); await onHecho(); return r ?? {}; }
    catch (e) { setFallo(e instanceof ErrorApi ? e.message : "No se pudo guardar."); return null; }
    finally { setGuardando(false); }
  }
  return { guardando, fallo, ejecutar };
}

function Metrica({ titulo, valor, tono }: { titulo: string; valor: number; tono?: "alerta" | "critico" }) {
  return (
    <div className="rounded-xl border border-borde bg-panel px-4 py-3">
      <p className="text-xs text-texto-3">{titulo}</p>
      <p className={cn("mt-1 text-2xl font-semibold tabular-nums", valor > 0 && tono === "alerta" && "text-alerta",
        valor > 0 && tono === "critico" && "text-critico")}>{valor}</p>
    </div>
  );
}

function Chips({ opciones, valor, onCambio }: { opciones: Record<string, string>; valor: string[]; onCambio: (v: string[]) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {Object.entries(opciones).map(([k, n]) => {
        const activo = valor.includes(k);
        return (
          <button key={k} type="button" onClick={() => onCambio(activo ? valor.filter((x) => x !== k) : [...valor, k])}
            className={cn("rounded-md border px-2.5 py-1 text-xs transition-colors",
              activo ? "border-acento bg-acento-tenue text-acento" : "border-borde-fuerte text-texto-2 hover:border-texto-3")}>{n}</button>
        );
      })}
    </div>
  );
}

// ================= Pestaña =================
export default function AliadosOrganizacion({ organizacionId, nombre }: { organizacionId: number; nombre?: string }) {
  const puede = usePuedeGestionar();
  const datos = useDatos<{ aliados: Aliado[]; resumen: Resumen }>(`/api/organizaciones/${organizacionId}/aliados`);
  const cat = useDatos<Catalogos>("/api/aliados/catalogos");
  const [abierto, setAbierto] = useState<number | null>(null);
  const [nuevo, setNuevo] = useState(false);
  const [filtro, setFiltro] = useState("vigentes");

  const visibles = useMemo(() => (datos.datos?.aliados ?? []).filter((a) =>
    filtro === "todos" ? true : filtro === "vigentes" ? ["activo", "onboarding"].includes(a.estado) : a.avisos.length > 0),
  [datos.datos, filtro]);

  if (datos.error) return <Aviso tono="critico">{datos.error}</Aviso>;
  if (!datos.datos || !cat.datos) return <Esqueleto className="h-64" />;
  const { resumen } = datos.datos;
  const c = cat.datos;

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Metrica titulo="Activos" valor={resumen.activos} />
        <Metrica titulo="Diligencia pendiente (vigentes)" valor={resumen.diligencia_pendiente} tono="critico" />
        <Metrica titulo="Revisión vencida" valor={resumen.revision_vencida} tono="critico" />
        <Metrica titulo="Riesgo alto (vigentes)" valor={resumen.riesgo_alto} tono="alerta" />
      </div>

      {nuevo && <NuevoAliado organizacionId={organizacionId} cat={c}
        onCerrar={() => setNuevo(false)} onCreado={async (id) => { setNuevo(false); await datos.recargar(); setAbierto(id); }} />}

      <Tarjeta>
        <TituloTarjeta titulo={`Aliados bancarios${nombre ? ` de ${nombre}` : ""}`}
          descripcion="Bancos, PSP, entidades de pago y VASP con los que opera la organización. Haga clic en uno para ver su relación."
          accion={puede && !nuevo ? <Boton variante="primario" onClick={() => setNuevo(true)}><Plus className="size-4" aria-hidden />Nuevo aliado</Boton> : undefined} />
        <div className="flex flex-wrap gap-1.5 px-5 pt-3">
          {[["vigentes", "Activos y en onboarding"], ["atencion", "Requieren atención"], ["todos", `Todos (${resumen.total})`]].map(([k, n]) => (
            <button key={k} onClick={() => setFiltro(k)}
              className={cn("rounded-md border px-2.5 py-1 text-xs", filtro === k ? "border-acento bg-acento-tenue text-acento" : "border-borde-fuerte text-texto-2")}>{n}</button>
          ))}
        </div>
        <div className="overflow-x-auto px-5 pb-4 pt-3">
          {visibles.length === 0 ? (
            <Vacio icono={<Landmark className="size-5" />} titulo={resumen.total === 0 ? "Registre el primer aliado bancario" : "Nada en este filtro"}
              texto={resumen.total === 0 ? "Agregue los bancos y rieles con los que opera la organización." : "Pruebe con «Todos»."} />
          ) : (
            <table className="w-full min-w-[880px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wider text-texto-3">
                <tr><th className="py-2 pr-4">Aliado</th><th className="pr-4">Servicios</th><th className="pr-4">Estado</th>
                  <th className="pr-4">Riesgo</th><th className="pr-4">Diligencia</th><th className="pr-4">Próx. revisión</th><th>Atención</th></tr>
              </thead>
              <tbody className="divide-y divide-borde">
                {visibles.map((a) => (
                  <tr key={a.id} onClick={() => setAbierto(abierto === a.id ? null : a.id)}
                    className={cn("cursor-pointer hover:bg-panel-2", abierto === a.id && "bg-acento-tenue/40")}>
                    <td className="py-3 pr-4"><p className="font-medium">{a.nombre}</p>
                      <p className="text-xs text-texto-3">{[a.tipo_entidad ? c.tipos_entidad[a.tipo_entidad] : "Tipo sin definir", a.pais].filter(Boolean).join(" · ")}</p></td>
                    <td className="pr-4 text-texto-2">{a.servicios.length ? a.servicios.map((s) => c.servicios[s] ?? s).join(", ") : <span className="text-texto-3">—</span>}</td>
                    <td className="pr-4"><Insignia tono={TONO_ESTADO[a.estado]}>{c.estados[a.estado]}</Insignia></td>
                    <td className="pr-4">{a.nivel_riesgo ? <Insignia tono={tonoRiesgo(a.nivel_riesgo)}>{a.nivel_riesgo}</Insignia> : <span className="text-texto-3">Sin calificar</span>}</td>
                    <td className="pr-4"><Insignia tono={TONO_DD[a.dd_estado]}>{c.dd_estados[a.dd_estado]}</Insignia></td>
                    <td className="pr-4 text-texto-2">{a.proxima_revision ? fecha(a.proxima_revision) : "—"}</td>
                    <td>{a.avisos.length ? <span className="inline-flex items-center gap-1 text-xs text-alerta"><AlertTriangle className="size-3.5" aria-hidden />{a.avisos.length}</span> : <span className="text-xs text-ok">Al día</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </Tarjeta>

      {abierto && <DetalleAliado key={abierto} organizacionId={organizacionId} relacionId={abierto} cat={c}
        onCambio={datos.recargar} onCerrar={() => setAbierto(null)} />}
      {abierto && <RequerimientosRelacionados key={`rq-${abierto}`} ruta={`/api/organizaciones/${organizacionId}/aliados/${abierto}/requerimientos`}
        organizacionId={organizacionId} prellenar={`aliado:${abierto}`} titulo="Requerimientos de este aliado"
        vacio="Este aliado no ha hecho requerimientos." />}
    </div>
  );
}

// ================= Alta =================
function NuevoAliado({ organizacionId, cat, onCerrar, onCreado }:
  { organizacionId: number; cat: Catalogos; onCerrar: () => void; onCreado: (id: number) => void }) {
  const [q, setQ] = useState("");
  const busqueda = useDatos<{ aliados: { id: number; nombre: string; razon_social: string | null; pais: string | null }[] }>(
    q.trim().length >= 2 ? `/api/aliados/buscar?q=${encodeURIComponent(q.trim())}` : null);
  const [existente, setExistente] = useState<{ id: number; nombre: string } | null>(null);
  const [f, setF] = useState({ nombre: "", razon_social: "", identificacion: "", pais: "Colombia", tipo_entidad: "", regulado: false,
    regulador: "", licencia: "", estado: "prospecto", nivel_riesgo: "", servicios: [] as string[], monedas: "COP", fecha_inicio: "" });
  const poner = (x: Partial<typeof f>) => setF((v) => ({ ...v, ...x }));
  const { guardando, fallo, ejecutar } = useEnvio(() => undefined);
  const listo = existente || f.nombre.trim().length >= 2;

  async function guardar() {
    const relacion = { estado: f.estado, nivel_riesgo: f.nivel_riesgo || null, servicios: f.servicios, monedas: lista(f.monedas),
      fecha_inicio: f.fecha_inicio || null };
    const entidad = existente ? { aliado_id: existente.id } : {
      nombre: f.nombre, razon_social: f.razon_social || null, identificacion: f.identificacion || null, pais: f.pais || null,
      tipo_entidad: f.tipo_entidad || null, regulado: f.regulado, regulador: f.regulador || null, licencia: f.licencia || null };
    const r = await ejecutar(`/api/organizaciones/${organizacionId}/aliados`, { ...entidad, ...relacion });
    if (r?.id) onCreado(r.id);
  }

  return (
    <Tarjeta>
      <TituloTarjeta titulo="Nuevo aliado bancario" descripcion="Si el aliado ya trabaja con otra organización, búsquelo y reutilice su ficha: solo se crea la relación."
        accion={<Boton variante="fantasma" onClick={onCerrar}><X className="size-4" aria-hidden />Cancelar</Boton>} />
      <div className="space-y-5 px-5 pb-5 pt-3">
        {!existente && (
          <div className="relative max-w-md">
            <Search className="pointer-events-none absolute left-3 top-2.5 size-4 text-texto-3" aria-hidden />
            <Entrada className="pl-9" placeholder="Buscar en aliados ya registrados" value={q} onChange={(e) => setQ(e.target.value)} />
            {(busqueda.datos?.aliados.length ?? 0) > 0 && (
              <div className="mt-1 rounded-lg border border-borde-fuerte bg-panel">
                {busqueda.datos!.aliados.map((a) => (
                  <button key={a.id} type="button" onClick={() => setExistente(a)} className="block w-full px-3 py-2 text-left text-sm hover:bg-panel-2">
                    <span className="font-medium">{a.nombre}</span> <span className="text-texto-3">{[a.razon_social, a.pais].filter(Boolean).join(" · ")}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        {existente ? (
          <Aviso tono="acento">Se usará la ficha existente de <strong>{existente.nombre}</strong>.{" "}
            <button className="underline" onClick={() => setExistente(null)}>Registrar otro</button></Aviso>
        ) : (
          <fieldset className="grid gap-4 md:grid-cols-3">
            <legend className="mb-2 text-[13px] font-medium text-texto-2">La entidad</legend>
            <div><Etiqueta htmlFor="al-nombre">Nombre comercial</Etiqueta><Entrada id="al-nombre" value={f.nombre} placeholder="Cobre" onChange={(e) => poner({ nombre: e.target.value })} /></div>
            <div><Etiqueta htmlFor="al-razon">Razón social</Etiqueta><Entrada id="al-razon" value={f.razon_social} onChange={(e) => poner({ razon_social: e.target.value })} /></div>
            <div><Etiqueta htmlFor="al-id">NIT / identificación</Etiqueta><Entrada id="al-id" value={f.identificacion} onChange={(e) => poner({ identificacion: e.target.value })} /></div>
            <div><Etiqueta htmlFor="al-pais">País</Etiqueta><Entrada id="al-pais" value={f.pais} onChange={(e) => poner({ pais: e.target.value })} /></div>
            <div><Etiqueta htmlFor="al-tipo">Tipo de entidad</Etiqueta>
              <Selector id="al-tipo" value={f.tipo_entidad} onChange={(e) => poner({ tipo_entidad: e.target.value })}>
                <option value="">Seleccione…</option>{Object.entries(cat.tipos_entidad).map(([k, n]) => <option key={k} value={k}>{n}</option>)}
              </Selector></div>
            <div className="flex items-end gap-2 pb-2 text-sm"><label className="flex items-center gap-2">
              <input type="checkbox" checked={f.regulado} onChange={(e) => poner({ regulado: e.target.checked })} />Entidad regulada</label></div>
            {f.regulado && <>
              <div><Etiqueta htmlFor="al-reg">Regulador</Etiqueta><Entrada id="al-reg" value={f.regulador} placeholder="Superintendencia Financiera" onChange={(e) => poner({ regulador: e.target.value })} /></div>
              <div><Etiqueta htmlFor="al-lic">Licencia</Etiqueta><Entrada id="al-lic" value={f.licencia} onChange={(e) => poner({ licencia: e.target.value })} /></div>
            </>}
          </fieldset>
        )}
        <fieldset className="grid gap-4 md:grid-cols-4">
          <legend className="mb-2 text-[13px] font-medium text-texto-2">La relación con la organización</legend>
          <div><Etiqueta htmlFor="al-estado">Estado</Etiqueta>
            <Selector id="al-estado" value={f.estado} onChange={(e) => poner({ estado: e.target.value })}>
              {Object.entries(cat.estados).map(([k, n]) => <option key={k} value={k}>{n}</option>)}</Selector></div>
          <div><Etiqueta htmlFor="al-riesgo">Riesgo</Etiqueta>
            <Selector id="al-riesgo" value={f.nivel_riesgo} onChange={(e) => poner({ nivel_riesgo: e.target.value })}>
              <option value="">Sin calificar</option>{cat.niveles.map((n) => <option key={n}>{n}</option>)}</Selector></div>
          <div><Etiqueta htmlFor="al-inicio">Inicio de la relación</Etiqueta><Entrada id="al-inicio" type="date" value={f.fecha_inicio} onChange={(e) => poner({ fecha_inicio: e.target.value })} /></div>
          <div><Etiqueta htmlFor="al-monedas">Monedas</Etiqueta><Entrada id="al-monedas" value={f.monedas} placeholder="COP, USD" onChange={(e) => poner({ monedas: e.target.value })} /></div>
          <div className="md:col-span-4"><Etiqueta>Servicios que presta</Etiqueta>
            <Chips opciones={cat.servicios} valor={f.servicios} onCambio={(servicios) => poner({ servicios })} /></div>
        </fieldset>
        {fallo && <Aviso tono="critico">{fallo}</Aviso>}
        <Boton variante="primario" cargando={guardando} disabled={!listo} onClick={guardar}><Save className="size-4" aria-hidden />Registrar aliado</Boton>
      </div>
    </Tarjeta>
  );
}

// ================= Detalle =================
function Dato({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return <div><p className="text-xs text-texto-3">{titulo}</p><div className="text-sm">{children || <span className="text-texto-3">—</span>}</div></div>;
}

function DetalleAliado({ organizacionId, relacionId, cat, onCambio, onCerrar }:
  { organizacionId: number; relacionId: number; cat: Catalogos; onCambio: () => Promise<void>; onCerrar: () => void }) {
  const puede = usePuedeGestionar();
  const ruta = `/api/organizaciones/${organizacionId}/aliados/${relacionId}`;
  const d = useDatos<Detalle>(ruta);
  const [modo, setModo] = useState<"ver" | "editar" | "mover">("ver");
  const hecho = async () => { setModo("ver"); await d.recargar(); await onCambio(); };

  if (d.error) return <Aviso tono="critico">{d.error}</Aviso>;
  if (!d.datos) return <Esqueleto className="h-72" />;
  const a = d.datos;

  return (
    <Tarjeta>
      <TituloTarjeta titulo={a.nombre}
        descripcion={a.organizaciones > 1 ? `También es aliado de: ${a.otras_organizaciones.map((o) => `${o.nombre} (${cat.estados[o.estado]})`).join(", ")}. Los datos de la entidad se comparten; la relación es independiente.` : "Relación con esta organización."}
        accion={<span className="flex gap-2">
          {puede && modo === "ver" && <>
            <Boton onClick={() => setModo("mover")}><ArrowRightLeft className="size-4" aria-hidden />Registrar cambio</Boton>
            <Boton onClick={() => setModo("editar")}><Pencil className="size-4" aria-hidden />Editar datos</Boton></>}
          <Boton variante="fantasma" onClick={onCerrar}><X className="size-4" aria-hidden />Cerrar</Boton></span>} />
      <div className="space-y-5 px-5 pb-5 pt-3">
        {a.avisos.length > 0 && (
          <div className="flex flex-wrap gap-1.5">{a.avisos.map((v) => <Insignia key={v.texto} tono={v.tono}>{v.texto}</Insignia>)}</div>
        )}

        {modo === "mover" && <Movimiento ruta={`${ruta}/movimientos`} a={a} cat={cat} onHecho={hecho} onCancelar={() => setModo("ver")} />}
        {modo === "editar" && <Edicion ruta={ruta} a={a} cat={cat} onHecho={hecho} onCancelar={() => setModo("ver")} />}

        {modo === "ver" && (
          <div className="grid gap-6 md:grid-cols-3">
            <section className="space-y-3">
              <h3 className="flex items-center gap-1.5 text-[13px] font-medium text-texto-2"><Building2 className="size-4" aria-hidden />La entidad</h3>
              <Dato titulo="Razón social">{a.razon_social}</Dato>
              <Dato titulo="Identificación · país">{[a.identificacion, a.pais].filter(Boolean).join(" · ")}</Dato>
              <Dato titulo="Tipo">{a.tipo_entidad ? cat.tipos_entidad[a.tipo_entidad] : null}</Dato>
              <Dato titulo="Regulación">{a.regulado ? [a.regulador ?? "Regulada", a.licencia && `licencia ${a.licencia}`].filter(Boolean).join(" · ") : "No regulada"}</Dato>
              {a.sitio_web && <Dato titulo="Sitio web">{a.sitio_web}</Dato>}
              {a.notas_entidad && <Dato titulo="Notas de la entidad"><span className="whitespace-pre-line">{a.notas_entidad}</span></Dato>}
            </section>
            <section className="space-y-3">
              <h3 className="flex items-center gap-1.5 text-[13px] font-medium text-texto-2"><Landmark className="size-4" aria-hidden />La relación</h3>
              <Dato titulo="Estado"><Insignia tono={TONO_ESTADO[a.estado]}>{cat.estados[a.estado]}</Insignia> <span className="text-xs text-texto-3">desde {fecha(a.fecha_estado)}</span></Dato>
              <Dato titulo="Inicio">{a.fecha_inicio ? fecha(a.fecha_inicio) : null}</Dato>
              <Dato titulo="Servicios">{a.servicios.map((s) => cat.servicios[s] ?? s).join(", ")}</Dato>
              <Dato titulo="Monedas">{a.monedas.join(", ")}</Dato>
              <Dato titulo="Riesgo · próxima revisión">{a.nivel_riesgo ? <><Insignia tono={tonoRiesgo(a.nivel_riesgo)}>{a.nivel_riesgo}</Insignia> {a.proxima_revision ? `· ${fecha(a.proxima_revision)}` : "· sin fecha"}</> : "Sin calificar"}</Dato>
              <Dato titulo="Debida diligencia"><Insignia tono={TONO_DD[a.dd_estado]}>{cat.dd_estados[a.dd_estado]}</Insignia>
                {a.dd_nivel && <span className="text-xs text-texto-3"> · {cat.dd_niveles[a.dd_nivel]}</span>}{a.dd_fecha && <span className="text-xs text-texto-3"> · {fecha(a.dd_fecha)}</span>}</Dato>
            </section>
            <section className="space-y-3">
              <h3 className="text-[13px] font-medium text-texto-2">Lo que exige a la organización</h3>
              {a.exigencias.length ? <ul className="list-disc space-y-1 pl-5 text-sm">{a.exigencias.map((x) => <li key={x}>{x}</li>)}</ul>
                : <p className="text-sm text-texto-3">Sin exigencias registradas.</p>}
              <Dato titulo="Contacto de cumplimiento">{[a.contacto_cumplimiento, a.correo_cumplimiento, a.telefono_cumplimiento].filter(Boolean).join(" · ")}</Dato>
              <Dato titulo="Contacto comercial">{[a.contacto_comercial, a.correo_comercial].filter(Boolean).join(" · ")}</Dato>
            </section>
          </div>
        )}
        {modo === "ver" && a.notas && <Dato titulo="Notas de la relación"><span className="whitespace-pre-line text-texto-2">{a.notas}</span></Dato>}
        {modo === "ver" && <DocumentosDelAliado a={a} organizacionId={organizacionId} onCambio={d.recargar} />}

        <div>
          <h3 className="mb-2 text-[13px] font-medium text-texto-2">Bitácora</h3>
          <ul className="divide-y divide-borde text-sm">
            {a.historial.map((h, i) => (
              <li key={i} className="flex flex-wrap gap-x-3 py-2">
                <span className="w-36 shrink-0 text-xs text-texto-3">{fechaHora(h.fecha)}</span>
                <span className="font-medium">{CAMPOS_BITACORA[h.campo] ?? h.campo}</span>
                <span className="text-texto-2">{h.valor_anterior ? `${h.valor_anterior} → ` : ""}{h.valor_nuevo}</span>
                {h.motivo && <span className="basis-full pl-[9.75rem] text-xs text-texto-3">{h.motivo}</span>}
                <span className="ml-auto text-xs text-texto-3">{h.usuario}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Tarjeta>
  );
}

function Movimiento({ ruta, a, cat, onHecho, onCancelar }:
  { ruta: string; a: Detalle; cat: Catalogos; onHecho: () => Promise<void>; onCancelar: () => void }) {
  const [f, setF] = useState({ estado: a.estado, nivel_riesgo: a.nivel_riesgo ?? "", proxima_revision: a.proxima_revision ?? "",
    dd_estado: a.dd_estado, dd_nivel: a.dd_nivel ?? "", dd_fecha: a.dd_fecha ?? "", motivo: "" });
  const poner = (x: Partial<typeof f>) => setF((v) => ({ ...v, ...x }));
  const { guardando, fallo, ejecutar } = useEnvio(onHecho);
  const cuerpo: Record<string, unknown> = { motivo: f.motivo };
  if (f.estado !== a.estado) cuerpo.estado = f.estado;
  if ((f.nivel_riesgo || null) !== a.nivel_riesgo && f.nivel_riesgo) cuerpo.nivel_riesgo = f.nivel_riesgo;
  if ((f.proxima_revision || null) !== a.proxima_revision) cuerpo.proxima_revision = f.proxima_revision || null;
  if (f.dd_estado !== a.dd_estado) cuerpo.dd_estado = f.dd_estado;
  if ((f.dd_nivel || null) !== a.dd_nivel) cuerpo.dd_nivel = f.dd_nivel || null;
  if ((f.dd_fecha || null) !== a.dd_fecha) cuerpo.dd_fecha = f.dd_fecha || null;
  const hayCambios = Object.keys(cuerpo).length > 1;

  return (
    <div className="space-y-4 rounded-xl border border-borde-fuerte p-4">
      <p className="text-sm text-texto-3">Cambie lo que corresponda y explique el motivo: queda en la bitácora y en la auditoría.</p>
      <div className="grid gap-4 md:grid-cols-3">
        <div><Etiqueta htmlFor="mv-estado">Estado de la relación</Etiqueta>
          <Selector id="mv-estado" value={f.estado} onChange={(e) => poner({ estado: e.target.value })}>
            {Object.entries(cat.estados).map(([k, n]) => <option key={k} value={k}>{n}</option>)}</Selector></div>
        <div><Etiqueta htmlFor="mv-riesgo">Riesgo</Etiqueta>
          <Selector id="mv-riesgo" value={f.nivel_riesgo} onChange={(e) => poner({ nivel_riesgo: e.target.value })}>
            {!a.nivel_riesgo && <option value="">Sin calificar</option>}{cat.niveles.map((n) => <option key={n}>{n}</option>)}</Selector></div>
        <div><Etiqueta htmlFor="mv-rev">Próxima revisión</Etiqueta>
          <Entrada id="mv-rev" type="date" value={f.proxima_revision} onChange={(e) => poner({ proxima_revision: e.target.value })} /></div>
        <div><Etiqueta htmlFor="mv-dd">Debida diligencia</Etiqueta>
          <Selector id="mv-dd" value={f.dd_estado} onChange={(e) => poner({ dd_estado: e.target.value })}>
            {Object.entries(cat.dd_estados).map(([k, n]) => <option key={k} value={k}>{n}</option>)}</Selector></div>
        <div><Etiqueta htmlFor="mv-ddn">Nivel de diligencia</Etiqueta>
          <Selector id="mv-ddn" value={f.dd_nivel} onChange={(e) => poner({ dd_nivel: e.target.value })}>
            <option value="">Sin definir</option>{Object.entries(cat.dd_niveles).map(([k, n]) => <option key={k} value={k}>{n}</option>)}</Selector></div>
        <div><Etiqueta htmlFor="mv-ddf">Fecha de la diligencia</Etiqueta>
          <Entrada id="mv-ddf" type="date" value={f.dd_fecha} onChange={(e) => poner({ dd_fecha: e.target.value })} /></div>
      </div>
      <div><Etiqueta htmlFor="mv-motivo">Motivo</Etiqueta>
        <textarea id="mv-motivo" rows={2} className={area} value={f.motivo} placeholder="Ej.: se recibió la diligencia completa y se aprobó la vinculación"
          onChange={(e) => poner({ motivo: e.target.value })} /></div>
      {fallo && <Aviso tono="critico">{fallo}</Aviso>}
      <div className="flex gap-2">
        <Boton variante="primario" cargando={guardando} disabled={!hayCambios || f.motivo.trim().length < 10} onClick={() => ejecutar(ruta, cuerpo)}>
          <Save className="size-4" aria-hidden />Registrar cambio</Boton>
        <Boton variante="fantasma" onClick={onCancelar}>Cancelar</Boton>
      </div>
    </div>
  );
}

function Edicion({ ruta, a, cat, onHecho, onCancelar }:
  { ruta: string; a: Detalle; cat: Catalogos; onHecho: () => Promise<void>; onCancelar: () => void }) {
  const [f, setF] = useState({
    nombre: a.nombre, razon_social: a.razon_social ?? "", identificacion: a.identificacion ?? "", pais: a.pais ?? "",
    tipo_entidad: a.tipo_entidad ?? "", regulado: a.regulado, regulador: a.regulador ?? "", licencia: a.licencia ?? "", sitio_web: a.sitio_web ?? "",
    notas_entidad: a.notas_entidad ?? "", fecha_inicio: a.fecha_inicio ?? "", servicios: a.servicios, monedas: a.monedas.join(", "),
    exigencias: a.exigencias.join("\n"), contacto_cumplimiento: a.contacto_cumplimiento ?? "", correo_cumplimiento: a.correo_cumplimiento ?? "",
    telefono_cumplimiento: a.telefono_cumplimiento ?? "", contacto_comercial: a.contacto_comercial ?? "", correo_comercial: a.correo_comercial ?? "",
    notas: a.notas ?? "", vence_contrato: a.vence_contrato ?? "", vence_poliza: a.vence_poliza ?? "", vence_licencia: a.vence_licencia ?? "",
  });
  const poner = (x: Partial<typeof f>) => setF((v) => ({ ...v, ...x }));
  const { guardando, fallo, ejecutar } = useEnvio(onHecho);
  const vacio = (v: string) => v.trim() || null;

  function guardar() {
    void ejecutar(ruta, {
      nombre: f.nombre, razon_social: vacio(f.razon_social), identificacion: vacio(f.identificacion), pais: vacio(f.pais),
      tipo_entidad: f.tipo_entidad || null, regulado: f.regulado, regulador: vacio(f.regulador), licencia: vacio(f.licencia),
      sitio_web: vacio(f.sitio_web), notas_entidad: vacio(f.notas_entidad), fecha_inicio: f.fecha_inicio || null, servicios: f.servicios,
      monedas: lista(f.monedas), exigencias: f.exigencias.split("\n").map((x) => x.trim()).filter(Boolean),
      contacto_cumplimiento: vacio(f.contacto_cumplimiento), correo_cumplimiento: vacio(f.correo_cumplimiento),
      telefono_cumplimiento: vacio(f.telefono_cumplimiento), contacto_comercial: vacio(f.contacto_comercial),
      correo_comercial: vacio(f.correo_comercial), notas: vacio(f.notas),
      vence_contrato: f.vence_contrato || null, vence_poliza: f.vence_poliza || null, vence_licencia: f.vence_licencia || null,
    }, "PATCH");
  }

  const campo = (k: keyof typeof f, titulo: string, extra?: Record<string, string>) => (
    <div><Etiqueta htmlFor={`ed-${k}`}>{titulo}</Etiqueta>
      <Entrada id={`ed-${k}`} value={f[k] as string} {...extra} onChange={(e) => poner({ [k]: e.target.value } as Partial<typeof f>)} /></div>
  );

  return (
    <div className="space-y-5 rounded-xl border border-borde-fuerte p-4">
      <fieldset className="grid gap-4 md:grid-cols-3">
        <legend className="mb-1 text-[13px] font-medium text-texto-2">La entidad {a.organizaciones > 1 && <span className="font-normal text-alerta">(se comparte con otras organizaciones)</span>}</legend>
        {campo("nombre", "Nombre comercial")}{campo("razon_social", "Razón social")}{campo("identificacion", "NIT / identificación")}
        {campo("pais", "País")}
        <div><Etiqueta htmlFor="ed-tipo">Tipo de entidad</Etiqueta>
          <Selector id="ed-tipo" value={f.tipo_entidad} onChange={(e) => poner({ tipo_entidad: e.target.value })}>
            <option value="">Sin definir</option>{Object.entries(cat.tipos_entidad).map(([k, n]) => <option key={k} value={k}>{n}</option>)}</Selector></div>
        {campo("sitio_web", "Sitio web")}
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.regulado} onChange={(e) => poner({ regulado: e.target.checked })} />Entidad regulada</label>
        {f.regulado && <>{campo("regulador", "Regulador")}{campo("licencia", "Licencia")}</>}
        <div className="md:col-span-3"><Etiqueta htmlFor="ed-ne">Notas de la entidad</Etiqueta>
          <textarea id="ed-ne" rows={2} className={area} value={f.notas_entidad} onChange={(e) => poner({ notas_entidad: e.target.value })} /></div>
      </fieldset>
      <fieldset className="grid gap-4 md:grid-cols-3">
        <legend className="mb-1 text-[13px] font-medium text-texto-2">La relación</legend>
        {campo("fecha_inicio", "Inicio de la relación", { type: "date" })}{campo("monedas", "Monedas", { placeholder: "COP, USD" })}
        {campo("vence_contrato", "Vencimiento del contrato", { type: "date" })}{campo("vence_poliza", "Vencimiento de la póliza", { type: "date" })}
        {campo("vence_licencia", "Vencimiento de la licencia", { type: "date" })}
        <div className="md:col-span-3"><Etiqueta>Servicios</Etiqueta><Chips opciones={cat.servicios} valor={f.servicios} onCambio={(servicios) => poner({ servicios })} /></div>
        <div className="md:col-span-3"><Etiqueta htmlFor="ed-ex">Lo que exige a la organización (una por línea)</Etiqueta>
          <textarea id="ed-ex" rows={3} className={area} value={f.exigencias} placeholder={"Recertificación AML anual\nKYC de cada cliente nuevo antes de operar"}
            onChange={(e) => poner({ exigencias: e.target.value })} /></div>
        {campo("contacto_cumplimiento", "Contacto de cumplimiento")}{campo("correo_cumplimiento", "Correo de cumplimiento", { type: "email" })}
        {campo("telefono_cumplimiento", "Teléfono de cumplimiento")}
        {campo("contacto_comercial", "Contacto comercial")}{campo("correo_comercial", "Correo comercial", { type: "email" })}
        <div className="md:col-span-3"><Etiqueta htmlFor="ed-n">Notas de la relación</Etiqueta>
          <textarea id="ed-n" rows={3} className={area} value={f.notas} onChange={(e) => poner({ notas: e.target.value })} /></div>
      </fieldset>
      {fallo && <Aviso tono="critico">{fallo}</Aviso>}
      <div className="flex gap-2">
        <Boton variante="primario" cargando={guardando} disabled={f.nombre.trim().length < 2} onClick={guardar}><Save className="size-4" aria-hidden />Guardar</Boton>
        <Boton variante="fantasma" onClick={onCancelar}>Cancelar</Boton>
      </div>
    </div>
  );
}

// ================= Documentos del aliado (desde su carpeta en OneDrive) =================
const DOCS_ALIADO: Record<string, string> = { contrato: "Contrato", poliza: "Póliza", licencia: "Licencia o autorización del regulador",
  certificado_existencia: "Certificado de existencia", rut: "RUT", aml: "Cuestionario o certificación AML / SARLAFT", estados_financieros: "Estados financieros" };

function DocumentosDelAliado({ a, organizacionId, onCambio }: { a: Detalle; organizacionId: number; onCambio: () => Promise<void> }) {
  const puede = usePuedeGestionar();
  const [fallo, setFallo] = useState<string | null>(null);
  const docs = a.documentos;
  async function asignar(id: number, codigo: string) {
    setFallo(null);
    try { await enviar(`/api/organizaciones/${organizacionId}/aliados/documentos/${id}/asignar`, { codigo: codigo || null }); await onCambio(); }
    catch (e) { setFallo(e instanceof ErrorApi ? e.message : "No se pudo asignar."); }
  }
  return (
    <section>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h3 className="flex items-center gap-1.5 text-[13px] font-medium text-texto-2"><FileText className="size-4" aria-hidden />Documentos</h3>
        {docs.carpeta ? (a.carpeta_web_url && <a href={a.carpeta_web_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-acento hover:underline">
          Carpeta «{a.carpeta_nombre}»<ExternalLink className="size-3" aria-hidden /></a>)
          : <span className="text-xs text-texto-3">Sin carpeta: créela en «Compliance/Aliados bancarios/{a.nombre}» y revise la carpeta Compliance (Ficha de la organización).</span>}
        {docs.carpeta && <Insignia tono={docs.completo ? "ok" : "alerta"}>{docs.completo ? "Completos" : "Incompletos"}</Insignia>}
      </div>
      <ul className="divide-y divide-borde text-sm">
        {docs.filas.map((f) => (
          <li key={f.codigo} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
            <span className={cn("inline-flex size-5 items-center justify-center rounded-full", f.cargado ? "bg-ok/15 text-ok" : "bg-panel-2 text-texto-3")}>
              {f.cargado ? <Check className="size-3.5" aria-hidden /> : <span className="text-xs">·</span>}</span>
            <span className="min-w-[220px] flex-1">{f.nombre}{!f.exigido && <span className="text-xs text-texto-3"> (opcional)</span>}</span>
            {f.archivos.map((x) => <a key={x.id} href={x.web_url ?? "#"} target="_blank" rel="noreferrer" className="max-w-[260px] truncate text-xs text-acento hover:underline">{x.nombre_archivo}</a>)}
            {f.vence && <Insignia tono={f.estado_vence === "vencido" ? "critico" : f.estado_vence === "por_vencer" ? "alerta" : "ok"}>
              {f.estado_vence === "vencido" ? "Vencido" : "Vence"} {fecha(f.vence)}</Insignia>}
          </li>
        ))}
      </ul>
      {docs.sin_reconocer.length > 0 && (
        <div className="mt-3">
          <p className="mb-1 text-xs text-texto-3">Archivos sin reconocer: asigne el tipo si corresponde (queda así aunque se vuelva a revisar).</p>
          <ul className="space-y-1.5 text-sm">{docs.sin_reconocer.map((x) => (
            <li key={x.id} className="flex flex-wrap items-center gap-2">
              <a href={x.web_url ?? "#"} target="_blank" rel="noreferrer" className="text-acento hover:underline">{x.nombre_archivo}</a>
              {puede && <Selector aria-label={`Tipo de ${x.nombre_archivo}`} className="w-auto py-1 text-xs" value="" onChange={(e) => asignar(x.id, e.target.value)}>
                <option value="">Asignar como…</option>{Object.entries(DOCS_ALIADO).map(([k, n]) => <option key={k} value={k}>{n}</option>)}</Selector>}
            </li>))}</ul>
        </div>
      )}
      {fallo && <Aviso tono="critico">{fallo}</Aviso>}
    </section>
  );
}
