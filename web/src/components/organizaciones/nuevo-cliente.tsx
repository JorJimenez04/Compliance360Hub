"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Save, X } from "lucide-react";
import { Aviso, Boton, Entrada, Esqueleto, Etiqueta, Selector, Tarjeta, TituloTarjeta } from "@/components/ui/basicos";
import { enviar, ErrorApi } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";
import type { Catalogo } from "@/lib/tipos";
import ActividadYModelos from "@/components/cumplimiento/actividades";
import { riesgoDe } from "@/components/cumplimiento/selector-modelos";

const VACIO = { razon_social: "", nit: "", tipo_persona: "juridica", estado: "Prospecto", nivel_riesgo: "Sin calificar",
  pais_constitucion: "Colombia", sitio_web: "", notas: "", actividades_ciiu: [] as string[], modelos_negocio: [] as string[] };

/** Alta manual de un cliente: el equipo diligencia su ficha KYC/KYB con las actividades del RUT. */
export default function NuevoCliente({ organizacionId, onCerrar }: { organizacionId: number; onCerrar: () => void }) {
  const router = useRouter();
  const cat = useDatos<Catalogo>("/api/catalogo");
  const [f, setF] = useState(VACIO);
  const [guardando, setGuardando] = useState(false);
  const [fallo, setFallo] = useState<string | null>(null);
  const poner = (c: Partial<typeof VACIO>) => setF({ ...f, ...c });

  async function crear(e: React.FormEvent) {
    e.preventDefault();
    setGuardando(true); setFallo(null);
    try {
      const cuerpo = Object.fromEntries(Object.entries(f).filter(([, v]) => v !== ""));
      const r = await enviar<{ id: number }>(`/api/organizaciones/${organizacionId}/clientes`, cuerpo);
      router.push(`/organizaciones/${organizacionId}/clientes/${r.id}?tab=perfil`);
    } catch (err) {
      setFallo(err instanceof ErrorApi ? err.message : "No se pudo crear el cliente.");
      setGuardando(false);
    }
  }

  if (!cat.datos) return <Esqueleto className="h-64" />;
  const sugerido = riesgoDe(cat.datos.modelos, f.modelos_negocio);

  return (
    <Tarjeta className="border-acento/40">
      <form onSubmit={crear}>
        <TituloTarjeta titulo="Nuevo cliente" descripcion="Diligencie la ficha con los datos del RUT. Al guardar se abre su expediente para registrar el perfil transaccional declarado."
          accion={<div className="flex gap-2">
            <Boton type="button" onClick={onCerrar}><X className="size-4" aria-hidden />Cancelar</Boton>
            <Boton type="submit" variante="primario" cargando={guardando} disabled={f.razon_social.trim().length < 2}>
              <Save className="size-4" aria-hidden />Crear cliente</Boton>
          </div>} />
        <div className="space-y-5 px-5 pb-5 pt-3">
          {fallo && <Aviso tono="critico">{fallo}</Aviso>}
          <div className="grid gap-4 md:grid-cols-3">
            <div><Etiqueta htmlFor="n-rs">Razón social *</Etiqueta>
              <Entrada id="n-rs" required minLength={2} maxLength={200} value={f.razon_social} onChange={(e) => poner({ razon_social: e.target.value })} /></div>
            <div><Etiqueta htmlFor="n-nit">NIT o documento</Etiqueta>
              <Entrada id="n-nit" maxLength={30} placeholder="Ej.: 901419688-5" value={f.nit} onChange={(e) => poner({ nit: e.target.value })} /></div>
            <div><Etiqueta htmlFor="n-tp">Tipo de persona</Etiqueta>
              <Selector id="n-tp" value={f.tipo_persona} onChange={(e) => poner({ tipo_persona: e.target.value })}>
                <option value="juridica">Persona jurídica</option><option value="natural">Persona natural</option></Selector></div>
            <div><Etiqueta htmlFor="n-riesgo">Nivel de riesgo</Etiqueta>
              <Selector id="n-riesgo" value={f.nivel_riesgo} onChange={(e) => poner({ nivel_riesgo: e.target.value })}>
                {["Sin calificar", "Alto", "Medio", "Bajo"].map((n) => <option key={n} value={n}>{n}</option>)}</Selector>
              {sugerido && <p className="mt-1 text-xs text-texto-3">Sugerido por sus modelos: {sugerido}
                {sugerido !== f.nivel_riesgo && <button type="button" className="ml-2 text-acento hover:underline" onClick={() => poner({ nivel_riesgo: sugerido })}>Usar</button>}</p>}</div>
            <div><Etiqueta htmlFor="n-est">Estado</Etiqueta>
              <Selector id="n-est" value={f.estado} onChange={(e) => poner({ estado: e.target.value })}>
                {["Prospecto", "Activo"].map((n) => <option key={n} value={n}>{n}</option>)}</Selector></div>
            <div><Etiqueta htmlFor="n-pais">País de constitución</Etiqueta>
              <Entrada id="n-pais" maxLength={80} value={f.pais_constitucion} onChange={(e) => poner({ pais_constitucion: e.target.value })} /></div>
            <div className="md:col-span-3"><Etiqueta htmlFor="n-web">Sitio web</Etiqueta>
              <Entrada id="n-web" maxLength={200} value={f.sitio_web} onChange={(e) => poner({ sitio_web: e.target.value })} /></div>
          </div>
          <ActividadYModelos modelos={cat.datos.modelos} documentos={cat.datos.documentos} actividades={f.actividades_ciiu} idBase="n-ciiu"
            modelosNegocio={f.modelos_negocio} onCambio={({ actividades, modelos }) => poner({ actividades_ciiu: actividades, modelos_negocio: modelos })} />
          <div><Etiqueta htmlFor="n-notas">Notas internas</Etiqueta>
            <textarea id="n-notas" rows={2} maxLength={2000} value={f.notas} onChange={(e) => poner({ notas: e.target.value })}
              className="w-full rounded-lg border border-borde-fuerte bg-fondo px-3 py-2 text-sm text-texto focus:border-acento focus:outline-none" /></div>
        </div>
      </form>
    </Tarjeta>
  );
}
