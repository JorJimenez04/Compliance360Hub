"use client";

import { useState } from "react";
import { AlertTriangle, FileText, Pencil, Plus, Save, ShieldAlert, UserX, X } from "lucide-react";
import { Aviso, Boton, Entrada, Esqueleto, Etiqueta, Insignia, Selector, Tarjeta, TituloTarjeta, Vacio, tonoRiesgo } from "@/components/ui/basicos";
import { enviar, ErrorApi } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";
import { usePuedeGestionar } from "@/lib/sesion";
import { entero, fecha, fechaHora, moneda } from "@/lib/formato";
import { cn } from "@/lib/cn";

const area = "w-full rounded-lg border border-borde-fuerte bg-fondo px-3 py-2 text-sm text-texto focus:border-acento focus:outline-none";

function useEnvio(onHecho: () => void | Promise<void>) {
  const [guardando, setGuardando] = useState(false);
  const [fallo, setFallo] = useState<string | null>(null);
  async function ejecutar(ruta: string, cuerpo: unknown, metodo = "POST") {
    setGuardando(true); setFallo(null);
    try { await enviar(ruta, cuerpo, metodo); await onHecho(); return true; }
    catch (e) { setFallo(e instanceof ErrorApi ? e.message : "No se pudo guardar."); return false; }
    finally { setGuardando(false); }
  }
  return { guardando, fallo, ejecutar, setFallo };
}

// ================= Personas vinculadas =================
interface Persona {
  id: number; nombre_completo: string; tipo_documento: string | null; numero_documento: string | null; nacionalidad: string;
  rol: string; pct_participacion: number | null; es_pep: boolean; en_listas_restriccion: boolean;
  fecha_verificacion: string | null; activo: boolean; notas: string | null; creado_por: string;
}
interface RespPersonas {
  personas: Persona[]; roles: string[]; tipos_documento: string[];
  resumen: { total: number; pep: number; en_listas: number; participacion_accionistas: number; tiene_representante: boolean; tiene_beneficiario_final: boolean };
}
const PERSONA_VACIA = { nombre_completo: "", tipo_documento: "CC", numero_documento: "", nacionalidad: "Colombia", rol: "Accionista",
  pct_participacion: "", es_pep: false, en_listas_restriccion: false, fecha_verificacion: "", notas: "" };
type FormPersona = typeof PERSONA_VACIA;

