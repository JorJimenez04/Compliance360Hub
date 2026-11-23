"use client";

import { AlertTriangle, FileText, Landmark } from "lucide-react";
import { Insignia, Tarjeta, TituloTarjeta, tonoRiesgo } from "@/components/ui/basicos";
import type { ModeloCat, Paquete } from "@/lib/tipos";

const CARPETAS: Record<string, string> = {
  "01_KYC": "Identidad, existencia y programa (KYC/KYB)",
  "02_Screening": "Listas, sanciones, PEP y medios adversos",
  "03_Contratos": "Contractual",
  "04_Fuente_de_fondos": "Fuente de fondos y perfil financiero",
  "05_Verificacion_actividad": "Verificación de la actividad",
  "06_Perfil_transaccional": "Perfil transaccional",
};
const APORTA: Record<string, string> = { cliente: "Cliente", oficial: "Oficial", ambos: "Cliente y oficial" };

function vigencia(meses: number | null) {
  if (meses === null) return "No vence";
  return meses % 12 === 0 ? `${meses / 12} ${meses === 12 ? "año" : "años"}` : `${meses} meses`;
}

/** Paquete de vinculación: lo que se le exige a un cliente según sus modelos, su nivel y su tipo de persona. */
export default function VistaPaquete({ paquete, modelos }: { paquete: Paquete; modelos: ModeloCat[] }) {
  const nombreModelo = (c: string) => modelos.find((m) => m.codigo === c)?.nombre ?? c;
  const porCarpeta = Object.keys(CARPETAS)
    .map((c) => ({ carpeta: c, docs: paquete.documentos.filter((d) => d.carpeta === c) }))
    .filter((g) => g.docs.length);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Insignia tono={tonoRiesgo(paquete.nivel)}>Riesgo {paquete.nivel}{paquete.nivel_es_provisional ? " (provisional)" : ""}</Insignia>
        <Insignia>{paquete.tipo_persona === "juridica" ? "Persona jurídica" : "Persona natural"}</Insignia>
        <Insignia>{paquete.documentos.length} requisitos</Insignia>
        {paquete.monitoreo_sugerido.map((m) => <Insignia key={m} tono="acento">Monitoreo {m}</Insignia>)}
      </div>

      {paquete.nivel_es_provisional && (
        <p className="text-sm text-alerta">
          La organización aún no tiene calificación de riesgo: el paquete usa el nivel sugerido por sus modelos de negocio.
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {paquete.regimen && (
          <Tarjeta className="pb-4">
            <TituloTarjeta titulo={paquete.regimen.nombre} descripcion={`${paquete.regimen.supervisor} · ${paquete.regimen.sistema}`}
              accion={<Landmark className="size-5 text-texto-3" aria-hidden />} />
            <div className="px-5 pt-3 text-sm">
              <p className="mb-1.5 text-[13px] font-medium text-texto-2">Reportes a la UIAF</p>
              {paquete.regimen.reportes_uiaf.length ? (
                <ul className="list-disc space-y-0.5 pl-5 text-texto-2">{paquete.regimen.reportes_uiaf.map((r) => <li key={r}>{r}</li>)}</ul>
              ) : <p className="text-texto-3">No reporta a la UIAF.</p>}
              {paquete.regimen.nota && <p className="mt-2 text-xs text-texto-3">{paquete.regimen.nota}</p>}
            </div>
          </Tarjeta>
        )}
        {paquete.senales_alerta.length > 0 && (
          <Tarjeta className="pb-4">
            <TituloTarjeta titulo="Señales de alerta a monitorear" descripcion="Según los modelos de negocio elegidos."
              accion={<AlertTriangle className="size-5 text-texto-3" aria-hidden />} />
            <ul className="list-disc space-y-0.5 px-5 pl-10 pt-3 text-sm text-texto-2">
              {paquete.senales_alerta.map((s) => <li key={s}>{s}</li>)}
            </ul>
          </Tarjeta>
        )}
      </div>

      <Tarjeta>
        <TituloTarjeta titulo="Documentación e información requerida"
          descripcion="Agrupada como quedará en la carpeta del cliente. La vigencia depende del nivel de riesgo."
          accion={<FileText className="size-5 text-texto-3" aria-hidden />} />
        <div className="overflow-x-auto px-2 pb-3 pt-2">
          <table className="w-full min-w-[760px] text-[13px]">
            <thead><tr className="text-left text-texto-3">
              <th className="px-3 py-2 font-medium">Documento</th><th className="px-3 py-2 font-medium">Lo aporta</th>
              <th className="px-3 py-2 font-medium">Vigencia</th><th className="px-3 py-2 font-medium">Exigido por</th></tr></thead>
            {porCarpeta.map((g) => (
              <tbody key={g.carpeta}>
                <tr><td colSpan={4} className="px-3 pb-1 pt-4 text-[11px] font-semibold uppercase tracking-wider text-texto-3">
                  {g.carpeta} · {CARPETAS[g.carpeta]}</td></tr>
                {g.docs.map((d) => (
                  <tr key={d.codigo} className="border-t border-borde/70 align-top">
                    <td className="px-3 py-2.5"><p>{d.nombre}</p>{d.nota && <p className="mt-0.5 text-xs text-texto-3">{d.nota}</p>}</td>
                    <td className="px-3 py-2.5 text-texto-2">{APORTA[d.aporta]}</td>
                    <td className="px-3 py-2.5 text-texto-2">{vigencia(d.vigencia_meses)}</td>
                    <td className="px-3 py-2.5 text-texto-3">{d.origen.map((o) => (o === "base" ? "Base" : nombreModelo(o))).join(" · ")}</td>
                  </tr>
                ))}
              </tbody>
            ))}
          </table>
        </div>
      </Tarjeta>
    </div>
  );
}
