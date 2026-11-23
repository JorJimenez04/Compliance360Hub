"use client";

import { useState } from "react";
import Link from "next/link";
import { AlertTriangle, RefreshCw, UserPlus, Users } from "lucide-react";
import { Aviso, Boton, Entrada, Esqueleto, Insignia, Tarjeta, TituloTarjeta, Vacio, tonoRiesgo } from "@/components/ui/basicos";
import { enviar, ErrorApi } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";
import { entero, fecha } from "@/lib/formato";
import type { ClienteFila, EmpresaSinCliente } from "@/lib/tipos";
import { cn } from "@/lib/cn";

export default function ClientesOrganizacion({ organizacionId }: { organizacionId: number }) {
  const { datos, error, recargar } = useDatos<{ clientes: ClienteFila[]; empresas_sin_cliente: EmpresaSinCliente[] }>(
    `/api/organizaciones/${organizacionId}/clientes`);
  const [marcadas, setMarcadas] = useState<number[]>([]);
  const [buscar, setBuscar] = useState("");
  const [trabajando, setTrabajando] = useState<"crear" | "evaluar" | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [fallo, setFallo] = useState<string | null>(null);

  async function crear() {
    setTrabajando("crear"); setFallo(null); setAviso(null);
    try {
      const r = await enviar<{ creados: unknown[] }>(`/api/organizaciones/${organizacionId}/clientes/desde-empresas`, { empresa_ids: marcadas });
      setAviso(`${r.creados.length} clientes creados y enlazados con su monitoreo. Complete su NIT, modelo de negocio y perfil declarado.`);
      setMarcadas([]); await recargar();
    } catch (e) { setFallo(e instanceof ErrorApi ? e.message : "No se pudieron crear."); }
    finally { setTrabajando(null); }
  }

  async function evaluar() {
    setTrabajando("evaluar"); setFallo(null); setAviso(null);
    try {
      const r = await enviar<{ nuevas: number; actualizadas: number; meses: number }>(`/api/organizaciones/${organizacionId}/alertas/evaluar`, { meses: 3 });
      setAviso(`Monitoreo evaluado (${r.meses} meses-empresa): ${r.nuevas} alertas nuevas, ${r.actualizadas} actualizadas.`);
      await recargar();
    } catch (e) { setFallo(e instanceof ErrorApi ? e.message : "No se pudo evaluar."); }
    finally { setTrabajando(null); }
  }

  if (error) return <Aviso tono="critico" icono={<AlertTriangle className="size-4" />}>{error}</Aviso>;
  if (!datos) return <Esqueleto className="h-96" />;
  const f = buscar.trim().toLowerCase();
  const clientes = datos.clientes.filter((c) => !f || c.razon_social.toLowerCase().includes(f) || (c.nit ?? "").includes(f));
  const pendientes = datos.empresas_sin_cliente;

  return (
    <div className="space-y-5">
      {fallo && <Aviso tono="critico" icono={<AlertTriangle className="size-4" />}>{fallo}</Aviso>}
      {aviso && <Aviso tono="ok">{aviso}</Aviso>}

      {pendientes.length > 0 && (
        <Tarjeta className="border-alerta/30">
          <TituloTarjeta titulo={`${pendientes.length} empresas monitoreadas sin ficha de cliente`}
            descripcion="Se crearon solas al cargar transacciones. Cree su ficha para gestionar su compliance."
            accion={<Boton variante="primario" cargando={trabajando === "crear"} disabled={!marcadas.length} onClick={crear}>
              <UserPlus className="size-4" aria-hidden />Crear {marcadas.length || ""} clientes</Boton>} />
          <div className="space-y-3 px-5 pb-5 pt-3">
            <button className="text-[13px] text-acento hover:underline" onClick={() => setMarcadas(marcadas.length === pendientes.length ? [] : pendientes.map((e) => e.id))}>
              {marcadas.length === pendientes.length ? "Quitar selección" : "Seleccionar todas"}
            </button>
            <div className="flex flex-wrap gap-2">
              {pendientes.map((e) => {
                const m = marcadas.includes(e.id);
                return (
                  <label key={e.id} className={cn("cursor-pointer rounded-lg border px-3 py-1.5 text-sm", m ? "border-acento bg-acento-tenue text-texto" : "border-borde-fuerte text-texto-2")}>
                    <input type="checkbox" className="sr-only" checked={m} onChange={() => setMarcadas(m ? marcadas.filter((x) => x !== e.id) : [...marcadas, e.id])} />
                    {e.nombre} <span className="cifra text-texto-3">· {entero(e.transacciones)} mov.</span>
                  </label>
                );
              })}
            </div>
          </div>
        </Tarjeta>
      )}

      <Tarjeta>
        <TituloTarjeta titulo="Clientes" descripcion="Haga clic en un cliente para abrir su expediente 360."
          accion={<div className="flex gap-2">
            <Entrada aria-label="Buscar cliente" placeholder="Buscar por nombre o NIT…" className="w-56" value={buscar} onChange={(e) => setBuscar(e.target.value)} />
            <Boton cargando={trabajando === "evaluar"} onClick={evaluar} title="Revisa los últimos 3 meses de cada empresa"><RefreshCw className="size-4" aria-hidden />Evaluar monitoreo</Boton>
          </div>} />
        {!clientes.length ? <Vacio icono={<Users className="size-8" />} titulo={datos.clientes.length ? "Ningún cliente coincide" : "Aún no hay clientes"}
          texto={datos.clientes.length ? undefined : "Créelos desde las empresas monitoreadas."} />
          : (
            <div className="overflow-x-auto px-2 pb-3 pt-3">
              <table className="w-full min-w-[820px] text-[13px]">
                <thead><tr className="text-left text-texto-3">
                  <th className="px-3 py-2 font-medium">Cliente</th><th className="px-3 py-2 font-medium">Riesgo</th>
                  <th className="px-3 py-2 font-medium">Estado</th><th className="px-3 py-2 font-medium">Empresas monitoreadas</th>
                  <th className="px-3 py-2 font-medium">Alertas abiertas</th><th className="px-3 py-2 font-medium">Próxima revisión</th></tr></thead>
                <tbody>
                  {clientes.map((c) => (
                    <tr key={c.id} className="border-t border-borde/70 hover:bg-panel-2/60">
                      <td className="px-3 py-3">
                        <Link href={`/organizaciones/${organizacionId}/clientes/${c.id}`} className="font-medium text-acento hover:underline">{c.razon_social}</Link>
                        <p className="text-xs text-texto-3">{c.nit ? `NIT ${c.nit}` : <span className="text-alerta">NIT pendiente</span>}</p>
                      </td>
                      <td className="px-3 py-3"><Insignia tono={tonoRiesgo(c.nivel_riesgo)}>{c.nivel_riesgo}</Insignia></td>
                      <td className="px-3 py-3 text-texto-2">{c.estado}</td>
                      <td className="px-3 py-3 text-texto-2">{c.empresas.map((e) => e.nombre).join(", ") || "—"}</td>
                      <td className="px-3 py-3">
                        {c.alertas_abiertas ? <span className="inline-flex items-center gap-2">
                          <span className="cifra">{entero(c.alertas_abiertas)}</span>
                          {c.alertas_altas > 0 && <Insignia tono="serio">{c.alertas_altas} altas o críticas</Insignia>}</span>
                          : <span className="text-texto-3">0</span>}
                      </td>
                      <td className="px-3 py-3 text-texto-3">{fecha(c.proxima_revision)}</td>
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
