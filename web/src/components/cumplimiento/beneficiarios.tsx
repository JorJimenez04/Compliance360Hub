"use client";

import { Fragment, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Copy, FolderPlus, RefreshCw, Users, X } from "lucide-react";
import { Aviso, Boton, Entrada, Esqueleto, Insignia, Tarjeta, TituloTarjeta, Vacio } from "@/components/ui/basicos";
import { enviar, ErrorApi } from "@/lib/api";
import { AsignarArchivo, Checklist, EnlaceArchivo, revisarCarpeta, type ArchivoDoc, type RequisitoDoc } from "./documentacion";
import { useDatos } from "@/lib/useDatos";
import { entero, fecha, fechaHora, moneda, monedaCorta, porcentaje } from "@/lib/formato";
import { cn } from "@/lib/cn";
import { Kpi } from "@/components/monitoreo/tablero";
import { usePuedeGestionar } from "@/lib/sesion";

interface Beneficiario {
  id_beneficiario: string; nombre: string | null; otros_nombres: string[]; tipo_identificacion: string | null;
  tipo_persona: string | null; pagos: number; rechazos: number; monto: number; participacion: number;
  ticket_promedio: number; primer_pago: string | null; ultimo_pago: string | null; bancos: string[];
  cuentas: string[]; empresas: string[]; senales: string[];
}
interface Respuesta {
  total_beneficiarios: number; monto_total: number; pagos_total: number; desde: string | null; hasta: string | null;
  senales: Record<string, string>; beneficiarios: Beneficiario[];
}
interface Movimiento {
  fecha_hora: string; empresa: string; id_transaccion: string; tipo_transaccion: string; estado: string;
  exitosa: boolean; monto: number; banco: string | null; cuenta: string | null; nombre: string | null;
}

const POR_PAGINA = 50;

interface Expediente {
  id_beneficiario: string; nombre: string | null; tipo_persona: "juridica" | "natural"; origen: "top10" | "manual" | "carpeta";
  abierto_por: string; posicion: number | null; monto: number; participacion: number; senales: string[];
  carpeta_nombre: string | null; carpeta_sugerida: string; requisitos: RequisitoDoc[]; completo: boolean; otros_archivos: ArchivoDoc[];
}
interface RespuestaExp { con_carpeta_cliente: boolean; expedientes: Expediente[]; completos: number; documentos: Record<string, string> }
const ORIGEN = { top10: "Top 10", manual: "Agregado", carpeta: "Con carpeta" } as const;

function Copiar({ texto }: { texto: string }) {
  const [hecho, setHecho] = useState(false);
  return (
    <button type="button" title="Copiar nombre de la carpeta" onClick={() => { void navigator.clipboard?.writeText(texto); setHecho(true); setTimeout(() => setHecho(false), 1500); }}
      className="inline-flex items-center gap-1 rounded border border-borde-fuerte px-1.5 py-0.5 text-[11px] text-texto-3 hover:text-texto">
      {hecho ? <CheckCircle2 className="size-3 text-ok" /> : <Copy className="size-3" />}{hecho ? "Copiado" : "Copiar"}</button>
  );
}

