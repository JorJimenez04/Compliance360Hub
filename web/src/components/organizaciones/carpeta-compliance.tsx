"use client";

import { useEffect, useState } from "react";
import { FolderOpen, RefreshCw, Save } from "lucide-react";
import { Aviso, Boton, Entrada, Esqueleto, Etiqueta, Insignia, Tarjeta, TituloTarjeta } from "@/components/ui/basicos";
import { enviar, ErrorApi } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";
import { usePuedeGestionar } from "@/lib/sesion";
import { fechaHora, haceCuanto } from "@/lib/formato";

interface Resumen {
  subclientes: { cliente_id: number; subcliente: string; carpeta: string; enlace: "manual" | "compliance" }[];
  carpetas_sin_subcliente: string[];
  aliados: { relacion_id: number; aliado: string; carpeta: string; archivos: number }[];
  aliados_sin_carpeta: string[]; carpetas_sin_aliado: string[];
  requerimientos: number; carpetas_req_sin_coincidir: string[];
}
interface Estado { carpeta_compliance: string | null; carpeta_nombre: string | null; carpeta_revisada_en: string | null; carpeta_error: string | null; carpeta_resumen: Resumen | null }

const ESTRUCTURA = `Compliance/
├── {Subcliente}/                  Documentación corporativa · Beneficiarios · Requerimientos
├── Aliados bancarios/{Aliado}/    contrato, póliza, licencia, AML, RUT, cámara…
└── Requerimientos/REQ-2026-001 - Asunto/   1. Solicitud · 2. Soportes · 3. Respuesta`;

