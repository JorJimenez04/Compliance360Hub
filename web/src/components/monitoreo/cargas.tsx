"use client";

import { useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Cloud, CloudOff, Copy, ExternalLink, FileUp, Info, Link2Off, RefreshCw, XCircle } from "lucide-react";
import { Aviso, Boton, Entrada, Esqueleto, Etiqueta, Insignia, Tarjeta, TituloTarjeta, Vacio } from "@/components/ui/basicos";
import { api, enviar } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";
import { entero, fechaHora, haceCuanto } from "@/lib/formato";
import type { Carga, Nube, Resumen } from "@/lib/tipos";
import { cn } from "@/lib/cn";

type Mensaje = { tono: "ok" | "alerta" | "critico"; titulo: string; texto?: string } | null;

function tonoResultado(r: string) {
  if (r === "OK") return "ok" as const;
  if (r === "OMITIDA") return "neutro" as const;
  if (r === "EN_CURSO") return "acento" as const;
  if (r === "PARCIAL" || r === "CON_ERRORES") return "alerta" as const;
  return "critico" as const;
}
const NOMBRE_RESULTADO: Record<string, string> = { OK: "Correcta", OMITIDA: "Sin cambios", EN_CURSO: "En curso", PARCIAL: "Parcial", CON_ERRORES: "Con errores", ERROR: "Error" };

