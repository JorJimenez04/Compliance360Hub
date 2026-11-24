"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, Circle, ExternalLink, FolderOpen, RefreshCw, Save } from "lucide-react";
import { Aviso, Boton, Entrada, Esqueleto, Etiqueta, Selector, Tarjeta, TituloTarjeta } from "@/components/ui/basicos";
import { enviar, ErrorApi } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";
import { fechaHora, haceCuanto } from "@/lib/formato";
import { cn } from "@/lib/cn";

export interface ArchivoDoc {
  id: number; id_beneficiario: string | null; codigo: string | null; nombre_archivo: string; ruta: string | null;
  web_url: string | null; tamano: number | null; modificado_en: string | null; asignacion: "auto" | "manual";
  asignado_por: string | null;
}
export interface RequisitoDoc { codigo: string; nombre: string; cargado: boolean; archivos: ArchivoDoc[] }
interface EstadoPropio {
  carpeta: { enlace: string | null; nombre: string | null; revisada_en: string | null; error: string | null };
  requisitos: RequisitoDoc[]; listo_para_banco: boolean; faltan: string[]; otros_archivos: ArchivoDoc[];
  documentos: Record<string, string>;
}

/** Llama a «Revisar OneDrive» y devuelve un mensaje para el usuario. */
export async function revisarCarpeta(clienteId: number): Promise<{ ok: boolean; mensaje: string }> {
  try {
    const r = await enviar<{ archivos_propios: number; carpetas_beneficiarios: number; archivos_beneficiarios: number; retirados: number }>(
      `/api/clientes/${clienteId}/documentacion/revisar`, {});
    return { ok: true, mensaje: `Carpeta revisada: ${r.archivos_propios} archivos propios y ${r.archivos_beneficiarios} de ${r.carpetas_beneficiarios} carpetas de beneficiarios`
      + (r.retirados ? `; ${r.retirados} archivos ya no están en OneDrive.` : ".") };
  } catch (e) {
    return { ok: false, mensaje: e instanceof ErrorApi ? e.message : "No se pudo revisar la carpeta." };
  }
}

