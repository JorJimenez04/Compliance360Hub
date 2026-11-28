"use client";

import { useState } from "react";
import { FileText, Lock, Trash2, Upload, X } from "lucide-react";
import { Aviso, Boton, Entrada, Esqueleto, Etiqueta, Insignia, Selector, Tarjeta, TituloTarjeta, Vacio } from "@/components/ui/basicos";
import { api, enviar, ErrorApi } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";
import { usePuedeGestionar, useSesion } from "@/lib/sesion";
import { fecha, fechaHora } from "@/lib/formato";

interface Reporte {
  id: number; tipo: "ROS" | "AROS" | "otro"; periodo_desde: string | null; periodo_hasta: string | null; fecha_presentacion: string;
  radicado: string | null; cliente_id: number | null; subcliente: string | null; descripcion: string | null; archivo_nombre: string;
  archivo_bytes: number; creado_por: string; creado_en: string;
}
const area = "w-full rounded-lg border border-borde-fuerte bg-fondo px-3 py-2 text-sm text-texto focus:border-acento focus:outline-none";

/** Reportes a la UIAF de la organización, cargados en PDF. Reserva legal: solo equipo interno. */
export default function ReportesUiaf({ organizacionId }: { organizacionId: number }) {
  const puede = usePuedeGestionar();
  const { rol } = useSesion();
  const ruta = `/api/organizaciones/${organizacionId}/reportes-uiaf`;
  const datos = useDatos<{ reportes: Reporte[]; tipos: Record<string, string> }>(ruta);
  const clientes = useDatos<{ clientes: { id: number; razon_social: string }[] }>(`/api/organizaciones/${organizacionId}/requerimientos`);
  const [nuevo, setNuevo] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);

  async function eliminar(r: Reporte) {
    const motivo = window.prompt(`¿Eliminar el ${r.tipo} «${r.archivo_nombre}»? Escriba el motivo (queda en la auditoría):`);
    if (!motivo) return;
    try { await enviar(`${ruta}/${r.id}/eliminar`, { motivo }); setAviso("Reporte eliminado."); await datos.recargar(); }
    catch (e) { setAviso(e instanceof ErrorApi ? e.message : "No se pudo eliminar."); }
  }

  if (datos.error) return <Aviso tono="critico">{datos.error}</Aviso>;
  if (!datos.datos) return <Esqueleto className="h-48" />;
  const lista = datos.datos.reportes;

  return (
    <div className="space-y-5">
      <Aviso tono="acento" icono={<Lock className="size-4" />}>Reserva legal: estos reportes solo los ve el equipo de cumplimiento. Cada descarga queda en la auditoría.</Aviso>
      {aviso && <Aviso tono="acento">{aviso}</Aviso>}
      {nuevo && <Carga ruta={ruta} tipos={datos.datos.tipos} clientes={clientes.datos?.clientes ?? []}
        onCerrar={() => setNuevo(false)} onCargado={async () => { setNuevo(false); setAviso("Reporte cargado."); await datos.recargar(); }} />}
      <Tarjeta>
        <TituloTarjeta titulo="Reportes UIAF" descripcion="ROS, AROS y otros reportes presentados por SIREL. Aparecen en el tablero de cumplimiento."
          accion={puede && !nuevo ? <Boton variante="primario" onClick={() => { setNuevo(true); setAviso(null); }}><Upload className="size-4" aria-hidden />Cargar reporte</Boton> : undefined} />
        <div className="overflow-x-auto px-5 pb-4 pt-3">
          {lista.length === 0 ? <Vacio icono={<FileText className="size-5" />} titulo="Cargue el primer reporte" texto="Suba el PDF que presentó por SIREL con su radicado." /> : (
            <table className="w-full min-w-[820px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wider text-texto-3">
                <tr><th className="py-2 pr-3">Tipo</th><th className="pr-3">Presentado</th><th className="pr-3">Periodo</th><th className="pr-3">Radicado</th>
                  <th className="pr-3">Subcliente</th><th className="pr-3">Archivo</th><th /></tr>
              </thead>
              <tbody className="divide-y divide-borde">
                {lista.map((r) => (
                  <tr key={r.id}>
                    <td className="py-2.5 pr-3"><Insignia tono={r.tipo === "ROS" ? "critico" : "acento"}>{r.tipo === "otro" ? "Otro" : r.tipo}</Insignia></td>
                    <td className="pr-3">{fecha(r.fecha_presentacion)}</td>
                    <td className="pr-3 text-texto-2">{r.periodo_desde ? `${fecha(r.periodo_desde)} – ${fecha(r.periodo_hasta)}` : "—"}</td>
                    <td className="pr-3 text-texto-2">{r.radicado ?? "—"}</td>
                    <td className="pr-3 text-texto-2">{r.subcliente ?? "—"}</td>
                    <td className="pr-3"><a href={`/api/reportes-uiaf/${r.id}/archivo`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-acento hover:underline">
                      <FileText className="size-3.5" aria-hidden />{r.archivo_nombre}</a>
                      <p className="text-xs text-texto-3">{Math.max(1, Math.round(r.archivo_bytes / 1024))} KB · {r.creado_por} · {fechaHora(r.creado_en)}</p></td>
                    <td className="text-right">{rol === "super_admin" && <Boton variante="fantasma" aria-label="Eliminar" onClick={() => eliminar(r)}><Trash2 className="size-4" aria-hidden /></Boton>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </Tarjeta>
    </div>
  );
}

function Carga({ ruta, tipos, clientes, onCerrar, onCargado }:
  { ruta: string; tipos: Record<string, string>; clientes: { id: number; razon_social: string }[]; onCerrar: () => void; onCargado: () => Promise<void> }) {
  const hoy = new Date().toISOString().slice(0, 10);
  const [f, setF] = useState({ tipo: "ROS", fecha_presentacion: hoy, periodo_desde: "", periodo_hasta: "", radicado: "", cliente_id: "", descripcion: "" });
  const [archivo, setArchivo] = useState<File | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [fallo, setFallo] = useState<string | null>(null);
  const poner = (x: Partial<typeof f>) => setF((v) => ({ ...v, ...x }));
  const listo = archivo && f.fecha_presentacion && (f.tipo !== "AROS" || (f.periodo_desde && f.periodo_hasta));

  async function guardar() {
    if (!archivo) return;
    const fd = new FormData();
    fd.append("archivo", archivo);
    Object.entries(f).forEach(([k, v]) => { if (v) fd.append(k, v); });
    setGuardando(true); setFallo(null);
    try { await api(ruta, { method: "POST", body: fd }); await onCargado(); }
    catch (e) { setFallo(e instanceof ErrorApi ? e.message : "No se pudo cargar."); }
    finally { setGuardando(false); }
  }

  return (
    <Tarjeta>
      <TituloTarjeta titulo="Cargar reporte UIAF" accion={<Boton variante="fantasma" onClick={onCerrar}><X className="size-4" aria-hidden />Cancelar</Boton>} />
      <div className="grid gap-4 px-5 pb-5 pt-3 md:grid-cols-3">
        <div><Etiqueta htmlFor="ru-tipo">Tipo</Etiqueta>
          <Selector id="ru-tipo" value={f.tipo} onChange={(e) => poner({ tipo: e.target.value })}>
            {Object.entries(tipos).map(([k, n]) => <option key={k} value={k}>{n}</option>)}</Selector></div>
        <div><Etiqueta htmlFor="ru-fp">Fecha de presentación</Etiqueta><Entrada id="ru-fp" type="date" max={hoy} value={f.fecha_presentacion} onChange={(e) => poner({ fecha_presentacion: e.target.value })} /></div>
        <div><Etiqueta htmlFor="ru-rad">Radicado SIREL</Etiqueta><Entrada id="ru-rad" value={f.radicado} onChange={(e) => poner({ radicado: e.target.value })} /></div>
        <div><Etiqueta htmlFor="ru-pd">Periodo reportado desde{f.tipo === "AROS" ? "" : " (opcional)"}</Etiqueta><Entrada id="ru-pd" type="date" value={f.periodo_desde} onChange={(e) => poner({ periodo_desde: e.target.value })} /></div>
        <div><Etiqueta htmlFor="ru-ph">hasta</Etiqueta><Entrada id="ru-ph" type="date" value={f.periodo_hasta} onChange={(e) => poner({ periodo_hasta: e.target.value })} /></div>
        <div><Etiqueta htmlFor="ru-cli">Subcliente reportado (opcional)</Etiqueta>
          <Selector id="ru-cli" value={f.cliente_id} onChange={(e) => poner({ cliente_id: e.target.value })}>
            <option value="">—</option>{clientes.map((c) => <option key={c.id} value={c.id}>{c.razon_social}</option>)}</Selector></div>
        <div className="md:col-span-3"><Etiqueta htmlFor="ru-desc">Descripción (opcional)</Etiqueta>
          <textarea id="ru-desc" rows={2} className={area} value={f.descripcion} onChange={(e) => poner({ descripcion: e.target.value })} /></div>
        <div className="md:col-span-3"><Etiqueta htmlFor="ru-pdf">PDF del reporte (máximo 15 MB)</Etiqueta>
          <input id="ru-pdf" type="file" accept="application/pdf,.pdf" className="block text-sm text-texto-2 file:mr-3 file:rounded-lg file:border file:border-borde-fuerte file:bg-panel-2 file:px-3 file:py-1.5 file:text-texto"
            onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} /></div>
        {fallo && <div className="md:col-span-3"><Aviso tono="critico">{fallo}</Aviso></div>}
        <div className="md:col-span-3"><Boton variante="primario" cargando={guardando} disabled={!listo} onClick={guardar}><Upload className="size-4" aria-hidden />Cargar</Boton></div>
      </div>
    </Tarjeta>
  );
}