function FormularioPersona({ clienteId, inicial, id, datos, onCerrar, onHecho }: {
  clienteId: number; inicial: FormPersona; id: number | null; datos: RespPersonas; onCerrar: () => void; onHecho: () => Promise<void>;
}) {
  const [f, setF] = useState(inicial);
  const { guardando, fallo, ejecutar } = useEnvio(async () => { await onHecho(); onCerrar(); });
  const poner = (c: Partial<FormPersona>) => setF({ ...f, ...c });
  const cuerpo = { ...f, pct_participacion: f.pct_participacion === "" ? null : Number(f.pct_participacion),
    fecha_verificacion: f.fecha_verificacion || null };
  return (
    <Tarjeta className="border-acento/40">
      <TituloTarjeta titulo={id ? "Editar persona vinculada" : "Agregar persona vinculada"}
        accion={<div className="flex gap-2">
          <Boton type="button" onClick={onCerrar}><X className="size-4" aria-hidden />Cancelar</Boton>
          <Boton variante="primario" cargando={guardando} disabled={f.nombre_completo.trim().length < 3}
            onClick={() => ejecutar(id ? `/api/clientes/${clienteId}/personas/${id}` : `/api/clientes/${clienteId}/personas`, cuerpo, id ? "PATCH" : "POST")}>
            <Save className="size-4" aria-hidden />Guardar</Boton></div>} />
      <div className="space-y-4 px-5 pb-5 pt-3">
        {fallo && <Aviso tono="critico">{fallo}</Aviso>}
        <div className="grid gap-4 md:grid-cols-4">
          <div className="md:col-span-2"><Etiqueta htmlFor="p-nombre">Nombre completo</Etiqueta>
            <Entrada id="p-nombre" value={f.nombre_completo} onChange={(e) => poner({ nombre_completo: e.target.value })} /></div>
          <div><Etiqueta htmlFor="p-rol">Rol</Etiqueta>
            <Selector id="p-rol" value={f.rol} onChange={(e) => poner({ rol: e.target.value })}>
              {datos.roles.map((r) => <option key={r}>{r}</option>)}</Selector></div>
          <div><Etiqueta htmlFor="p-pct">% participación</Etiqueta>
            <Entrada id="p-pct" type="number" min={0} max={100} step="0.01" value={f.pct_participacion}
              onChange={(e) => poner({ pct_participacion: e.target.value })} /></div>
          <div><Etiqueta htmlFor="p-td">Tipo de documento</Etiqueta>
            <Selector id="p-td" value={f.tipo_documento} onChange={(e) => poner({ tipo_documento: e.target.value })}>
              {datos.tipos_documento.map((t) => <option key={t}>{t}</option>)}</Selector></div>
          <div><Etiqueta htmlFor="p-doc">Número de documento</Etiqueta>
            <Entrada id="p-doc" value={f.numero_documento} onChange={(e) => poner({ numero_documento: e.target.value })} /></div>
          <div><Etiqueta htmlFor="p-nac">Nacionalidad</Etiqueta>
            <Entrada id="p-nac" value={f.nacionalidad} onChange={(e) => poner({ nacionalidad: e.target.value })} /></div>
          <div><Etiqueta htmlFor="p-ver">Verificada en listas el</Etiqueta>
            <Entrada id="p-ver" type="date" value={f.fecha_verificacion} onChange={(e) => poner({ fecha_verificacion: e.target.value })} /></div>
        </div>
        <div className="flex flex-wrap gap-6 text-sm">
          <label className="flex items-center gap-2"><input type="checkbox" className="size-4 accent-[var(--color-acento)]" checked={f.es_pep}
            onChange={(e) => poner({ es_pep: e.target.checked })} />Persona expuesta políticamente (PEP)</label>
          <label className="flex items-center gap-2"><input type="checkbox" className="size-4 accent-[var(--color-acento)]" checked={f.en_listas_restriccion}
            onChange={(e) => poner({ en_listas_restriccion: e.target.checked })} />Aparece en listas restrictivas</label>
        </div>
        <div><Etiqueta htmlFor="p-notas">Notas</Etiqueta>
          <textarea id="p-notas" rows={2} className={area} value={f.notas} onChange={(e) => poner({ notas: e.target.value })} /></div>
      </div>
    </Tarjeta>
  );
}

