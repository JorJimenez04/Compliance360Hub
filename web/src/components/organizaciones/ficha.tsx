"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowLeft, Save } from "lucide-react";
import { Aviso, Boton, Entrada, Esqueleto, Etiqueta, Insignia, Selector, Tarjeta, TituloTarjeta, tonoRiesgo } from "@/components/ui/basicos";
import { enviar, ErrorApi } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";
import { useSesion } from "@/lib/sesion";
import type { Catalogo, Ficha, Paquete } from "@/lib/tipos";
import { cn } from "@/lib/cn";
import SelectorModelos from "@/components/cumplimiento/selector-modelos";
import VistaPaquete from "@/components/cumplimiento/paquete";

type Edicion = Pick<Ficha, "tipo_persona" | "servicios" | "modelos_negocio" | "regimen" | "nivel_riesgo" | "fecha_calificacion"
  | "proxima_revision" | "oficial_principal_id" | "oficial_suplente" | "fecha_designacion" | "acta_designacion">;

const CAMPOS: (keyof Edicion)[] = ["tipo_persona", "servicios", "modelos_negocio", "regimen", "nivel_riesgo",
  "fecha_calificacion", "proxima_revision", "oficial_principal_id", "oficial_suplente", "fecha_designacion", "acta_designacion"];

