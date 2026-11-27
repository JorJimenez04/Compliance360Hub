"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle2, Clock, ShieldAlert, X } from "lucide-react";
import { Aviso, Boton, Esqueleto, Etiqueta, Insignia, Selector, Tarjeta, TituloTarjeta, Vacio } from "@/components/ui/basicos";
import { enviar, ErrorApi } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";
import { usePuedeGestionar } from "@/lib/sesion";
import { fecha, fechaHora, mesCorto } from "@/lib/formato";
import type { AlertaCaso, AlertaDetalle, EstadoAlerta, Prioridad } from "@/lib/tipos";
import { cn } from "@/lib/cn";

export const NOMBRE_ESTADO: Record<EstadoAlerta, string> = {
  nueva: "Nueva", en_analisis: "En análisis", descartada: "Descartada", escalada: "Escalada", posible_ros: "Posible ROS",
};
const TONO_ESTADO: Record<EstadoAlerta, "neutro" | "acento" | "ok" | "alerta" | "critico"> = {
  nueva: "acento", en_analisis: "alerta", descartada: "ok", escalada: "critico", posible_ros: "critico",
};
const TONO_PRIORIDAD: Record<Prioridad, "critico" | "serio" | "alerta" | "neutro"> = {
  "Crítica": "critico", Alta: "serio", Media: "alerta", Baja: "neutro",
};
const ABIERTAS: EstadoAlerta[] = ["nueva", "en_analisis", "escalada"];
const REQUIERE_JUSTIFICACION: EstadoAlerta[] = ["descartada", "escalada", "posible_ros"];

const vencida = (a: AlertaCaso) => !!a.fecha_limite && ABIERTAS.includes(a.estado)
  && a.fecha_limite < new Date().toISOString().slice(0, 10);