export function PersonasCliente({ clienteId }: { clienteId: number }) {
  const [todas, setTodas] = useState(false);
  const { datos, error, recargar } = useDatos<RespPersonas>(`/api/clientes/${clienteId}/personas?todas=${todas}`);
  const puede = usePuedeGestionar();
  const [editando, setEditando] = useState<{ id: number | null; inicial: FormPersona } | null>(null);
  const retiro = useEnvio(recargar);
  if (error) return <Aviso tono="critico" icono={<AlertTriangle className="size-4" />}>{error}</Aviso>;
  if (!datos) return <Esqueleto className="h-64" />;
  const r = datos.resumen;
  const avisos = [
    !r.tiene_representante && "No hay representante legal registrado.",
    !r.tiene_beneficiario_final && "No hay beneficiario final (UBO) registrado.",
    r.participacion_accionistas > 0 && r.participacion_accionistas < 100 && `Los accionistas registrados suman ${r.participacion_accionistas} %.`,
  ].filter(Boolean) as string[];

  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[["Personas vinculadas", entero(r.total), ""], ["PEP", entero(r.pep), r.pep ? "text-serio" : ""],
          ["En listas restrictivas", entero(r.en_listas), r.en_listas ? "text-critico" : ""],
          ["Participación accionistas", `${r.participacion_accionistas} %`, ""]].map(([t, v, c]) => (
          <Tarjeta key={t} className="px-5 py-4"><p className="text-[13px] text-texto-3">{t}</p>
            <p className={cn("cifra mt-1 text-2xl font-semibold", c)}>{v}</p></Tarjeta>
        ))}
      </div>
      {avisos.length > 0 && <Aviso tono="alerta" icono={<ShieldAlert className="size-4" />}>{avisos.join(" ")}</Aviso>}
      {retiro.fallo && <Aviso tono="critico">{retiro.fallo}</Aviso>}
      {editando && <FormularioPersona clienteId={clienteId} id={editando.id} inicial={editando.inicial} datos={datos}
        onCerrar={() => setEditando(null)} onHecho={recargar} />}

      <Tarjeta>
        <TituloTarjeta titulo="Representantes, accionistas y beneficiarios finales"
          descripcion="Personas naturales o jurídicas vinculadas al cliente. Las marcadas como PEP o en listas se reflejan en su riesgo."
          accion={<div className="flex items-center gap-2">
            <button type="button" onClick={() => setTodas(!todas)}
              className={cn("whitespace-nowrap rounded-md border px-2.5 py-1 text-xs", todas ? "border-acento bg-acento-tenue text-texto" : "border-borde-fuerte text-texto-3")}>
              Ver retiradas</button>
            {puede && !editando && <Boton variante="primario" onClick={() => setEditando({ id: null, inicial: PERSONA_VACIA })}>
              <Plus className="size-4" aria-hidden />Agregar</Boton>}</div>} />
        {!datos.personas.length ? <Vacio titulo="Sin personas vinculadas" texto="Registre al representante legal, los accionistas y el beneficiario final." /> : (
          <div className="overflow-x-auto px-2 pb-3 pt-2">
            <table className="w-full min-w-[900px] text-[13px]">
              <thead><tr className="text-left text-texto-3">
                <th className="px-3 py-2 font-medium">Persona</th><th className="px-3 py-2 font-medium">Rol</th>
                <th className="px-3 py-2 text-right font-medium">Participación</th><th className="px-3 py-2 font-medium">Nacionalidad</th>
                <th className="px-3 py-2 font-medium">Alertas</th><th className="px-3 py-2 font-medium">Verificación</th><th className="px-3 py-2" /></tr></thead>
              <tbody>
                {datos.personas.map((p) => (
                  <tr key={p.id} className={cn("border-t border-borde/70", !p.activo && "opacity-50")}>
                    <td className="px-3 py-2.5"><p className="text-texto">{p.nombre_completo}</p>
                      <p className="text-xs text-texto-3">{[p.tipo_documento, p.numero_documento].filter(Boolean).join(" ") || "Sin documento"}</p></td>
                    <td className="px-3 py-2.5 text-texto-2">{p.rol}{!p.activo && " · retirada"}</td>
                    <td className="cifra px-3 py-2.5 text-right">{p.pct_participacion != null ? `${p.pct_participacion} %` : "—"}</td>
                    <td className="px-3 py-2.5 text-texto-2">{p.nacionalidad}</td>
                    <td className="px-3 py-2.5"><div className="flex flex-wrap gap-1">
                      {p.es_pep && <Insignia tono="serio">PEP</Insignia>}
                      {p.en_listas_restriccion && <Insignia tono="critico">En listas</Insignia>}
                      {!p.es_pep && !p.en_listas_restriccion && <span className="text-texto-3">—</span>}</div></td>
                    <td className="px-3 py-2.5 text-texto-2">{p.fecha_verificacion ? fecha(p.fecha_verificacion) : <span className="text-alerta">Sin verificar</span>}</td>
                    <td className="px-3 py-2.5 text-right">{puede && (
                      <div className="flex justify-end gap-2">
                        <button type="button" title="Editar" className="text-texto-3 hover:text-texto" onClick={() => setEditando({ id: p.id, inicial: {
                          nombre_completo: p.nombre_completo, tipo_documento: p.tipo_documento ?? "CC", numero_documento: p.numero_documento ?? "",
                          nacionalidad: p.nacionalidad, rol: p.rol, pct_participacion: p.pct_participacion?.toString() ?? "", es_pep: p.es_pep,
                          en_listas_restriccion: p.en_listas_restriccion, fecha_verificacion: p.fecha_verificacion ?? "", notas: p.notas ?? "" } })}>
                          <Pencil className="size-4" /></button>
                        <button type="button" title={p.activo ? "Retirar" : "Reactivar"} className="text-texto-3 hover:text-critico"
                          onClick={() => (p.activo ? window.confirm(`¿Retirar a ${p.nombre_completo} de las personas vinculadas?`) : true)
                            && retiro.ejecutar(`/api/clientes/${clienteId}/personas/${p.id}`, { activo: !p.activo }, "PATCH")}>
                          <UserX className="size-4" /></button>
                      </div>)}</td>
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

// ================= Contratos =================
interface Contrato {
  id: number; empresa_grupo: string; estado: string; fecha_inicio: string | null; fecha_vencimiento: string | null;
  contrato_firmado: boolean; fecha_firma: string | null; numero_contrato: string | null; contacto_operativo: string | null;
  email_operativo: string | null; telefono_operativo: string | null; contacto_compliance: string | null; email_compliance: string | null;
  sla_contratado: string | null; volumen_mensual_cop: number | null; num_transacciones_mes: number | null; notas: string | null;
  dias_para_vencer: number | null; servicios: { servicio: string; estado: string; fecha_activacion: string | null }[];
}
interface RespContratos { contratos: Contrato[]; empresas: string[]; estados: string[]; servicios: string[] }
const CAMPOS_TEXTO: [keyof Contrato, string][] = [["numero_contrato", "Número de contrato"], ["sla_contratado", "SLA contratado"],
  ["contacto_operativo", "Contacto operativo"], ["email_operativo", "Correo operativo"], ["telefono_operativo", "Teléfono operativo"],
  ["contacto_compliance", "Contacto de cumplimiento"], ["email_compliance", "Correo de cumplimiento"]];

function FormularioContrato({ clienteId, empresa, c, datos, onCerrar, onHecho }: {
  clienteId: number; empresa: string; c: Contrato | undefined; datos: RespContratos; onCerrar: () => void; onHecho: () => Promise<void>;
}) {
  const [f, setF] = useState<Record<string, string | boolean | string[]>>(() => ({
    estado: c?.estado ?? "Prospecto", fecha_inicio: c?.fecha_inicio ?? "", fecha_vencimiento: c?.fecha_vencimiento ?? "",
    contrato_firmado: c?.contrato_firmado ?? false, fecha_firma: c?.fecha_firma ?? "",
    volumen_mensual_cop: c?.volumen_mensual_cop?.toString() ?? "", num_transacciones_mes: c?.num_transacciones_mes?.toString() ?? "",
    notas: c?.notas ?? "", servicios: c?.servicios.filter((s) => s.estado === "Activo").map((s) => s.servicio) ?? [],
    ...Object.fromEntries(CAMPOS_TEXTO.map(([k]) => [k, (c?.[k] as string | null) ?? ""])),
  }));
  const { guardando, fallo, ejecutar } = useEnvio(async () => { await onHecho(); onCerrar(); });
  const nulo = (v: unknown) => (v === "" ? null : v);
  const cuerpo = { ...Object.fromEntries(Object.entries(f).map(([k, v]) => [k, nulo(v)])), empresa_grupo: empresa,
    volumen_mensual_cop: f.volumen_mensual_cop === "" ? null : Number(f.volumen_mensual_cop),
    num_transacciones_mes: f.num_transacciones_mes === "" ? null : Number(f.num_transacciones_mes), servicios: f.servicios };
  const servicios = f.servicios as string[];
  return (
    <div className="space-y-4 border-t border-borde px-5 pb-5 pt-4">
      {fallo && <Aviso tono="critico">{fallo}</Aviso>}
      <div className="grid gap-4 md:grid-cols-4">
        <div><Etiqueta htmlFor={`k-est-${empresa}`}>Estado</Etiqueta>
          <Selector id={`k-est-${empresa}`} value={f.estado as string} onChange={(e) => setF({ ...f, estado: e.target.value })}>
            {datos.estados.map((x) => <option key={x}>{x}</option>)}</Selector></div>
        {(["fecha_inicio", "fecha_vencimiento", "fecha_firma"] as const).map((k) => (
          <div key={k}><Etiqueta htmlFor={`k-${k}-${empresa}`}>{k === "fecha_inicio" ? "Inicio" : k === "fecha_vencimiento" ? "Vencimiento" : "Fecha de firma"}</Etiqueta>
            <Entrada id={`k-${k}-${empresa}`} type="date" value={f[k] as string} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></div>
        ))}
        {CAMPOS_TEXTO.map(([k, n]) => (
          <div key={k}><Etiqueta htmlFor={`k-${k}-${empresa}`}>{n}</Etiqueta>
            <Entrada id={`k-${k}-${empresa}`} value={f[k] as string} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></div>
        ))}
        <div><Etiqueta htmlFor={`k-vol-${empresa}`}>Volumen mensual (COP)</Etiqueta>
          <Entrada id={`k-vol-${empresa}`} type="number" min={0} value={f.volumen_mensual_cop as string} onChange={(e) => setF({ ...f, volumen_mensual_cop: e.target.value })} /></div>
        <div><Etiqueta htmlFor={`k-ops-${empresa}`}>Transacciones al mes</Etiqueta>
          <Entrada id={`k-ops-${empresa}`} type="number" min={0} value={f.num_transacciones_mes as string} onChange={(e) => setF({ ...f, num_transacciones_mes: e.target.value })} /></div>
      </div>
      <div className="flex flex-wrap items-center gap-5 text-sm">
        <label className="flex items-center gap-2"><input type="checkbox" className="size-4 accent-[var(--color-acento)]" checked={f.contrato_firmado as boolean}
          onChange={(e) => setF({ ...f, contrato_firmado: e.target.checked })} />Contrato firmado</label>
        <span className="text-texto-3">Servicios:</span>
        {datos.servicios.map((s) => (
          <label key={s} className="flex items-center gap-2"><input type="checkbox" className="size-4 accent-[var(--color-acento)]" checked={servicios.includes(s)}
            onChange={(e) => setF({ ...f, servicios: e.target.checked ? [...servicios, s] : servicios.filter((x) => x !== s) })} />{s}</label>
        ))}
      </div>
      <div><Etiqueta htmlFor={`k-notas-${empresa}`}>Notas</Etiqueta>
        <textarea id={`k-notas-${empresa}`} rows={2} className={area} value={f.notas as string} onChange={(e) => setF({ ...f, notas: e.target.value })} /></div>
      <div className="flex gap-2">
        <Boton variante="primario" cargando={guardando} onClick={() => ejecutar(`/api/clientes/${clienteId}/contratos`, cuerpo)}><Save className="size-4" aria-hidden />Guardar contrato</Boton>
        <Boton onClick={onCerrar}>Cancelar</Boton>
      </div>
    </div>
  );
}

export function ContratosCliente({ clienteId }: { clienteId: number }) {
  const { datos, error, recargar } = useDatos<RespContratos>(`/api/clientes/${clienteId}/contratos`);
  const puede = usePuedeGestionar();
  const [editando, setEditando] = useState<string | null>(null);
  if (error) return <Aviso tono="critico" icono={<AlertTriangle className="size-4" />}>{error}</Aviso>;
  if (!datos) return <Esqueleto className="h-64" />;
  return (
    <div className="space-y-4">
      <p className="text-sm text-texto-3">Un contrato por cada empresa del grupo que le presta servicios al cliente.</p>
      {datos.empresas.map((empresa) => {
        const c = datos.contratos.find((x) => x.empresa_grupo === empresa);
        const vence = c?.dias_para_vencer;
        return (
          <Tarjeta key={empresa}>
            <TituloTarjeta titulo={empresa}
              descripcion={c ? `Contrato ${c.numero_contrato ?? "sin número"} · ${c.contrato_firmado ? `firmado${c.fecha_firma ? ` el ${fecha(c.fecha_firma)}` : ""}` : "sin firmar"}` : "Sin contrato registrado"}
              accion={<div className="flex items-center gap-2">
                {c && <Insignia tono={c.estado === "Activo" ? "ok" : c.estado === "Terminado" ? "neutro" : "alerta"}>{c.estado}</Insignia>}
                {vence != null && c?.estado === "Activo" && vence < 0 && <Insignia tono="critico">Vencido</Insignia>}
                {vence != null && c?.estado === "Activo" && vence >= 0 && vence <= 30 && <Insignia tono="alerta">Vence en {vence} días</Insignia>}
                {puede && editando !== empresa && <Boton onClick={() => setEditando(empresa)}>{c ? <><Pencil className="size-4" aria-hidden />Editar</> : <><Plus className="size-4" aria-hidden />Registrar</>}</Boton>}
              </div>} />
            {c && editando !== empresa && (
              <div className="grid gap-x-6 gap-y-2 px-5 pb-5 pt-2 text-[13px] md:grid-cols-3">
                <p><span className="text-texto-3">Vigencia: </span>{fecha(c.fecha_inicio)} – {fecha(c.fecha_vencimiento)}</p>
                <p><span className="text-texto-3">Volumen pactado: </span>{moneda(c.volumen_mensual_cop)} · {entero(c.num_transacciones_mes)} tx/mes</p>
                <p><span className="text-texto-3">SLA: </span>{c.sla_contratado ?? "—"}</p>
                <p><span className="text-texto-3">Operativo: </span>{[c.contacto_operativo, c.email_operativo, c.telefono_operativo].filter(Boolean).join(" · ") || "—"}</p>
                <p className="md:col-span-2"><span className="text-texto-3">Cumplimiento: </span>{[c.contacto_compliance, c.email_compliance].filter(Boolean).join(" · ") || "—"}</p>
                <div className="flex flex-wrap items-center gap-1 md:col-span-3"><span className="text-texto-3">Servicios: </span>
                  {c.servicios.length ? c.servicios.map((s) => <Insignia key={s.servicio} tono={s.estado === "Activo" ? "acento" : "neutro"}>{s.servicio}{s.estado !== "Activo" && ` · ${s.estado.toLowerCase()}`}</Insignia>) : "—"}</div>
                {c.notas && <p className="text-texto-2 md:col-span-3">{c.notas}</p>}
              </div>
            )}
            {editando === empresa && <FormularioContrato clienteId={clienteId} empresa={empresa} c={c} datos={datos}
              onCerrar={() => setEditando(null)} onHecho={recargar} />}
          </Tarjeta>
        );
      })}
    </div>
  );
}

// ================= Calificación de riesgo =================
interface Calificacion {
  id: number; puntaje_anterior: number | null; puntaje_nuevo: number; nivel_anterior: string | null; nivel_nuevo: string;
  motivo: string | null; observaciones: string | null; registrado_por: string; registrado_en: string;
}
interface RespRiesgo {
  nivel_actual: string; puntaje_actual: number | null; fecha_ultima_calificacion: string | null; proxima_revision: string | null;
  niveles: string[]; historial: Calificacion[];
}

export function RiesgoCliente({ clienteId, sugerido, onCambio }: { clienteId: number; sugerido: string | null; onCambio: () => void }) {
  const { datos, error, recargar } = useDatos<RespRiesgo>(`/api/clientes/${clienteId}/riesgo`);
  const puede = usePuedeGestionar();
  const [abierto, setAbierto] = useState(false);
  const [f, setF] = useState({ nivel: "", puntaje: "", motivo: "", observaciones: "", proxima_revision: "" });
  const { guardando, fallo, ejecutar } = useEnvio(async () => { await recargar(); onCambio(); setAbierto(false);
    setF({ nivel: "", puntaje: "", motivo: "", observaciones: "", proxima_revision: "" }); });
  if (error) return <Aviso tono="critico" icono={<AlertTriangle className="size-4" />}>{error}</Aviso>;
  if (!datos) return <Esqueleto className="h-64" />;
  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Tarjeta className="px-5 py-4"><p className="text-[13px] text-texto-3">Nivel actual</p>
          <div className="mt-2"><Insignia tono={tonoRiesgo(datos.nivel_actual)}>{datos.nivel_actual}</Insignia></div>
          {sugerido && <p className="mt-2 text-xs text-texto-3">Sugerido por sus modelos: {sugerido}</p>}</Tarjeta>
        <Tarjeta className="px-5 py-4"><p className="text-[13px] text-texto-3">Puntaje</p>
          <p className="cifra mt-1 text-2xl font-semibold">{datos.puntaje_actual ?? "—"}<span className="text-sm text-texto-3"> / 100</span></p></Tarjeta>
        <Tarjeta className="px-5 py-4"><p className="text-[13px] text-texto-3">Última calificación</p>
          <p className="mt-1 text-lg font-medium">{fecha(datos.fecha_ultima_calificacion)}</p></Tarjeta>
        <Tarjeta className="px-5 py-4"><p className="text-[13px] text-texto-3">Próxima revisión</p>
          <p className={cn("mt-1 text-lg font-medium", datos.proxima_revision && datos.proxima_revision < new Date().toISOString().slice(0, 10) && "text-critico")}>
            {fecha(datos.proxima_revision)}</p></Tarjeta>
      </div>

      {puede && (abierto ? (
        <Tarjeta className="border-acento/40">
          <TituloTarjeta titulo="Nueva calificación" descripcion="Queda en el historial con su motivo y responsable." />
          <div className="space-y-4 px-5 pb-5 pt-3">
            {fallo && <Aviso tono="critico">{fallo}</Aviso>}
            <div className="grid gap-4 md:grid-cols-3">
              <div><Etiqueta htmlFor="r-nivel">Nivel</Etiqueta>
                <Selector id="r-nivel" value={f.nivel} onChange={(e) => setF({ ...f, nivel: e.target.value })}>
                  <option value="">Elija…</option>{datos.niveles.map((n) => <option key={n}>{n}</option>)}</Selector></div>
              <div><Etiqueta htmlFor="r-puntaje">Puntaje (0–100, opcional)</Etiqueta>
                <Entrada id="r-puntaje" type="number" min={0} max={100} value={f.puntaje} onChange={(e) => setF({ ...f, puntaje: e.target.value })} /></div>
              <div><Etiqueta htmlFor="r-prox">Próxima revisión</Etiqueta>
                <Entrada id="r-prox" type="date" value={f.proxima_revision} onChange={(e) => setF({ ...f, proxima_revision: e.target.value })} /></div>
            </div>
            <div><Etiqueta htmlFor="r-motivo">Motivo (obligatorio)</Etiqueta>
              <textarea id="r-motivo" rows={2} className={area} placeholder="Factores que sustentan la calificación: actividad, jurisdicción, canal, comportamiento, PEP…"
                value={f.motivo} onChange={(e) => setF({ ...f, motivo: e.target.value })} /></div>
            <div><Etiqueta htmlFor="r-obs">Observaciones</Etiqueta>
              <textarea id="r-obs" rows={2} className={area} value={f.observaciones} onChange={(e) => setF({ ...f, observaciones: e.target.value })} /></div>
            <div className="flex gap-2">
              <Boton variante="primario" cargando={guardando} disabled={!f.nivel || f.motivo.trim().length < 10}
                onClick={() => ejecutar(`/api/clientes/${clienteId}/riesgo`, { nivel: f.nivel, puntaje: f.puntaje === "" ? null : Number(f.puntaje),
                  motivo: f.motivo, observaciones: f.observaciones || null, proxima_revision: f.proxima_revision || null })}>
                <Save className="size-4" aria-hidden />Registrar calificación</Boton>
              <Boton onClick={() => setAbierto(false)}>Cancelar</Boton>
            </div>
          </div>
        </Tarjeta>
      ) : <Boton variante="primario" onClick={() => setAbierto(true)}><Plus className="size-4" aria-hidden />Nueva calificación</Boton>)}

      <Tarjeta>
        <TituloTarjeta titulo="Historial de calificaciones" descripcion="Incluye las registradas en la app anterior y los cambios hechos desde la ficha." />
        {!datos.historial.length ? <Vacio titulo="Sin calificaciones registradas" /> : (
          <ol className="space-y-3 px-5 pb-5 pt-2">
            {datos.historial.map((h) => (
              <li key={h.id} className="rounded-r-lg border-l-2 border-borde-fuerte bg-fondo/40 px-4 py-2.5 text-[13px]">
                <div className="flex flex-wrap items-center gap-2">
                  {h.nivel_anterior && <><Insignia tono={tonoRiesgo(h.nivel_anterior)}>{h.nivel_anterior}</Insignia><span className="text-texto-3">→</span></>}
                  <Insignia tono={tonoRiesgo(h.nivel_nuevo)}>{h.nivel_nuevo}</Insignia>
                  <span className="cifra text-texto-3">puntaje {h.puntaje_anterior != null ? `${h.puntaje_anterior} → ` : ""}{h.puntaje_nuevo}</span>
                  <span className="ml-auto text-xs text-texto-3">{fechaHora(h.registrado_en)} · {h.registrado_por}</span>
                </div>
                {h.motivo && <p className="mt-1 text-texto">{h.motivo}</p>}
                {h.observaciones && <p className="text-texto-3">{h.observaciones}</p>}
              </li>
            ))}
          </ol>
        )}
      </Tarjeta>
    </div>
  );
}

// ================= Documentos de la app anterior =================
interface DocAnterior { id: number; titulo: string; carpeta: string; estado: string; formato: string; url: string | null; version: string; fecha_emision: string | null }

export function DocumentosAnteriores({ clienteId }: { clienteId: number }) {
  const { datos } = useDatos<{ documentos: DocAnterior[] }>(`/api/clientes/${clienteId}/documentos-anteriores`);
  if (!datos?.documentos.length) return null;
  return (
    <Tarjeta>
      <TituloTarjeta titulo={`Documentos registrados en la app anterior (${datos.documentos.length})`}
        descripcion="Solo consulta. Lo nuevo se gestiona en la carpeta del cliente en OneDrive." />
      <ul className="divide-y divide-borde/70 px-5 pb-4 pt-1 text-[13px]">
        {datos.documentos.map((d) => (
          <li key={d.id} className="flex flex-wrap items-center gap-3 py-2">
            <FileText className="size-4 text-texto-3" aria-hidden />
            {d.url ? <a href={d.url} target="_blank" rel="noopener noreferrer" className="text-acento hover:underline">{d.titulo}</a> : <span>{d.titulo}</span>}
            <span className="text-xs text-texto-3">{d.carpeta} · v{d.version}{d.fecha_emision && ` · ${fecha(d.fecha_emision)}`}</span>
            <Insignia tono={d.estado === "Vigente" ? "ok" : d.estado === "Vencido" ? "critico" : "neutro"}>{d.estado}</Insignia>
          </li>
        ))}
      </ul>
    </Tarjeta>
  );
}