export default function FichaOrganizacion({ id }: { id: number }) {
  const { rol } = useSesion();
  const puedeEditar = rol === "super_admin";
  const ficha = useDatos<Ficha>(`/api/organizaciones/${id}`);
  const cat = useDatos<Catalogo>("/api/catalogo");
  const [version, setVersion] = useState(0);
  const paquete = useDatos<Paquete>(`/api/organizaciones/${id}/paquete?v=${version}`);
  const [ed, setEd] = useState<Edicion | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [fallo, setFallo] = useState<string | null>(null);
  const [ok, setOk] = useState(false);

  useEffect(() => {
    if (ficha.datos) setEd(Object.fromEntries(CAMPOS.map((c) => [c, ficha.datos![c]])) as unknown as Edicion);
  }, [ficha.datos]);

  if (ficha.error) return <Aviso tono="critico" icono={<AlertTriangle className="size-4" />}>{ficha.error}</Aviso>;
  if (!ficha.datos || !cat.datos || !ed) return <Esqueleto className="h-96" />;
  const f = ficha.datos, c = cat.datos;
  const poner = (cambios: Partial<Edicion>) => { setEd({ ...ed, ...cambios }); setOk(false); };

  async function guardar() {
    setGuardando(true); setFallo(null); setOk(false);
    try {
      await enviar(`/api/organizaciones/${id}`, { ...ed, oficial_suplente: ed!.oficial_suplente || null,
        acta_designacion: ed!.acta_designacion || null }, "PATCH");
      await ficha.recargar(); setVersion((v) => v + 1); setOk(true);
    } catch (e) { setFallo(e instanceof ErrorApi ? e.message : "No se pudo guardar."); }
    finally { setGuardando(false); }
  }

  const servicioMarcado = (s: string) => ed.servicios.includes(s);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <Link href="/organizaciones" className="mb-2 inline-flex items-center gap-1.5 text-sm text-texto-3 hover:text-texto">
            <ArrowLeft className="size-4" aria-hidden />Organizaciones</Link>
          <h1 className="text-2xl font-semibold tracking-tight">{f.nombre}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-texto-3">
            {f.nit && <span>NIT {f.nit}</span>}
            <Insignia tono={tonoRiesgo(f.nivel_riesgo)}>Riesgo {f.nivel_riesgo}</Insignia>
            {f.riesgo_sugerido && f.nivel_riesgo !== f.riesgo_sugerido && <span>Sugerido por sus modelos: {f.riesgo_sugerido}</span>}
            {!f.activa && <Insignia>Inactiva</Insignia>}
          </div>
        </div>
        {puedeEditar && <Boton variante="primario" cargando={guardando} onClick={guardar}><Save className="size-4" aria-hidden />Guardar ficha</Boton>}
      </div>

      {fallo && <Aviso tono="critico" icono={<AlertTriangle className="size-4" />}>{fallo}</Aviso>}
      {ok && <Aviso tono="ok">Ficha guardada. El paquete de vinculación se actualizó.</Aviso>}

      <div className="grid gap-6 xl:grid-cols-2">
        <Tarjeta>
          <TituloTarjeta titulo="Servicios contratados" descripcion="Activan los módulos que verá esta organización." />
          <div className="grid gap-2 px-5 pb-5 pt-3 sm:grid-cols-2">
            {c.servicios.map((s) => (
              <label key={s.codigo} title={s.descripcion}
                className={cn("flex cursor-pointer items-start gap-2.5 rounded-lg border px-3 py-2 text-sm",
                  servicioMarcado(s.codigo) ? "border-acento bg-acento-tenue" : "border-borde-fuerte", !puedeEditar && "pointer-events-none")}>
                <input type="checkbox" className="mt-0.5 accent-[var(--color-acento)]" disabled={!puedeEditar} checked={servicioMarcado(s.codigo)}
                  onChange={() => poner({ servicios: servicioMarcado(s.codigo) ? ed.servicios.filter((x) => x !== s.codigo) : [...ed.servicios, s.codigo] })} />
                <span><span className="font-medium">{s.nombre}</span><span className="mt-0.5 block text-xs text-texto-3">{s.descripcion}</span></span>
              </label>
            ))}
          </div>
        </Tarjeta>

        <div className="space-y-6">
          <Tarjeta>
            <TituloTarjeta titulo="Régimen y riesgo" />
            <div className="grid gap-4 px-5 pb-5 pt-3 sm:grid-cols-2">
              <div className="sm:col-span-2"><Etiqueta htmlFor="f-regimen">Régimen / supervisor</Etiqueta>
                <Selector id="f-regimen" disabled={!puedeEditar} value={ed.regimen ?? ""} onChange={(e) => poner({ regimen: e.target.value || null })}>
                  <option value="">Sin definir</option>
                  {c.regimenes.map((r) => <option key={r.codigo} value={r.codigo}>{r.nombre}</option>)}
                </Selector></div>
              <div><Etiqueta htmlFor="f-nivel">Nivel de riesgo</Etiqueta>
                <Selector id="f-nivel" disabled={!puedeEditar} value={ed.nivel_riesgo} onChange={(e) => poner({ nivel_riesgo: e.target.value as Edicion["nivel_riesgo"] })}>
                  {["Sin calificar", ...c.niveles].map((n) => <option key={n} value={n}>{n}</option>)}
                </Selector></div>
              <div><Etiqueta htmlFor="f-persona">Tipo de persona</Etiqueta>
                <Selector id="f-persona" disabled={!puedeEditar} value={ed.tipo_persona} onChange={(e) => poner({ tipo_persona: e.target.value as Edicion["tipo_persona"] })}>
                  <option value="juridica">Persona jurídica</option><option value="natural">Persona natural</option>
                </Selector></div>
              <div><Etiqueta htmlFor="f-calif">Fecha de calificación</Etiqueta>
                <Entrada id="f-calif" type="date" disabled={!puedeEditar} value={ed.fecha_calificacion ?? ""} onChange={(e) => poner({ fecha_calificacion: e.target.value || null })} /></div>
              <div><Etiqueta htmlFor="f-rev">Próxima revisión</Etiqueta>
                <Entrada id="f-rev" type="date" disabled={!puedeEditar} value={ed.proxima_revision ?? ""} onChange={(e) => poner({ proxima_revision: e.target.value || null })} /></div>
            </div>
          </Tarjeta>

          <Tarjeta>
            <TituloTarjeta titulo="Oficial de cumplimiento" />
            <div className="grid gap-4 px-5 pb-5 pt-3 sm:grid-cols-2">
              <div><Etiqueta htmlFor="f-oficial">Principal</Etiqueta>
                <Selector id="f-oficial" disabled={!puedeEditar} value={ed.oficial_principal_id ?? ""} onChange={(e) => poner({ oficial_principal_id: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">Sin designar</option>
                  {f.oficiales_disponibles.map((o) => <option key={o.id} value={o.id}>{o.nombre}</option>)}
                </Selector></div>
              <div><Etiqueta htmlFor="f-suplente">Suplente</Etiqueta>
                <Entrada id="f-suplente" disabled={!puedeEditar} maxLength={200} placeholder="Nombre y documento" value={ed.oficial_suplente ?? ""} onChange={(e) => poner({ oficial_suplente: e.target.value })} /></div>
              <div><Etiqueta htmlFor="f-fdes">Fecha de designación</Etiqueta>
                <Entrada id="f-fdes" type="date" disabled={!puedeEditar} value={ed.fecha_designacion ?? ""} onChange={(e) => poner({ fecha_designacion: e.target.value || null })} /></div>
              <div><Etiqueta htmlFor="f-acta">Acta de designación</Etiqueta>
                <Entrada id="f-acta" disabled={!puedeEditar} maxLength={200} placeholder="Ej.: Acta 15 de junta directiva" value={ed.acta_designacion ?? ""} onChange={(e) => poner({ acta_designacion: e.target.value })} /></div>
            </div>
          </Tarjeta>
        </div>
      </div>

      <Tarjeta>
        <TituloTarjeta titulo="Modelos de negocio" descripcion="Definen el riesgo sugerido, la documentación exigida y las señales de alerta del monitoreo." />
        <div className="px-5 pb-5 pt-3">
          <SelectorModelos modelos={c.modelos} valor={ed.modelos_negocio} onCambio={(v) => poner({ modelos_negocio: v })} disabled={!puedeEditar} />
        </div>
      </Tarjeta>

      <div>
        <h2 className="mb-3 text-lg font-semibold tracking-tight">Paquete de vinculación</h2>
        {!f.modelos_negocio.length ? <p className="text-sm text-texto-3">Defina al menos un modelo de negocio y guarde la ficha para generar el paquete.</p>
          : !paquete.datos ? <Esqueleto className="h-64" />
          : <VistaPaquete paquete={paquete.datos} modelos={c.modelos} />}
      </div>
    </div>
  );
}