/** Lista de alertas y casos con su panel de gestión. `ruta`: endpoint GET que devuelve {alertas}. */
export function ListaAlertas({ ruta, mostrarEmpresa = true }: { ruta: string; mostrarEmpresa?: boolean }) {
  const [filtro, setFiltro] = useState<"abiertas" | "todas" | EstadoAlerta>("abiertas");
  const { datos, error, recargar } = useDatos<{ alertas: AlertaCaso[] }>(ruta);
  const [abierta, setAbierta] = useState<number | null>(null);

  const todas = datos?.alertas ?? [];
  const filas = todas.filter((a) => filtro === "todas" || (filtro === "abiertas" ? ABIERTAS.includes(a.estado) : a.estado === filtro));
  const cuenta = (f: typeof filtro) => todas.filter((a) => f === "todas" || (f === "abiertas" ? ABIERTAS.includes(a.estado) : a.estado === f)).length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filtrar por estado">
        {(["abiertas", "nueva", "en_analisis", "escalada", "posible_ros", "descartada", "todas"] as const).map((f) => (
          <button key={f} onClick={() => setFiltro(f)} aria-pressed={filtro === f}
            className={cn("rounded-full border px-3 py-1 text-[13px]", filtro === f ? "border-acento/40 bg-acento-tenue text-acento" : "border-borde-fuerte text-texto-3 hover:text-texto-2")}>
            {f === "abiertas" ? "Abiertas" : f === "todas" ? "Todas" : NOMBRE_ESTADO[f]} <span className="cifra text-texto-3">{cuenta(f)}</span>
          </button>
        ))}
      </div>
      {error && <Aviso tono="critico" icono={<AlertTriangle className="size-4" />}>{error}</Aviso>}
      <div className={cn("grid gap-5", abierta && "xl:grid-cols-[1fr_440px]")}>
        <Tarjeta>
          {!datos ? <div className="space-y-2 p-5">{[0, 1, 2].map((i) => <Esqueleto key={i} className="h-12" />)}</div>
            : !filas.length ? <Vacio icono={<CheckCircle2 className="size-8" />} titulo={filtro === "abiertas" ? "Sin alertas abiertas" : "Sin alertas en este estado"}
                texto="Las alertas se generan al cargar transacciones, comparando cada mes con las reglas del monitoreo y con el perfil declarado del cliente." />
            : (
              <div className="overflow-x-auto px-2 py-2">
                <table className="w-full min-w-[760px] text-[13px]">
                  <thead><tr className="text-left text-texto-3">
                    <th className="px-3 py-2 font-medium">Prioridad</th><th className="px-3 py-2 font-medium">Alerta</th>
                    {mostrarEmpresa && <th className="px-3 py-2 font-medium">Empresa</th>}
                    <th className="px-3 py-2 font-medium">Mes</th><th className="px-3 py-2 font-medium">Estado</th>
                    <th className="px-3 py-2 font-medium">Analista</th><th className="px-3 py-2 font-medium">Límite</th></tr></thead>
                  <tbody>
                    {filas.map((a) => (
                      <tr key={a.id} onClick={() => setAbierta(a.id)}
                        className={cn("cursor-pointer border-t border-borde/70 hover:bg-panel-2/60", abierta === a.id && "bg-acento-tenue")}>
                        <td className="px-3 py-2.5"><Insignia tono={TONO_PRIORIDAD[a.prioridad]}>{a.prioridad}</Insignia></td>
                        <td className="px-3 py-2.5"><p className="text-texto">{a.titulo}</p>
                          {a.requiere_reporte_uiaf && <p className="mt-0.5 inline-flex items-center gap-1 text-xs text-serio"><ShieldAlert className="size-3" />Puede requerir reporte a la UIAF</p>}</td>
                        {mostrarEmpresa && <td className="px-3 py-2.5 text-texto-2">{a.empresa}</td>}
                        <td className="px-3 py-2.5 text-texto-2">{mesCorto(a.periodo)}</td>
                        <td className="px-3 py-2.5"><Insignia tono={TONO_ESTADO[a.estado]}>{NOMBRE_ESTADO[a.estado]}</Insignia></td>
                        <td className="px-3 py-2.5 text-texto-2">{a.analista ?? "—"}</td>
                        <td className={cn("px-3 py-2.5", vencida(a) ? "font-medium text-critico" : "text-texto-3")}>
                          {a.fecha_limite ? <span className="inline-flex items-center gap-1">{vencida(a) && <Clock className="size-3.5" />}{fecha(a.fecha_limite)}</span> : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
        </Tarjeta>
        {abierta && <PanelAlerta id={abierta} onCerrar={() => setAbierta(null)} onCambio={recargar} />}
      </div>
    </div>
  );
}

function PanelAlerta({ id, onCerrar, onCambio }: { id: number; onCerrar: () => void; onCambio: () => void }) {
  const puede = usePuedeGestionar();      // el director de cumplimiento solo consulta
  const { datos: a, error, recargar } = useDatos<AlertaDetalle>(`/api/alertas/${id}`);
  const analistas = useDatos<{ analistas: { id: number; nombre: string }[] }>("/api/alertas/analistas");
  const [destino, setDestino] = useState<EstadoAlerta | "">("");
  const [texto, setTexto] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [fallo, setFallo] = useState<string | null>(null);

  async function enviarCambio(cuerpo: Record<string, unknown>) {
    setGuardando(true); setFallo(null);
    try { await enviar(`/api/alertas/${id}`, cuerpo, "PATCH"); setTexto(""); setDestino(""); await recargar(); onCambio(); }
    catch (e) { setFallo(e instanceof ErrorApi ? e.message : "No se pudo guardar."); }
    finally { setGuardando(false); }
  }

  if (error) return <Tarjeta className="p-5"><Aviso tono="critico">{error}</Aviso></Tarjeta>;
  if (!a) return <Tarjeta className="p-5"><Esqueleto className="h-64" /></Tarjeta>;
  const exige = destino && REQUIERE_JUSTIFICACION.includes(destino);

  return (
    <Tarjeta className="self-start xl:sticky xl:top-6">
      <TituloTarjeta titulo={a.titulo} descripcion={`${a.empresa} · ${mesCorto(a.periodo)} · regla ${a.regla}`}
        accion={<button onClick={onCerrar} aria-label="Cerrar" className="rounded-md p-1 text-texto-3 hover:bg-panel-2 hover:text-texto"><X className="size-4" /></button>} />
      <div className="space-y-4 px-5 pb-5 pt-3 text-sm">
        <div className="flex flex-wrap gap-2">
          <Insignia tono={TONO_PRIORIDAD[a.prioridad]}>{a.prioridad}</Insignia>
          <Insignia tono={TONO_ESTADO[a.estado]}>{NOMBRE_ESTADO[a.estado]}</Insignia>
          {a.tipo && <Insignia>{a.tipo}</Insignia>}
        </div>
        {a.descripcion && <p className="text-texto-2">{a.descripcion}</p>}
        {a.accion_requerida && <p><span className="text-texto-3">Acción requerida: </span>{a.accion_requerida}</p>}
        {a.justificacion && <Aviso tono="acento" titulo={`Decisión de ${a.decidida_por} · ${fechaHora(a.decidida_en)}`}>{a.justificacion}</Aviso>}
        {fallo && <Aviso tono="critico">{fallo}</Aviso>}

        {puede && (<>
        <div className="grid gap-3 sm:grid-cols-2">
          <div><Etiqueta htmlFor="analista">Analista</Etiqueta>
            <Selector id="analista" disabled={guardando} value={a.analista_id ?? ""}
              onChange={(e) => enviarCambio(e.target.value ? { analista_id: Number(e.target.value) } : { quitar_analista: true })}>
              <option value="">Sin asignar</option>
              {analistas.datos?.analistas.map((x) => <option key={x.id} value={x.id}>{x.nombre}</option>)}
            </Selector></div>
          {a.transiciones.length > 0 && (
            <div><Etiqueta htmlFor="destino">Cambiar estado</Etiqueta>
              <Selector id="destino" disabled={guardando} value={destino} onChange={(e) => setDestino(e.target.value as EstadoAlerta | "")}>
                <option value="">—</option>
                {a.transiciones.map((t) => <option key={t} value={t}>{NOMBRE_ESTADO[t]}</option>)}
              </Selector></div>
          )}
        </div>
        <div>
          <Etiqueta htmlFor="texto">{exige ? "Justificación (obligatoria)" : destino ? "Motivo" : "Nota de seguimiento"}</Etiqueta>
          <textarea id="texto" rows={3} value={texto} onChange={(e) => setTexto(e.target.value)}
            placeholder={exige ? "Explique la decisión y los soportes revisados" : "Qué se revisó, qué se pidió al cliente…"}
            className="w-full rounded-lg border border-borde-fuerte bg-fondo px-3 py-2 text-sm text-texto placeholder:text-texto-3 focus:border-acento focus:outline-none" />
        </div>
        <div className="flex gap-2">
          {destino ? (
            <Boton variante={destino === "posible_ros" || destino === "escalada" ? "peligro" : "primario"} cargando={guardando}
              disabled={!!exige && texto.trim().length < 10}
              onClick={() => enviarCambio({ estado: destino, ...(exige ? { justificacion: texto } : { nota: texto }) })}>
              Pasar a «{NOMBRE_ESTADO[destino]}»
            </Boton>
          ) : (
            <Boton cargando={guardando} disabled={!texto.trim()} onClick={() => enviarCambio({ nota: texto })}>Agregar nota</Boton>
          )}
        </div>

        </>)}

        <div>
          <p className="mb-2 text-[13px] font-medium text-texto-2">Trazabilidad</p>
          <ol className="space-y-2.5 border-l border-borde pl-4">
            {a.eventos.slice().reverse().map((e) => (
              <li key={e.id} className="text-[13px]">
                <p className="text-texto-3">{fechaHora(e.creado_en)} · {e.usuario}</p>
                <p className="text-texto">
                  {e.accion === "detectada" ? "Alerta detectada"
                    : e.accion === "estado" ? <>Estado: {NOMBRE_ESTADO[e.estado_anterior as EstadoAlerta] ?? e.estado_anterior} → {NOMBRE_ESTADO[e.estado_nuevo as EstadoAlerta] ?? e.estado_nuevo}</>
                    : e.accion === "asignacion" ? "Cambio de analista" : "Nota"}
                </p>
                {e.nota && e.accion !== "detectada" && <p className="text-texto-2">{e.nota}</p>}
              </li>
            ))}
          </ol>
        </div>
      </div>
    </Tarjeta>
  );
}
