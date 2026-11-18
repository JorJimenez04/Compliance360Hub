"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Copy, KeyRound } from "lucide-react";
import { api, enviar, ErrorApi } from "@/lib/api";
import { useSesion } from "@/lib/sesion";
import { Boton, Tarjeta, TituloTarjeta } from "@/components/ui/basicos";

interface Cliente {
  id: number; username: string; nombre: string; email: string | null; activo: boolean;
  ultimo_acceso: string | null; empresas: string;
}
interface Resultado { username: string; clave_temporal: string }

export default function Usuarios() {
  const { rol } = useSesion();
  const [clientes, setClientes] = useState<Cliente[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmar, setConfirmar] = useState<number | null>(null);
  const [trabajando, setTrabajando] = useState(false);
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [copiado, setCopiado] = useState(false);

  const cargar = useCallback(() => {
    api<{ clientes: Cliente[] }>("/api/usuarios/clientes")
      .then((d) => setClientes(d.clientes))
      .catch((e) => setError(e instanceof ErrorApi ? e.message : "No se pudo cargar."));
  }, []);
  useEffect(() => { if (rol === "super_admin") cargar(); }, [rol, cargar]);

  if (rol !== "super_admin") return <p className="text-sm text-texto-3">Su rol no tiene acceso a esta sección.</p>;

  async function restablecer(id: number) {
    setTrabajando(true); setError(null); setCopiado(false);
    try {
      setResultado(await enviar<Resultado>(`/api/usuarios/clientes/${id}/restablecer-clave`));
      setConfirmar(null);
    } catch (e) {
      setError(e instanceof ErrorApi ? e.message : "No se pudo restablecer la clave.");
    } finally { setTrabajando(false); }
  }

  async function copiar() {
    if (!resultado) return;
    try { await navigator.clipboard.writeText(resultado.clave_temporal); setCopiado(true); } catch { /* el usuario puede copiarla a mano */ }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Usuarios clientes</h1>
        <p className="mt-1 text-sm text-texto-3">
          Los clientes no pueden cambiar su clave. Si la pierde o se filtró, genere una nueva y entréguela por llamada o mensajería.
        </p>
      </div>

      {error && <p role="alert" className="rounded-lg border border-critico/40 bg-critico/10 px-4 py-3 text-sm text-critico">{error}</p>}

      {resultado && (
        <Tarjeta className="border-acento/40">
          <TituloTarjeta titulo={`Nueva clave de «${resultado.username}»`}
            descripcion="Se muestra una sola vez. Al cerrar esta ventana no se puede volver a ver. La clave anterior ya no sirve." />
          <div className="flex flex-wrap items-center gap-3 px-5 pb-4 pt-3">
            <code className="rounded-lg border border-borde-fuerte bg-fondo px-3 py-2 font-mono text-base tracking-wider select-all">
              {resultado.clave_temporal}
            </code>
            <Boton onClick={copiar}>{copiado ? <Check className="size-4" aria-hidden /> : <Copy className="size-4" aria-hidden />}{copiado ? "Copiada" : "Copiar"}</Boton>
            <Boton variante="fantasma" onClick={() => setResultado(null)}>Cerrar</Boton>
          </div>
        </Tarjeta>
      )}

      <Tarjeta>
        <TituloTarjeta titulo="Clientes" />
        <div className="overflow-x-auto px-5 pb-4 pt-3">
          {!clientes ? <p className="text-sm text-texto-3">Cargando…</p> : clientes.length === 0 ? (
            <p className="text-sm text-texto-3">Aún no hay clientes. Se crean con scripts/crear_usuario_cliente.py.</p>
          ) : (
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wider text-texto-3">
                <tr><th className="py-2 pr-4">Cliente</th><th className="pr-4">Usuario</th><th className="pr-4">Empresas</th><th className="pr-4">Estado</th><th /></tr>
              </thead>
              <tbody className="divide-y divide-borde">
                {clientes.map((c) => (
                  <tr key={c.id}>
                    <td className="py-3 pr-4"><p className="font-medium">{c.nombre}</p><p className="text-xs text-texto-3">{c.email}</p></td>
                    <td className="pr-4 font-mono text-xs">{c.username}</td>
                    <td className="pr-4">{c.empresas || "—"}</td>
                    <td className="pr-4">{c.activo ? "Activo" : "Inactivo"}</td>
                    <td className="text-right">
                      {confirmar === c.id ? (
                        <span className="inline-flex gap-2">
                          <Boton variante="peligro" cargando={trabajando} onClick={() => restablecer(c.id)}>Sí, restablecer</Boton>
                          <Boton variante="fantasma" disabled={trabajando} onClick={() => setConfirmar(null)}>Cancelar</Boton>
                        </span>
                      ) : (
                        <Boton onClick={() => { setConfirmar(c.id); setResultado(null); }}><KeyRound className="size-4" aria-hidden />Restablecer clave</Boton>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </Tarjeta>
    </div>
  );
}
