"use client";

import { useState } from "react";
import Link from "next/link";
import { AlertTriangle, Building2, Plus } from "lucide-react";
import { Aviso, Boton, Entrada, Esqueleto, Etiqueta, Insignia, Tarjeta, TituloTarjeta, Vacio } from "@/components/ui/basicos";
import { enviar, ErrorApi } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";
import { useSesion } from "@/lib/sesion";
import { entero } from "@/lib/formato";
import type { Organizacion } from "@/lib/tipos";
import { cn } from "@/lib/cn";

export default function Organizaciones() {
  const { rol } = useSesion();
  const esSuper = rol === "super_admin";      // solo él crea y desactiva; el resto del equipo interno consulta
  const { datos, error, recargar } = useDatos<{ organizaciones: Organizacion[] }>("/api/organizaciones");
  const [nombre, setNombre] = useState("");
  const [nit, setNit] = useState("");
  const [creando, setCreando] = useState(false);
  const [guardando, setGuardando] = useState<number | null>(null);
  const [confirmar, setConfirmar] = useState<number | null>(null);
  const [fallo, setFallo] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);


  async function crear(ev: React.FormEvent) {
    ev.preventDefault();
    setCreando(true); setFallo(null); setAviso(null);
    try {
      const r = await enviar<{ nombre: string }>("/api/organizaciones", { nombre, nit: nit || null });
      setAviso(`Organización «${r.nombre}» creada. Ahora puede crearle usuarios en la sección Usuarios.`);
      setNombre(""); setNit("");
      await recargar();
    } catch (e) {
      setFallo(e instanceof ErrorApi ? e.message : "No se pudo crear la organización.");
    } finally { setCreando(false); }
  }

  async function alternar(o: Organizacion) {
    setGuardando(o.id); setFallo(null); setAviso(null);
    try { await enviar(`/api/organizaciones/${o.id}`, { activa: !o.activa }, "PATCH"); setConfirmar(null); await recargar(); }
    catch (e) { setFallo(e instanceof ErrorApi ? e.message : "No se pudo guardar."); }
    finally { setGuardando(null); }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Organizaciones</h1>
        <p className="mt-1 text-sm text-texto-3">
          Cada organización es un cliente de la plataforma y un sujeto obligado independiente. Sus usuarios solo ven datos de ella.
        </p>
      </div>

      {(error || fallo) && <Aviso tono="critico" icono={<AlertTriangle className="size-4" />}>{error ?? fallo}</Aviso>}
      {aviso && <Aviso tono="ok">{aviso}</Aviso>}

      {esSuper && <Tarjeta>
        <TituloTarjeta titulo="Nueva organización" />
        <form onSubmit={crear} className="grid gap-4 px-5 pb-5 pt-3 sm:grid-cols-[1fr_220px_auto] sm:items-end">
          <div>
            <Etiqueta htmlFor="org-nombre">Nombre</Etiqueta>
            <Entrada id="org-nombre" required minLength={2} maxLength={120} value={nombre} onChange={(e) => setNombre(e.target.value)} placeholder="Razón social o nombre comercial" />
          </div>
          <div>
            <Etiqueta htmlFor="org-nit">NIT (opcional)</Etiqueta>
            <Entrada id="org-nit" maxLength={30} value={nit} onChange={(e) => setNit(e.target.value)} />
          </div>
          <Boton type="submit" variante="primario" cargando={creando} disabled={nombre.trim().length < 2}>
            <Plus className="size-4" aria-hidden />Crear
          </Boton>
        </form>
      </Tarjeta>}

      <Tarjeta>
        <TituloTarjeta titulo="Organizaciones registradas"
          descripcion={esSuper ? "Abra una organización para completar su ficha: servicios, régimen, modelos de negocio, riesgo y oficial. Desactivarla cierra de inmediato la sesión de sus usuarios externos."
            : "Abra una organización para ver sus clientes, alertas y ficha."} />
        {!datos ? <div className="space-y-2 p-5">{[0, 1].map((i) => <Esqueleto key={i} className="h-12" />)}</div>
          : datos.organizaciones.length === 0 ? <Vacio icono={<Building2 className="size-8" />} titulo="No hay organizaciones" />
          : (
            <div className="overflow-x-auto px-2 pb-3 pt-3">
              <table className="w-full min-w-[720px] text-[13px]">
                <thead><tr className="text-left text-texto-3">
                  <th className="px-3 py-2 font-medium">Organización</th>
                  <th className="px-3 py-2 text-right font-medium">Clientes</th>
                  <th className="px-3 py-2 text-right font-medium">Empresas monitoreadas</th>
                  <th className="px-3 py-2 text-right font-medium">Usuarios externos</th>
                  <th className="px-3 py-2 font-medium">Estado</th></tr></thead>
                <tbody>
                  {datos.organizaciones.map((o) => (
                    <tr key={o.id} className={cn("border-t border-borde/70", guardando === o.id && "opacity-60")}>
                      <td className="px-3 py-3"><Link href={`/organizaciones/${o.id}`} className="font-medium text-acento hover:underline">{o.nombre}</Link>
                        {o.nit && <p className="text-xs text-texto-3">NIT {o.nit}</p>}</td>
                      <td className="cifra px-3 py-3 text-right">{entero(o.clientes ?? 0)}</td>
                      <td className="cifra px-3 py-3 text-right">{entero(o.empresas ?? 0)}</td>
                      <td className="cifra px-3 py-3 text-right">{entero(o.usuarios ?? 0)}</td>
                      <td className="px-3 py-3">
                        <span className="inline-flex items-center gap-3">
                          <Insignia tono={o.activa ? "ok" : "neutro"}>{o.activa ? "Activa" : "Inactiva"}</Insignia>
                          {!esSuper ? null : o.activa && confirmar === o.id ? (
                            <>
                              <Boton variante="peligro" className="h-8" cargando={guardando === o.id} onClick={() => alternar(o)}>Sí, desactivar</Boton>
                              <Boton variante="fantasma" className="h-8" onClick={() => setConfirmar(null)}>Cancelar</Boton>
                            </>
                          ) : (
                            <Boton variante="fantasma" className="h-8" disabled={guardando === o.id}
                              onClick={() => (o.activa ? setConfirmar(o.id) : alternar(o))}>
                              {o.activa ? "Desactivar" : "Activar"}
                            </Boton>
                          )}
                        </span>
                      </td>
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
