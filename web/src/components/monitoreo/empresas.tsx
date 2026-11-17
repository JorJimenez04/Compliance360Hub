"use client";

import { useState } from "react";
import { AlertTriangle, Building2 } from "lucide-react";
import { Aviso, Esqueleto, Insignia, Selector, Tarjeta, TituloTarjeta, Vacio, tonoRiesgo } from "@/components/ui/basicos";
import { enviar } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";
import { entero } from "@/lib/formato";
import type { ClienteOpcion, Empresa } from "@/lib/tipos";
import { cn } from "@/lib/cn";

export default function VistaEmpresas({ alCambiar }: { alCambiar: () => void }) {
  const { datos, error, recargar } = useDatos<{ empresas: Empresa[]; clientes: ClienteOpcion[] }>("/api/monitoreo/empresas");
  const [guardando, setGuardando] = useState<number | null>(null);
  const [fallo, setFallo] = useState<string | null>(null);

  async function cambiar(id: number, cambio: Record<string, unknown>) {
    setGuardando(id); setFallo(null);
    try { await enviar(`/api/monitoreo/empresas/${id}`, cambio, "PATCH"); await recargar(); alCambiar(); }
    catch (e) { setFallo((e as Error).message); }
    finally { setGuardando(null); }
  }

  return (
    <Tarjeta>
      <TituloTarjeta titulo="Empresas de AdamoPay"
        descripcion="Enlace cada empresa con su cliente para heredar el NIT y el nivel de riesgo. Las inactivas no aparecen en el tablero." />
      {(error || fallo) && <div className="px-5 pt-4"><Aviso tono="critico" icono={<AlertTriangle className="size-4" />}>{error ?? fallo}</Aviso></div>}
      {!datos ? <div className="space-y-2 p-5">{[0, 1, 2].map((i) => <Esqueleto key={i} className="h-12" />)}</div>
        : datos.empresas.length === 0 ? <Vacio icono={<Building2 className="size-8" />} titulo="No hay empresas" texto="Se crean solas al cargar el primer historial de cada una." />
        : (
          <div className="overflow-x-auto px-2 pb-3 pt-3">
            <table className="w-full min-w-[820px] text-[13px]">
              <thead><tr className="text-left text-texto-3">
                <th className="px-3 py-2 font-medium">Empresa (carpeta)</th><th className="px-3 py-2 text-right font-medium">Movimientos</th>
                <th className="px-3 py-2 font-medium">Cliente enlazado</th><th className="px-3 py-2 font-medium">Riesgo</th>
                <th className="px-3 py-2 font-medium">Estado</th></tr></thead>
              <tbody>
                {datos.empresas.map((e) => (
                  <tr key={e.id} className={cn("border-t border-borde/70", guardando === e.id && "opacity-60")}>
                    <td className="px-3 py-3 font-medium">{e.nombre_reporte}</td>
                    <td className="cifra px-3 py-3 text-right">{entero(e.transacciones ?? 0)}</td>
                    <td className="px-3 py-3">
                      <Selector aria-label={`Cliente de ${e.nombre_reporte}`} className="h-8 w-72" disabled={guardando === e.id}
                        value={e.cliente_id ?? ""} onChange={(ev) => cambiar(e.id, ev.target.value ? { cliente_id: Number(ev.target.value) } : { quitar_enlace: true })}>
                        <option value="">Sin enlazar</option>
                        {datos.clientes.map((c) => <option key={c.id} value={c.id}>{c.razon_social}{c.nit ? ` · ${c.nit}` : ""}</option>)}
                      </Selector>
                    </td>
                    <td className="px-3 py-3">{e.enlazada ? <Insignia tono={tonoRiesgo(e.nivel_riesgo)}>{e.nivel_riesgo ?? "Sin calificar"}</Insignia> : <span className="text-texto-3">—</span>}</td>
                    <td className="px-3 py-3">
                      <button role="switch" aria-checked={e.activa} disabled={guardando === e.id} onClick={() => cambiar(e.id, { activa: !e.activa })}
                        className="inline-flex items-center gap-2 text-texto-2">
                        <span className={cn("relative h-5 w-9 rounded-full transition-colors", e.activa ? "bg-acento" : "bg-borde-fuerte")}>
                          <span className={cn("absolute top-0.5 size-4 rounded-full bg-white transition-all", e.activa ? "left-[18px]" : "left-0.5")} />
                        </span>
                        {e.activa ? "Activa" : "Inactiva"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </Tarjeta>
  );
}