export default function VistaCargas({ puedeCargar, alCargar }: { puedeCargar: boolean; alCargar: () => void }) {
  const nube = useDatos<Nube>("/api/monitoreo/nube");
  const cargas = useDatos<{ cargas: Carga[] }>("/api/monitoreo/cargas");
  const recargarTodo = () => { nube.recargar(); cargas.recargar(); alCargar(); };

  return (
    <div className="space-y-5">
      <div className="grid gap-5 xl:grid-cols-5">
        <PanelNube n={nube.datos} cargando={nube.cargando} puedeCargar={puedeCargar} alCambiar={recargarTodo} className="xl:col-span-3" />
        {puedeCargar && <CargaManual alCargar={recargarTodo} className="xl:col-span-2" />}
      </div>

      <Tarjeta>
        <TituloTarjeta titulo="Bitácora de cargas" descripcion="Cada archivo procesado, automático o manual" />
        {!cargas.datos ? <div className="space-y-2 p-5">{[0, 1, 2, 3].map((i) => <Esqueleto key={i} className="h-10" />)}</div>
          : cargas.datos.cargas.length === 0 ? <Vacio titulo="Todavía no hay cargas" />
          : (
            <div className="overflow-x-auto px-2 pb-3 pt-3">
              <table className="w-full min-w-[860px] text-[13px]">
                <thead><tr className="text-left text-texto-3">
                  <th className="px-3 py-2 font-medium">Fecha</th><th className="px-3 py-2 font-medium">Archivo</th>
                  <th className="px-3 py-2 font-medium">Resultado</th><th className="px-3 py-2 text-right font-medium">Leídas</th>
                  <th className="px-3 py-2 text-right font-medium">Nuevas</th><th className="px-3 py-2 text-right font-medium">Actualizadas</th>
                  <th className="px-3 py-2 text-right font-medium">Rechazadas</th><th className="px-3 py-2 font-medium">Completitud</th>
                  <th className="px-3 py-2 font-medium">Origen</th></tr></thead>
                <tbody>
                  {cargas.datos.cargas.map((c) => (
                    <tr key={c.id} className="border-t border-borde/70 align-top" title={c.mensaje ?? undefined}>
                      <td className="whitespace-nowrap px-3 py-2.5 text-texto-2">{fechaHora(c.fecha)}</td>
                      <td className="px-3 py-2.5"><span className="block max-w-[260px] truncate">{c.archivo ?? "—"}</span></td>
                      <td className="px-3 py-2.5"><Insignia tono={tonoResultado(c.resultado)}>{NOMBRE_RESULTADO[c.resultado] ?? c.resultado}</Insignia></td>
                      <td className="cifra px-3 py-2.5 text-right">{entero(c.leidas)}</td>
                      <td className="cifra px-3 py-2.5 text-right">{entero(c.nuevas)}</td>
                      <td className="cifra px-3 py-2.5 text-right">{entero(c.actualizadas)}</td>
                      <td className={cn("cifra px-3 py-2.5 text-right", c.rechazadas > 0 && "text-serio")}>{entero(c.rechazadas)}</td>
                      <td className="px-3 py-2.5">{c.resultado === "OMITIDA" ? <span className="text-texto-3">—</span>
                        : c.faltantes || c.descuadres_saldo
                          ? <span className="inline-flex items-center gap-1 text-alerta"><AlertTriangle className="size-3.5" aria-hidden />
                              {[c.faltantes && `${entero(c.faltantes)} faltantes`, c.descuadres_saldo && `${entero(c.descuadres_saldo)} descuadres`].filter(Boolean).join(" · ")}</span>
                          : <span className="inline-flex items-center gap-1 text-texto-2"><CheckCircle2 className="size-3.5 text-ok" aria-hidden />Completa</span>}
                      </td>
                      <td className="px-3 py-2.5 text-texto-3">{c.usuario ?? "—"}</td>
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

// ---------------- OneDrive ----------------
function PanelNube({ n, cargando, puedeCargar, alCambiar, className }:
  { n: Nube | null; cargando: boolean; puedeCargar: boolean; alCambiar: () => void; className?: string }) {
  const [msg, setMsg] = useState<Mensaje>(null);
  const [ocupado, setOcupado] = useState<null | "sync" | "conectar" | "desconectar">(null);
  const [codigo, setCodigo] = useState<{ codigo: string; url: string; vence: number } | null>(null);
  const sondeo = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => { if (sondeo.current) clearInterval(sondeo.current); }, []);

  async function sincronizar() {
    setOcupado("sync"); setMsg(null);
    try {
      const r = await enviar<{ resultado: string; mensaje: string; cargados: number; errores: number }>("/api/monitoreo/nube/sincronizar");
      setMsg({ tono: r.errores ? "alerta" : "ok", titulo: r.cargados ? `Se cargaron ${r.cargados} archivo(s)` : "Revisión completada", texto: r.mensaje });
      alCambiar();
    } catch (e) { setMsg({ tono: "critico", titulo: "No se pudo revisar OneDrive", texto: (e as Error).message }); }
    finally { setOcupado(null); }
  }

  async function conectar() {
    setOcupado("conectar"); setMsg(null);
    try {
      const r = await enviar<{ codigo: string; url: string; vence_en_s: number }>("/api/monitoreo/nube/conectar");
      setCodigo({ codigo: r.codigo, url: r.url, vence: Date.now() + r.vence_en_s * 1000 });
      if (sondeo.current) clearInterval(sondeo.current);
      sondeo.current = setInterval(async () => {
        try {
          const c = await enviar<{ listo: boolean; cuenta?: string }>("/api/monitoreo/nube/completar");
          if (c.listo) {
            clearInterval(sondeo.current!); setCodigo(null);
            setMsg({ tono: "ok", titulo: "OneDrive conectado", texto: `Cuenta ${c.cuenta}. La revisión diaria ya puede leer la carpeta.` });
            alCambiar();
          }
        } catch (e) {
          clearInterval(sondeo.current!); setCodigo(null);
          setMsg({ tono: "critico", titulo: "No se completó la conexión", texto: (e as Error).message });
        }
      }, 5000);
    } catch (e) { setMsg({ tono: "critico", titulo: "No se pudo iniciar la conexión", texto: (e as Error).message }); }
    finally { setOcupado(null); }
  }

  async function desconectar() {
    if (!window.confirm("¿Desconectar OneDrive? La revisión diaria dejará de cargar archivos hasta que se conecte de nuevo.")) return;
    setOcupado("desconectar");
    try { await enviar("/api/monitoreo/nube/desconectar"); setMsg({ tono: "ok", titulo: "OneDrive desconectado" }); alCambiar(); }
    catch (e) { setMsg({ tono: "critico", titulo: "No se pudo desconectar", texto: (e as Error).message }); }
    finally { setOcupado(null); }
  }

  const ultima = n?.revisiones[0];
  const conectado = !!n?.lista;

  return (
    <Tarjeta className={className}>
      <TituloTarjeta titulo="Carga automática desde OneDrive"
        descripcion="Todos los días a las 7:00 p. m. se revisa la carpeta y se cargan los historiales nuevos."
        accion={n && (conectado ? <Insignia tono="ok"><Cloud className="size-3.5" aria-hidden />Conectado</Insignia>
          : <Insignia tono="alerta"><CloudOff className="size-3.5" aria-hidden />{n.configurada ? "Sin conectar" : "No configurado"}</Insignia>)} />
      <div className="space-y-4 px-5 pb-5 pt-4">
        {!n && cargando ? <Esqueleto className="h-24" /> : n && (
          <>
            <dl className="grid gap-4 text-[13px] sm:grid-cols-2">
              <div><dt className="text-texto-3">Carpeta</dt><dd className="mt-0.5 break-words text-texto-2">{n.descripcion ?? "—"}</dd></div>
              {n.conexion && <div><dt className="text-texto-3">Cuenta</dt><dd className="mt-0.5 text-texto-2">{n.conexion.cuenta}
                <span className="block text-texto-3">desde {fechaHora(n.conexion.conectado_en)}</span></dd></div>}
              <div><dt className="text-texto-3">Última revisión</dt><dd className="mt-0.5 text-texto-2">
                {ultima ? <>{haceCuanto(ultima.fecha)} · <span className="text-texto-3">{ultima.usuario === "programada" ? "programada" : `manual (${ultima.usuario})`}</span>
                  <span className="block text-texto-3">{ultima.mensaje}</span></> : "Nunca"}</dd></div>
            </dl>

            {!n.configurada && <Aviso tono="alerta" icono={<Info className="size-4" />}>
              El servidor no tiene las variables TX_ONEDRIVE_*. Siga la guía «Carga automática desde OneDrive».</Aviso>}

            {codigo && (
              <div className="rounded-xl border border-acento/30 bg-acento-tenue p-4">
                <p className="text-sm text-texto">1. Abra la página de Microsoft e inicie sesión con su cuenta corporativa.</p>
                <a href={codigo.url} target="_blank" rel="noopener" className="mt-1 inline-flex items-center gap-1 text-sm text-acento underline-offset-2 hover:underline">
                  {codigo.url}<ExternalLink className="size-3.5" aria-hidden /></a>
                <p className="mt-3 text-sm text-texto">2. Escriba este código:</p>
                <div className="mt-1 flex items-center gap-3">
                  <span className="mono select-all text-2xl font-semibold tracking-[0.2em] text-acento">{codigo.codigo}</span>
                  <button onClick={() => navigator.clipboard?.writeText(codigo.codigo)} className="rounded-md p-1.5 text-texto-3 hover:bg-panel-2 hover:text-texto" aria-label="Copiar código"><Copy className="size-4" /></button>
                </div>
                <p className="mt-3 flex items-center gap-2 text-[13px] text-texto-3"><RefreshCw className="size-3.5 animate-spin" aria-hidden />Esperando a que termine de iniciar sesión…</p>
              </div>
            )}

            {msg && <Aviso tono={msg.tono} titulo={msg.titulo} icono={msg.tono === "ok" ? <CheckCircle2 className="size-4" /> : msg.tono === "alerta" ? <AlertTriangle className="size-4" /> : <XCircle className="size-4" />}>{msg.texto}</Aviso>}

            {puedeCargar && n.configurada && (
              <div className="flex flex-wrap gap-2">
                {conectado && <Boton variante="primario" cargando={ocupado === "sync"} onClick={sincronizar}><RefreshCw className="size-4" />Revisar ahora</Boton>}
                {n.delegado && !codigo && <Boton cargando={ocupado === "conectar"} onClick={conectar}><Cloud className="size-4" />{n.conexion ? "Reconectar" : "Conectar OneDrive"}</Boton>}
                {n.delegado && n.conexion && <Boton variante="fantasma" cargando={ocupado === "desconectar"} onClick={desconectar}><Link2Off className="size-4" />Desconectar</Boton>}
              </div>
            )}

            {n.archivos.length > 0 && (
              <div className="border-t border-borde pt-4">
                <p className="mb-2 text-[13px] font-medium text-texto-2">Últimos archivos vistos en la carpeta</p>
                <ul className="space-y-2 text-[13px]">
                  {n.archivos.slice(0, 5).map((a, i) => (
                    <li key={i} className="flex items-start justify-between gap-3" title={a.mensaje}>
                      <span className="min-w-0"><span className="block truncate text-texto-2">{a.empresa} / {a.nombre}</span>
                        <span className="text-texto-3">{fechaHora(a.fecha)}</span></span>
                      <Insignia tono={tonoResultado(a.resultado)}>{NOMBRE_RESULTADO[a.resultado] ?? a.resultado}</Insignia>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </div>
    </Tarjeta>
  );
}

// ---------------- Carga manual ----------------
function CargaManual({ alCargar, className }: { alCargar: () => void; className?: string }) {
  const [archivo, setArchivo] = useState<File | null>(null);
  const [empresa, setEmpresa] = useState("");
  const [forzar, setForzar] = useState(false);
  const [cargando, setCargando] = useState(false);
  const [msg, setMsg] = useState<Mensaje>(null);
  const [empresas, setEmpresas] = useState<string[]>([]);
  const entrada = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api<Resumen>("/api/monitoreo/resumen").then((r) => setEmpresas(r.empresas.map((e) => e.nombre_reporte))).catch(() => {});
  }, []);

  const esCsv = archivo?.name.toLowerCase().endsWith(".csv");

  async function cargar(e: React.FormEvent) {
    e.preventDefault();
    if (!archivo) return;
    setCargando(true); setMsg(null);
    const fd = new FormData();
    fd.append("archivo", archivo);
    if (empresa.trim()) fd.append("empresa", empresa.trim());
    fd.append("forzar", String(forzar));
    try {
      const r = await api<{ resultado: string; mensaje: string; insertadas: number; actualizadas: number; rechazadas: number; faltantes: number }>(
        "/api/monitoreo/cargas", { method: "POST", body: fd });
      const tono = r.resultado === "OK" && !r.faltantes ? "ok" : r.resultado === "OMITIDA" ? "alerta" : r.resultado === "ERROR" ? "critico" : "alerta";
      setMsg({ tono, titulo: r.resultado === "OMITIDA" ? "El archivo no tiene cambios" : `${entero(r.insertadas)} nuevas · ${entero(r.actualizadas)} actualizadas`, texto: r.mensaje });
      setArchivo(null); if (entrada.current) entrada.current.value = "";
      alCargar();
    } catch (err) { setMsg({ tono: "critico", titulo: "No se pudo cargar el archivo", texto: (err as Error).message }); }
    finally { setCargando(false); }
  }

  return (
    <Tarjeta className={className}>
      <TituloTarjeta titulo="Carga manual" descripcion="Para un archivo puntual. Lo habitual es la carga automática." />
      <form onSubmit={cargar} className="space-y-4 px-5 pb-5 pt-4">
        <label className={cn("flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border border-dashed px-4 py-7 text-center transition-colors",
          archivo ? "border-acento/40 bg-acento-tenue" : "border-borde-fuerte hover:border-texto-3")}>
          <FileUp className={cn("size-6", archivo ? "text-acento" : "text-texto-3")} aria-hidden />
          <span className="text-sm">{archivo ? archivo.name : "Elegir el CSV «Historial de pagos»"}</span>
          <span className="text-[12px] text-texto-3">{archivo ? `${(archivo.size / 1024 / 1024).toFixed(1)} MB` : "CSV o Excel de AdamoPay · máximo 25 MB"}</span>
          <input ref={entrada} type="file" accept=".csv,.xlsx" className="sr-only" onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} />
        </label>
        <div>
          <Etiqueta htmlFor="empresa-carga">Empresa {esCsv && <span className="text-critico">*</span>}</Etiqueta>
          <Entrada id="empresa-carga" list="empresas-conocidas" value={empresa} onChange={(e) => setEmpresa(e.target.value)}
            placeholder="Tal como se llama su carpeta en OneDrive" />
          <datalist id="empresas-conocidas">{empresas.map((e) => <option key={e} value={e} />)}</datalist>
        </div>
        <label className="flex items-start gap-2.5 text-[13px] text-texto-2">
          <input type="checkbox" checked={forzar} onChange={(e) => setForzar(e.target.checked)} className="mt-0.5 accent-[#5fe9d0]" />
          <span>Reprocesar aunque el archivo ya se haya cargado</span>
        </label>
        {msg && <Aviso tono={msg.tono} titulo={msg.titulo}>{msg.texto}</Aviso>}
        <Boton type="submit" variante="primario" className="w-full" cargando={cargando} disabled={!archivo || (esCsv && !empresa.trim())}>Cargar archivo</Boton>
      </form>
    </Tarjeta>
  );
}