function Expedientes({ clienteId, datos, recargar }: { clienteId: number; datos: RespuestaExp; recargar: () => Promise<void> }) {
  const [abierto, setAbierto] = useState<string | null>(null);
  const [aviso, setAviso] = useState<{ ok: boolean; mensaje: string } | null>(null);
  const [revisando, setRevisando] = useState(false);
  const puede = usePuedeGestionar();
  const cerrar = async (idb: string) => {
    if (!window.confirm("¿Cerrar el expediente de este beneficiario? Sus archivos en OneDrive no se tocan.")) return;
    try { await enviar(`/api/clientes/${clienteId}/expedientes-beneficiarios/${encodeURIComponent(idb)}`, {}, "DELETE"); await recargar(); }
    catch (e) { setAviso({ ok: false, mensaje: e instanceof ErrorApi ? e.message : "No se pudo cerrar." }); }
  };
  const faltanCarpetas = datos.expedientes.filter((e) => !e.carpeta_nombre).length;
  return (
    <Tarjeta>
      <TituloTarjeta titulo={`Expedientes documentales · ${datos.completos} de ${datos.expedientes.length} completos`}
        descripcion="Los 10 beneficiarios más representativos por monto, más los que agregue. Sus documentos se leen de «Beneficiarios/{documento} - {nombre}» dentro de la carpeta del cliente."
        accion={puede && datos.con_carpeta_cliente && <Boton className="whitespace-nowrap" cargando={revisando} onClick={async () => {
          setRevisando(true); setAviso(await revisarCarpeta(clienteId)); await recargar(); setRevisando(false);
        }}><RefreshCw className="size-4" aria-hidden />Revisar OneDrive</Boton>} />
      <div className="space-y-3 px-5 pb-5 pt-2">
        {!datos.con_carpeta_cliente && <Aviso tono="alerta">Registre primero la carpeta del cliente en OneDrive (pestaña «Documentación propia»).</Aviso>}
        {aviso && <Aviso tono={aviso.ok ? "ok" : "critico"}>{aviso.mensaje}</Aviso>}
        {datos.con_carpeta_cliente && faltanCarpetas > 0 && (
          <p className="text-xs text-texto-3">{faltanCarpetas} expedientes aún no tienen carpeta: créela dentro de «Beneficiarios» con el nombre indicado.</p>
        )}
        <table className="w-full text-[13px]">
          <thead><tr className="text-left text-texto-3">
            <th className="w-6 py-2" /><th className="py-2 font-medium">Beneficiario</th><th className="py-2 font-medium">Origen</th>
            <th className="py-2 font-medium">Carpeta</th><th className="py-2 font-medium">Documentos</th><th className="w-8 py-2" /></tr></thead>
          <tbody>
            {datos.expedientes.map((e) => {
              const ver = abierto === e.id_beneficiario;
              return (
                <Fragment key={e.id_beneficiario}>
                  <tr className="border-t border-borde/70">
                    <td className="py-2"><button type="button" aria-label="Ver documentos" onClick={() => setAbierto(ver ? null : e.id_beneficiario)} className="text-texto-3 hover:text-texto">
                      {ver ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}</button></td>
                    <td className="py-2">
                      <p className="text-texto">{e.posicion && <span className="cifra mr-1.5 text-texto-3">#{e.posicion}</span>}{e.nombre ?? "Sin nombre"}</p>
                      <p className="text-xs text-texto-3">{e.id_beneficiario} · {e.tipo_persona === "juridica" ? "Persona jurídica" : "Persona natural"} · {monedaCorta(e.monto)} ({porcentaje(e.participacion)})</p>
                    </td>
                    <td className="py-2 text-texto-2">{ORIGEN[e.origen]}</td>
                    <td className="py-2">{e.carpeta_nombre ? <span className="text-texto-2">{e.carpeta_nombre}</span>
                      : <span className="inline-flex flex-wrap items-center gap-1.5 text-xs"><FolderPlus className="size-3.5 text-alerta" aria-hidden />
                          <span className="text-alerta">{puede ? "Crear:" : "Sin carpeta:"}</span><span className="font-mono text-texto-2">{e.carpeta_sugerida}</span>{puede && <Copiar texto={e.carpeta_sugerida} />}</span>}</td>
                    <td className="py-2">
                      <div className="flex flex-wrap gap-1">
                        {e.requisitos.map((r) => <Insignia key={r.codigo} tono={r.cargado ? "ok" : "neutro"}>{r.cargado ? "✓" : "✗"} {r.nombre}</Insignia>)}
                      </div>
                    </td>
                    <td className="py-2">{puede && <button type="button" onClick={() => cerrar(e.id_beneficiario)} title="Cerrar expediente"
                      className="text-texto-3 hover:text-critico"><X className="size-4" /></button>}</td>
                  </tr>
                  {ver && (
                    <tr className="bg-fondo/40"><td /><td colSpan={5} className="pb-3">
                      <Checklist requisitos={e.requisitos} documentos={datos.documentos} onHecho={recargar} />
                      {e.otros_archivos.length > 0 && <div className="mt-2 space-y-1 text-[13px]">
                        <p className="text-xs text-texto-3">Otros archivos en su carpeta:</p>
                        {e.otros_archivos.map((a) => <div key={a.id} className="flex flex-wrap items-center gap-2"><EnlaceArchivo a={a} />
                          <AsignarArchivo a={a} documentos={datos.documentos}
                            permitidos={["documento_identidad", "certificacion_bancaria", "certificado_existencia", "rut"]} onHecho={recargar} /></div>)}
                      </div>}
                    </td></tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </Tarjeta>
  );
}

function Movimientos({ clienteId, idb }: { clienteId: number; idb: string }) {
  const { datos, error } = useDatos<{ movimientos: Movimiento[] }>(
    `/api/clientes/${clienteId}/beneficiarios/${encodeURIComponent(idb)}/movimientos`);
  if (error) return <p className="text-sm text-critico">{error}</p>;
  if (!datos) return <Esqueleto className="h-24" />;
  return (
    <div className="max-h-80 overflow-y-auto rounded-lg border border-borde/60 px-2">
    {datos.movimientos.length >= 200 && <p className="py-1 text-xs text-texto-3">Se muestran los 200 movimientos más recientes.</p>}
    <table className="w-full text-[12px]">
      <thead className="sticky top-0 bg-panel"><tr className="text-left text-texto-3">
        <th className="py-1 pr-3 font-medium">Fecha</th><th className="py-1 pr-3 font-medium">Transacción</th>
        <th className="py-1 pr-3 font-medium">Tipo</th><th className="py-1 pr-3 font-medium">Estado</th>
        <th className="py-1 pr-3 text-right font-medium">Monto</th><th className="py-1 pr-3 font-medium">Banco · cuenta</th>
        <th className="py-1 font-medium">Nombre reportado</th></tr></thead>
      <tbody>
        {datos.movimientos.map((m) => (
          <tr key={m.id_transaccion + m.fecha_hora} className="border-t border-borde/50">
            <td className="py-1 pr-3 text-texto-2">{fechaHora(m.fecha_hora)}</td>
            <td className="py-1 pr-3 font-mono text-texto-3">{m.id_transaccion}</td>
            <td className="py-1 pr-3 text-texto-2">{m.tipo_transaccion}</td>
            <td className={cn("py-1 pr-3", m.exitosa ? "text-texto-2" : "text-alerta")}>{m.estado}</td>
            <td className="cifra py-1 pr-3 text-right">{moneda(m.monto)}</td>
            <td className="py-1 pr-3 text-texto-2">{[m.banco, m.cuenta].filter(Boolean).join(" · ")}</td>
            <td className="py-1 text-texto-3">{m.nombre}</td>
          </tr>
        ))}
      </tbody>
    </table>
    </div>
  );
}

/** A quién le paga el cliente: beneficiarios tomados de sus transacciones, con señales de revisión. */
export default function BeneficiariosCliente({ clienteId }: { clienteId: number }) {
  const { datos, error } = useDatos<Respuesta>(`/api/clientes/${clienteId}/beneficiarios`);
  const exp = useDatos<RespuestaExp>(`/api/clientes/${clienteId}/expedientes-beneficiarios`);
  const conExpediente = useMemo(() => new Set((exp.datos?.expedientes ?? []).map((e) => e.id_beneficiario)), [exp.datos]);
  const [abriendo, setAbriendo] = useState<string | null>(null);
  const puede = usePuedeGestionar();
  const abrirExpediente = async (idb: string) => {
    setAbriendo(idb);
    try { await enviar(`/api/clientes/${clienteId}/expedientes-beneficiarios`, { id_beneficiario: idb }); await exp.recargar(); }
    finally { setAbriendo(null); }
  };
  const [buscar, setBuscar] = useState("");
  const [soloSenales, setSoloSenales] = useState(false);
  const [abierto, setAbierto] = useState<string | null>(null);
  const [pagina, setPagina] = useState(1);

  const filas = useMemo(() => {
    const f = buscar.trim().toLowerCase();
    return (datos?.beneficiarios ?? []).filter((b) => (!soloSenales || b.senales.length)
      && (!f || b.id_beneficiario.includes(f) || (b.nombre ?? "").toLowerCase().includes(f)));
  }, [datos, buscar, soloSenales]);

  if (error) return <Aviso tono="critico" icono={<AlertTriangle className="size-4" />}>{error}</Aviso>;
  if (!datos) return <Esqueleto className="h-96" />;
  if (!datos.total_beneficiarios)
    return <Tarjeta><Vacio icono={<Users className="size-8" />} titulo="Sin beneficiarios"
      texto="Este cliente aún no tiene pagos a beneficiarios en sus transacciones." /></Tarjeta>;

  const conSenales = datos.beneficiarios.filter((b) => b.senales.length).length;
  const top10 = datos.beneficiarios.slice(0, 10).reduce((s, b) => s + b.participacion, 0);
  const visibles = filas.slice(0, pagina * POR_PAGINA);

  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi titulo="Beneficiarios" valor={entero(datos.total_beneficiarios)} detalle={<>{fecha(datos.desde)} – {fecha(datos.hasta)}</>} />
        <Kpi titulo="Monto pagado" valor={monedaCorta(datos.monto_total)} detalle={<>{entero(datos.pagos_total)} pagos exitosos</>} />
        <Kpi titulo="Concentración top 10" valor={porcentaje(top10)} detalle="del monto pagado" />
        <Kpi titulo="Con señales de revisión" valor={entero(conSenales)} detalle={conSenales ? "revise abajo" : "ninguna señal"} />
      </div>

      {exp.datos ? <Expedientes clienteId={clienteId} datos={exp.datos} recargar={exp.recargar} /> : <Esqueleto className="h-48" />}

      <Tarjeta>
        <TituloTarjeta titulo="Beneficiarios del cliente" descripcion="Tomados de sus transacciones, agrupados por documento. Abra uno para ver sus movimientos. Las cuentas se muestran enmascaradas."
          accion={<div className="flex items-center gap-2">
            <button type="button" onClick={() => { setSoloSenales(!soloSenales); setPagina(1); }}
              className={cn("whitespace-nowrap rounded-md border px-2.5 py-1 text-xs", soloSenales ? "border-acento bg-acento-tenue text-texto" : "border-borde-fuerte text-texto-3")}>
              Solo con señales</button>
            <Entrada aria-label="Buscar beneficiario" placeholder="Nombre o documento…" className="w-56" value={buscar}
              onChange={(e) => { setBuscar(e.target.value); setPagina(1); }} />
          </div>} />
        <div className="overflow-x-auto px-2 pb-3 pt-3">
          <table className="w-full min-w-[1100px] text-[13px]">
            <thead><tr className="text-left text-texto-3">
              <th className="w-6 px-2 py-2" /><th className="px-2 py-2 font-medium">Beneficiario</th>
              <th className="px-2 py-2 text-right font-medium">Pagos</th><th className="px-2 py-2 text-right font-medium">Monto</th>
              <th className="px-2 py-2 text-right font-medium">Participación</th><th className="px-2 py-2 font-medium">Primer / último pago</th>
              <th className="px-2 py-2 font-medium">Bancos · cuentas</th><th className="px-2 py-2 font-medium">Señales</th>
              <th className="px-2 py-2 font-medium">Expediente</th></tr></thead>
            <tbody>
              {visibles.map((b) => {
                const ver = abierto === b.id_beneficiario;
                return (
                  <Fragment key={b.id_beneficiario}>
                    <tr className="cursor-pointer border-t border-borde/70 hover:bg-panel-2/60" onClick={() => setAbierto(ver ? null : b.id_beneficiario)}>
                      <td className="px-2 py-2.5 text-texto-3">{ver ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}</td>
                      <td className="px-2 py-2.5">
                        <p className="font-medium text-texto">{b.nombre ?? "Sin nombre"}</p>
                        <p className="text-xs text-texto-3">{b.tipo_identificacion ?? "Doc."} {b.id_beneficiario}{b.tipo_persona && <> · {b.tipo_persona}</>}</p>
                      </td>
                      <td className="cifra whitespace-nowrap px-2 py-2.5 text-right">{entero(b.pagos)}{b.rechazos > 0 && <span className="ml-1 text-xs text-alerta">+{b.rechazos} rech.</span>}</td>
                      <td className="cifra whitespace-nowrap px-2 py-2.5 text-right">{monedaCorta(b.monto)}</td>
                      <td className="cifra whitespace-nowrap px-2 py-2.5 text-right">{porcentaje(b.participacion)}</td>
                      <td className="whitespace-nowrap px-2 py-2.5 text-texto-2">{fecha(b.primer_pago)} – {fecha(b.ultimo_pago)}</td>
                      <td className="px-2 py-2.5 text-texto-2">{b.bancos.join(", ") || "—"}<span className="text-texto-3"> · {b.cuentas.length} cta.</span></td>
                      <td className="px-2 py-2.5">
                        <div className="flex flex-wrap gap-1">
                          {b.senales.map((s) => <span key={s} title={datos.senales[s]}><Insignia tono="serio">{datos.senales[s]}</Insignia></span>)}
                        </div>
                      </td>
                      <td className="px-2 py-2.5" onClick={(ev) => ev.stopPropagation()}>
                        {conExpediente.has(b.id_beneficiario) ? <span className="text-xs text-ok">Abierto</span>
                          : !puede ? <span className="text-xs text-texto-3">—</span> : <button type="button" disabled={abriendo === b.id_beneficiario} onClick={() => abrirExpediente(b.id_beneficiario)}
                              className="whitespace-nowrap text-xs text-acento hover:underline disabled:opacity-50">+ Abrir</button>}
                      </td>
                    </tr>
                    {ver && (
                      <tr className="bg-fondo/40">
                        <td />
                        <td colSpan={8} className="space-y-2 px-2 pb-3 pt-1">
                          <p className="text-xs text-texto-3">
                            Ticket promedio {moneda(b.ticket_promedio)} · Cuentas: {b.cuentas.join(", ") || "—"}
                            {b.otros_nombres.length > 0 && <> · También reportado como: {b.otros_nombres.join(", ")}</>}
                            {b.empresas.length > 1 && <> · Empresas: {b.empresas.join(", ")}</>}
                          </p>
                          <Movimientos clienteId={clienteId} idb={b.id_beneficiario} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
          {!filas.length && <p className="px-3 py-6 text-center text-sm text-texto-3">Ningún beneficiario coincide.</p>}
          {filas.length > visibles.length && (
            <div className="pt-3 text-center">
              <button type="button" className="text-sm text-acento hover:underline" onClick={() => setPagina(pagina + 1)}>
                Ver más ({entero(filas.length - visibles.length)} restantes)</button>
            </div>
          )}
        </div>
      </Tarjeta>
    </div>
  );
}
