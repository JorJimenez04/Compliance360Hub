"use client";

import { useState } from "react";
import { AlertTriangle } from "lucide-react";
import { Aviso, Esqueleto, Etiqueta, Selector, Tarjeta, TituloTarjeta } from "@/components/ui/basicos";
import { useDatos } from "@/lib/useDatos";
import { query } from "@/lib/api";
import type { Catalogo, Paquete } from "@/lib/tipos";
import SelectorModelos from "./selector-modelos";
import VistaPaquete from "./paquete";

/** Para un cliente potencial: elija su modelo de negocio y vea qué documentación se le pedirá. */
export default function CatalogoCumplimiento() {
  const cat = useDatos<Catalogo>("/api/catalogo");
  const [modelos, setModelos] = useState<string[]>([]);
  const [nivel, setNivel] = useState("");
  const [persona, setPersona] = useState("juridica");
  const [regimen, setRegimen] = useState("");
  const paquete = useDatos<Paquete>(modelos.length
    ? `/api/catalogo/paquete${query({ modelos, nivel, tipo_persona: persona, regimen })}` : null);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Catálogo de cumplimiento</h1>
        <p className="mt-1 text-sm text-texto-3">
          Documentación estandarizada para vincular un cliente nuevo según su modelo de negocio y su nivel de riesgo.
          Es una referencia: valide cada requisito frente a la norma vigente de su supervisor.
        </p>
      </div>
      {cat.error && <Aviso tono="critico" icono={<AlertTriangle className="size-4" />}>{cat.error}</Aviso>}
      {!cat.datos ? <Esqueleto className="h-96" /> : (
        <>
          <Tarjeta>
            <TituloTarjeta titulo="Cliente potencial" descripcion={`${cat.datos.modelos.length} modelos de negocio en ${new Set(cat.datos.modelos.map((m) => m.grupo)).size} grupos. Pase el cursor sobre uno para ver por qué tiene ese riesgo.`} />
            <div className="space-y-5 px-5 pb-5 pt-3">
              <SelectorModelos modelos={cat.datos.modelos} valor={modelos} onCambio={setModelos} />
              <div className="grid gap-4 md:grid-cols-3">
                <div><Etiqueta htmlFor="c-nivel">Nivel de riesgo</Etiqueta>
                  <Selector id="c-nivel" value={nivel} onChange={(e) => setNivel(e.target.value)}>
                    <option value="">Sugerido por el modelo</option>
                    {cat.datos.niveles.map((n) => <option key={n} value={n}>{n}</option>)}
                  </Selector></div>
                <div><Etiqueta htmlFor="c-persona">Tipo de persona</Etiqueta>
                  <Selector id="c-persona" value={persona} onChange={(e) => setPersona(e.target.value)}>
                    <option value="juridica">Persona jurídica</option><option value="natural">Persona natural</option>
                  </Selector></div>
                <div><Etiqueta htmlFor="c-regimen">Régimen</Etiqueta>
                  <Selector id="c-regimen" value={regimen} onChange={(e) => setRegimen(e.target.value)}>
                    <option value="">Sin definir</option>
                    {cat.datos.regimenes.map((r) => <option key={r.codigo} value={r.codigo}>{r.nombre}</option>)}
                  </Selector></div>
              </div>
            </div>
          </Tarjeta>
          {!modelos.length ? <p className="text-sm text-texto-3">Elija al menos un modelo de negocio para ver el paquete de vinculación.</p>
            : paquete.error ? <Aviso tono="critico">{paquete.error}</Aviso>
            : !paquete.datos ? <Esqueleto className="h-64" />
            : <VistaPaquete paquete={paquete.datos} modelos={cat.datos.modelos} />}
        </>
      )}
    </div>
  );
}