export function EnlaceArchivo({ a }: { a: ArchivoDoc }) {
  return a.web_url
    ? <a href={a.web_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-acento hover:underline">
        {a.nombre_archivo}<ExternalLink className="size-3" aria-hidden /></a>
    : <span>{a.nombre_archivo}</span>;
}

export function AsignarArchivo({ a, documentos, permitidos, onHecho }: {
  a: ArchivoDoc; documentos: Record<string, string>; permitidos?: string[]; onHecho: () => void;
}) {
  const [trabajando, setTrabajando] = useState(false);
  const opciones = Object.entries(documentos).filter(([c]) => !permitidos || permitidos.includes(c));
  return (
    <Selector aria-label={`Tipo de documento de ${a.nombre_archivo}`} className="h-8 w-60 text-xs" disabled={trabajando}
      value={a.codigo ?? ""} onChange={async (e) => {
        setTrabajando(true);
        try { await enviar(`/api/documentos/${a.id}`, { codigo: e.target.value || null }, "PATCH"); onHecho(); }
        finally { setTrabajando(false); }
      }}>
      <option value="">Sin asignar</option>
      {opciones.map(([c, n]) => <option key={c} value={c}>{n}</option>)}
    </Selector>
  );
}

export function Checklist({ requisitos, documentos, onHecho }: { requisitos: RequisitoDoc[]; documentos: Record<string, string>; onHecho: () => void }) {
  return (
    <ul className="divide-y divide-borde/70">
      {requisitos.map((r) => (
        <li key={r.codigo} className="flex flex-wrap items-start gap-3 py-2.5">
          {r.cargado ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-ok" aria-label="Cargado" />
            : <Circle className="mt-0.5 size-4 shrink-0 text-texto-3" aria-label="Falta" />}
          <span className={cn("w-72 text-sm", r.cargado ? "text-texto" : "text-texto-2")}>{r.nombre}</span>
          <div className="flex-1 space-y-1 text-[13px]">
            {!r.archivos.length ? <span className="text-alerta">Falta</span> : r.archivos.map((a) => (
              <div key={a.id} className="flex flex-wrap items-center gap-2">
                <EnlaceArchivo a={a} />
                <span className="text-xs text-texto-3">{a.ruta}{a.asignacion === "manual" && " · asignado a mano"}</span>
                <AsignarArchivo a={a} documentos={documentos} onHecho={onHecho} />
              </div>
            ))}
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Documentación corporativa del cliente, leída de su carpeta en OneDrive. */
export default function DocumentacionPropia({ clienteId, enlace, onGuardado }: { clienteId: number; enlace: string | null; onGuardado: () => void }) {
  const estado = useDatos<EstadoPropio>(`/api/clientes/${clienteId}/documentacion`);
  const [url, setUrl] = useState(enlace ?? "");
  useEffect(() => setUrl(enlace ?? ""), [enlace]);
  const [trabajando, setTrabajando] = useState<"guardar" | "revisar" | null>(null);
  const [aviso, setAviso] = useState<{ ok: boolean; mensaje: string } | null>(null);

  async function guardar() {
    setTrabajando("guardar"); setAviso(null);
    try {
      await enviar(`/api/clientes/${clienteId}`, { carpeta_onedrive: url.trim() || null }, "PATCH");
      onGuardado();
      if (url.trim()) setAviso(await revisarCarpeta(clienteId));
      await estado.recargar();
    } catch (e) { setAviso({ ok: false, mensaje: e instanceof ErrorApi ? e.message : "No se pudo guardar." }); }
    finally { setTrabajando(null); }
  }
  async function revisar() {
    setTrabajando("revisar"); setAviso(null);
    setAviso(await revisarCarpeta(clienteId));
    await estado.recargar(); setTrabajando(null);
  }

  const e = estado.datos;
  return (
    <div className="space-y-5">
      <Tarjeta>
        <TituloTarjeta titulo="Carpeta del cliente en OneDrive"
          descripcion="Pegue el enlace de su carpeta. Dentro, la plataforma lee «Documentación corporativa» y «Beneficiarios». Se revisa con cada sincronización o con el botón."
          accion={e?.carpeta.enlace && <Boton className="whitespace-nowrap" cargando={trabajando === "revisar"} onClick={revisar}><RefreshCw className="size-4" aria-hidden />Revisar OneDrive</Boton>} />
        <div className="space-y-3 px-5 pb-5 pt-3">
          <div className="flex flex-wrap items-end gap-2">
            <div className="min-w-[320px] flex-1"><Etiqueta htmlFor="carpeta">Enlace de la carpeta</Etiqueta>
              <Entrada id="carpeta" placeholder="https://…sharepoint.com/:f:/g/personal/…" value={url} onChange={(ev) => setUrl(ev.target.value)} /></div>
            <Boton variante="primario" cargando={trabajando === "guardar"} disabled={(url.trim() || null) === (enlace || null)} onClick={guardar}>
              <Save className="size-4" aria-hidden />Guardar</Boton>
          </div>
          {e?.carpeta.revisada_en && !e.carpeta.error && (
            <p className="text-xs text-texto-3"><FolderOpen className="mr-1 inline size-3.5" aria-hidden />
              {e.carpeta.nombre ?? "Carpeta"} · revisada {haceCuanto(e.carpeta.revisada_en)} ({fechaHora(e.carpeta.revisada_en)})</p>
          )}
          {e?.carpeta.error && <Aviso tono="critico" titulo="No se pudo leer la carpeta">{e.carpeta.error}</Aviso>}
          {aviso && <Aviso tono={aviso.ok ? "ok" : "critico"}>{aviso.mensaje}</Aviso>}
        </div>
      </Tarjeta>

      {!e ? <Esqueleto className="h-64" /> : (
        <>
          <Tarjeta>
            <TituloTarjeta titulo="Documentación corporativa"
              descripcion="Cada archivo se reconoce por su nombre. Si alguno no se reconoce, asígnelo a mano: queda así aunque se vuelva a revisar."
              accion={<span className={cn("inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm font-medium",
                e.listo_para_banco ? "border-ok/40 bg-ok/10 text-ok" : "border-alerta/40 bg-alerta/10 text-alerta")}>
                <span className={cn("size-2.5 rounded-full", e.listo_para_banco ? "bg-ok" : "bg-alerta")} />
                {e.listo_para_banco ? "Listo para banco" : `Faltan ${e.faltan.length}`}</span>} />
            <div className="px-5 pb-4 pt-1">
              <Checklist requisitos={e.requisitos} documentos={e.documentos} onHecho={estado.recargar} />
            </div>
          </Tarjeta>
          {e.otros_archivos.length > 0 && (
            <Tarjeta>
              <TituloTarjeta titulo={`Otros archivos en la carpeta (${e.otros_archivos.length})`}
                descripcion="No se reconocieron como documentos exigidos. Asigne el tipo si corresponde a alguno." />
              <ul className="divide-y divide-borde/70 px-5 pb-4 pt-1">
                {e.otros_archivos.map((a) => (
                  <li key={a.id} className="flex flex-wrap items-center gap-3 py-2 text-[13px]">
                    <EnlaceArchivo a={a} /><span className="flex-1 text-xs text-texto-3">{a.ruta}</span>
                    <AsignarArchivo a={a} documentos={e.documentos} onHecho={estado.recargar} />
                  </li>
                ))}
              </ul>
            </Tarjeta>
          )}
        </>
      )}
    </div>
  );
}