/** Un solo enlace por organización: la plataforma encuentra subclientes, aliados y requerimientos por nombre. */
export default function CarpetaCompliance({ organizacionId }: { organizacionId: number }) {
  const puede = usePuedeGestionar();
  const ruta = `/api/organizaciones/${organizacionId}/carpeta-compliance`;
  const d = useDatos<Estado>(ruta);
  const [url, setUrl] = useState("");
  const [trabajando, setTrabajando] = useState<"guardar" | "revisar" | null>(null);
  const [aviso, setAviso] = useState<{ ok: boolean; mensaje: string } | null>(null);
  useEffect(() => setUrl(d.datos?.carpeta_compliance ?? ""), [d.datos?.carpeta_compliance]);

  async function ejecutar(tipo: "guardar" | "revisar") {
    setTrabajando(tipo); setAviso(null);
    try {
      const r = tipo === "guardar" ? await enviar<{ resumen: Resumen | null }>(ruta, { enlace: url.trim() || null }, "PUT")
        : await enviar<{ resumen: Resumen }>(`${ruta}/revisar`, {});
      const s = r?.resumen;
      setAviso({ ok: true, mensaje: s ? `Carpeta revisada: ${s.subclientes.length} subclientes, ${s.aliados.length} aliados y ${s.requerimientos} requerimientos encontrados.`
        : "Enlace retirado." });
    } catch (e) { setAviso({ ok: false, mensaje: e instanceof ErrorApi ? e.message : "No se pudo revisar la carpeta." }); }
    finally { setTrabajando(null); await d.recargar(); }
  }

  if (!d.datos) return <Esqueleto className="h-40" />;
  const e = d.datos;
  const r = e.carpeta_resumen;
  return (
    <Tarjeta>
      <TituloTarjeta titulo="Carpeta Compliance en OneDrive"
        descripcion="Pegue una sola vez el enlace de la carpeta Compliance de la organización. La plataforma encuentra por su nombre las carpetas de subclientes, aliados bancarios y requerimientos (sin importar mayúsculas, tildes ni números al inicio). Solo lee: nunca modifica OneDrive."
        accion={puede && e.carpeta_compliance ? <Boton className="whitespace-nowrap" cargando={trabajando === "revisar"} onClick={() => ejecutar("revisar")}>
          <RefreshCw className="size-4" aria-hidden />Revisar ahora</Boton> : undefined} />
      <div className="space-y-4 px-5 pb-5 pt-3">
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-[320px] flex-1"><Etiqueta htmlFor="carpeta-comp">Enlace de la carpeta Compliance</Etiqueta>
            <Entrada id="carpeta-comp" disabled={!puede} placeholder="https://…sharepoint.com/:f:/g/personal/…" value={url} onChange={(ev) => setUrl(ev.target.value)} /></div>
          {puede && <Boton variante="primario" cargando={trabajando === "guardar"} disabled={(url.trim() || null) === (e.carpeta_compliance || null)}
            onClick={() => ejecutar("guardar")}><Save className="size-4" aria-hidden />Guardar y revisar</Boton>}
        </div>
        {e.carpeta_revisada_en && !e.carpeta_error && (
          <p className="text-xs text-texto-3"><FolderOpen className="mr-1 inline size-3.5" aria-hidden />
            {e.carpeta_nombre ?? "Carpeta"} · revisada {haceCuanto(e.carpeta_revisada_en)} ({fechaHora(e.carpeta_revisada_en)}). Se vuelve a revisar sola cada noche.</p>
        )}
        {e.carpeta_error && <Aviso tono="critico" titulo="No se pudo leer la carpeta">{e.carpeta_error}</Aviso>}
        {aviso && <Aviso tono={aviso.ok ? "ok" : "critico"}>{aviso.mensaje}</Aviso>}

        {r ? (
          <div className="grid gap-5 text-sm md:grid-cols-3">
            <section>
              <h3 className="mb-1 text-[13px] font-medium text-texto-2">Subclientes ({r.subclientes.length})</h3>
              <ul className="space-y-1">{r.subclientes.map((s) => (
                <li key={s.cliente_id}>{s.subcliente} <span className="text-xs text-texto-3">← {s.carpeta}</span>{" "}
                  {s.enlace === "manual" && <Insignia>enlace propio</Insignia>}</li>))}</ul>
              {r.carpetas_sin_subcliente.length > 0 && <p className="mt-2 text-xs text-alerta">Carpetas sin subcliente: {r.carpetas_sin_subcliente.join(", ")}</p>}
            </section>
            <section>
              <h3 className="mb-1 text-[13px] font-medium text-texto-2">Aliados bancarios ({r.aliados.length})</h3>
              <ul className="space-y-1">{r.aliados.map((a) => <li key={a.relacion_id}>{a.aliado} <span className="text-xs text-texto-3">← {a.carpeta} · {a.archivos} archivos</span></li>)}</ul>
              {r.aliados_sin_carpeta.length > 0 && <p className="mt-2 text-xs text-texto-3">Sin carpeta: {r.aliados_sin_carpeta.join(", ")}</p>}
              {r.carpetas_sin_aliado.length > 0 && <p className="mt-1 text-xs text-alerta">Carpetas que no coinciden con ningún aliado: {r.carpetas_sin_aliado.join(", ")}</p>}
            </section>
            <section>
              <h3 className="mb-1 text-[13px] font-medium text-texto-2">Requerimientos con carpeta ({r.requerimientos})</h3>
              <p className="text-xs text-texto-3">La carpeta debe empezar por su consecutivo, por ejemplo «REQ-2026-001 - Asunto».</p>
              {r.carpetas_req_sin_coincidir.length > 0 && <p className="mt-2 text-xs text-alerta">Sin requerimiento registrado: {r.carpetas_req_sin_coincidir.join(", ")}</p>}
            </section>
          </div>
        ) : (
          <div><p className="mb-1 text-xs text-texto-3">Estructura que reconoce la plataforma:</p>
            <pre className="overflow-x-auto rounded-lg border border-borde bg-panel-2 p-3 text-xs text-texto-2">{ESTRUCTURA}</pre></div>
        )}
      </div>
    </Tarjeta>
  );
}
