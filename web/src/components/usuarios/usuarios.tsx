"use client";

import { useMemo, useState } from "react";
import { AlertTriangle, Check, Copy, KeyRound, UserPlus } from "lucide-react";
import { enviar, ErrorApi } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";
import { useSesion } from "@/lib/sesion";
import { fechaHora } from "@/lib/formato";
import { Aviso, Boton, Entrada, Esqueleto, Etiqueta, Insignia, Selector, Tarjeta, TituloTarjeta, Vacio } from "@/components/ui/basicos";
import type { Alcance, Empresa, Organizacion, PerfilGestionado, UsuarioGestionado } from "@/lib/tipos";
import { cn } from "@/lib/cn";

const PERFILES: Record<PerfilGestionado, { nombre: string; descripcion: string }> = {
  cliente: { nombre: "Cliente", descripcion: "Equipo de la organización. Solo lectura: monitoreo y estado de su cumplimiento." },
  junta: { nombre: "Junta directiva", descripcion: "Tablero ejecutivo de su organización, sin datos personales." },
  compliance: { nombre: "Compliance (equipo interno)", descripcion: "Su equipo. Opera todas las organizaciones; no pertenece a ninguna." },
};

interface Resultado { username: string; clave_temporal: string; titulo: string }

const VACIO = { username: "", nombre: "", email: "", rol: "cliente" as PerfilGestionado, organizacion_id: "", alcance: "organizacion" as Alcance, empresas: [] as number[] };

export default function Usuarios() {
  const { rol } = useSesion();
  const esSuper = rol === "super_admin";
  const usuarios = useDatos<{ usuarios: UsuarioGestionado[] }>(esSuper ? "/api/usuarios" : null);
  const orgs = useDatos<{ organizaciones: Organizacion[] }>(esSuper ? "/api/organizaciones" : null);
  const [form, setForm] = useState(VACIO);
  const empresasOrg = useDatos<{ empresas: Empresa[] }>(
    esSuper && form.rol === "cliente" && form.alcance === "empresas" && form.organizacion_id
      ? `/api/monitoreo/empresas?organizacion_id=${form.organizacion_id}` : null);
  const [creando, setCreando] = useState(false);
  const [confirmar, setConfirmar] = useState<number | null>(null);
  const [trabajando, setTrabajando] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [copiado, setCopiado] = useState(false);

  const activas = useMemo(() => (orgs.datos?.organizaciones ?? []).filter((o) => o.activa), [orgs.datos]);

  if (!esSuper) return <p className="text-sm text-texto-3">Su rol no tiene acceso a esta sección.</p>;

  const externo = form.rol !== "compliance";
  const listo = form.username.trim().length >= 3 && form.nombre.trim().length >= 2 && form.email.includes("@")
    && (!externo || form.organizacion_id) && (form.rol !== "cliente" || form.alcance === "organizacion" || form.empresas.length > 0);

  async function crear(ev: React.FormEvent) {
    ev.preventDefault();
    setCreando(true); setError(null); setResultado(null); setCopiado(false);
    try {
      const cuerpo = {
        username: form.username.trim(), nombre: form.nombre.trim(), email: form.email.trim(), rol: form.rol,
        organizacion_id: externo ? Number(form.organizacion_id) : null,
        alcance: form.rol === "cliente" ? form.alcance : null,
        empresas: form.rol === "cliente" && form.alcance === "empresas" ? form.empresas : [],
      };
      const r = await enviar<{ username: string; clave_temporal: string }>("/api/usuarios", cuerpo);
      setResultado({ ...r, titulo: `Usuario «${r.username}» creado` });
      setForm(VACIO);
      await usuarios.recargar();
    } catch (e) {
      setError(e instanceof ErrorApi ? e.message : "No se pudo crear el usuario.");
    } finally { setCreando(false); }
  }

  async function restablecer(id: number) {
    setTrabajando(id); setError(null); setCopiado(false);
    try {
      const r = await enviar<{ username: string; clave_temporal: string }>(`/api/usuarios/${id}/restablecer-clave`);
      setResultado({ ...r, titulo: `Nueva clave de «${r.username}»` });
      setConfirmar(null);
      await usuarios.recargar();
    } catch (e) {
      setError(e instanceof ErrorApi ? e.message : "No se pudo restablecer la clave.");
    } finally { setTrabajando(null); }
  }

  async function alternar(u: UsuarioGestionado) {
    setTrabajando(u.id); setError(null);
    try { await enviar(`/api/usuarios/${u.id}`, { activo: !u.activo }, "PATCH"); await usuarios.recargar(); }
    catch (e) { setError(e instanceof ErrorApi ? e.message : "No se pudo guardar."); }
    finally { setTrabajando(null); }
  }

  async function copiar() {
    if (!resultado) return;
    try { await navigator.clipboard.writeText(resultado.clave_temporal); setCopiado(true); } catch { /* se puede copiar a mano */ }
  }

  const poner = (cambios: Partial<typeof VACIO>) => setForm((f) => ({ ...f, ...cambios }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Usuarios</h1>
        <p className="mt-1 text-sm text-texto-3">
          Solo usted crea perfiles. Nadie puede cambiar su propia clave: si la pierde o se filtró, genere una nueva y entréguela por llamada o mensajería.
        </p>
      </div>

      {error && <Aviso tono="critico" icono={<AlertTriangle className="size-4" />}>{error}</Aviso>}

      {resultado && (
        <Tarjeta className="border-acento/40">
          <TituloTarjeta titulo={resultado.titulo}
            descripcion="La clave temporal se muestra una sola vez. Al cerrar este aviso no se puede volver a ver." />
          <div className="flex flex-wrap items-center gap-3 px-5 pb-4 pt-3">
            <code className="select-all rounded-lg border border-borde-fuerte bg-fondo px-3 py-2 font-mono text-base tracking-wider">
              {resultado.clave_temporal}
            </code>
            <Boton onClick={copiar}>{copiado ? <Check className="size-4" aria-hidden /> : <Copy className="size-4" aria-hidden />}{copiado ? "Copiada" : "Copiar"}</Boton>
            <Boton variante="fantasma" onClick={() => setResultado(null)}>Cerrar</Boton>
          </div>
        </Tarjeta>
      )}

      <Tarjeta>
        <TituloTarjeta titulo="Nuevo usuario" />
        <form onSubmit={crear} className="space-y-4 px-5 pb-5 pt-3">
          <fieldset>
            <legend className="mb-2 text-[13px] font-medium text-texto-2">Perfil</legend>
            <div className="grid gap-2 md:grid-cols-3">
              {(Object.keys(PERFILES) as PerfilGestionado[]).map((p) => (
                <label key={p} className={cn("cursor-pointer rounded-lg border px-3 py-2.5 text-sm transition-colors",
                  form.rol === p ? "border-acento bg-acento-tenue" : "border-borde-fuerte hover:border-texto-3")}>
                  <input type="radio" name="perfil" className="sr-only" checked={form.rol === p} onChange={() => poner({ rol: p, empresas: [] })} />
                  <span className="font-medium">{PERFILES[p].nombre}</span>
                  <span className="mt-0.5 block text-xs text-texto-3">{PERFILES[p].descripcion}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <div className="grid gap-4 md:grid-cols-3">
            <div><Etiqueta htmlFor="u-nombre">Nombre completo</Etiqueta>
              <Entrada id="u-nombre" required value={form.nombre} onChange={(e) => poner({ nombre: e.target.value })} /></div>
            <div><Etiqueta htmlFor="u-email">Correo</Etiqueta>
              <Entrada id="u-email" type="email" required value={form.email} onChange={(e) => poner({ email: e.target.value })} /></div>
            <div><Etiqueta htmlFor="u-usuario">Usuario</Etiqueta>
              <Entrada id="u-usuario" required pattern="[A-Za-z0-9._\-]{3,60}" title="De 3 a 60 caracteres: letras, números, punto o guion"
                value={form.username} onChange={(e) => poner({ username: e.target.value })} placeholder="nombre.apellido" /></div>
          </div>

          {externo && (
            <div className="grid gap-4 md:grid-cols-3">
              <div><Etiqueta htmlFor="u-org">Organización</Etiqueta>
                <Selector id="u-org" required value={form.organizacion_id} onChange={(e) => poner({ organizacion_id: e.target.value, empresas: [] })}>
                  <option value="">Seleccione…</option>
                  {activas.map((o) => <option key={o.id} value={o.id}>{o.nombre}</option>)}
                </Selector></div>
              {form.rol === "cliente" && (
                <div className="md:col-span-2">
                  <Etiqueta>Qué puede ver</Etiqueta>
                  <div className="flex flex-wrap gap-4 pt-1.5 text-sm">
                    <label className="inline-flex items-center gap-2"><input type="radio" name="alcance" checked={form.alcance === "organizacion"}
                      onChange={() => poner({ alcance: "organizacion", empresas: [] })} />Toda la organización</label>
                    <label className="inline-flex items-center gap-2"><input type="radio" name="alcance" checked={form.alcance === "empresas"}
                      onChange={() => poner({ alcance: "empresas" })} />Solo empresas específicas</label>
                  </div>
                </div>
              )}
            </div>
          )}

          {form.rol === "cliente" && form.alcance === "empresas" && form.organizacion_id && (
            <div>
              <Etiqueta>Empresas que puede consultar</Etiqueta>
              {!empresasOrg.datos ? <Esqueleto className="h-10" />
                : empresasOrg.datos.empresas.length === 0 ? <p className="text-sm text-texto-3">Esta organización aún no tiene empresas monitoreadas.</p>
                : (
                  <div className="flex flex-wrap gap-2">
                    {empresasOrg.datos.empresas.map((e) => {
                      const marcada = form.empresas.includes(e.id);
                      return (
                        <label key={e.id} className={cn("cursor-pointer rounded-lg border px-3 py-1.5 text-sm",
                          marcada ? "border-acento bg-acento-tenue text-acento" : "border-borde-fuerte text-texto-2")}>
                          <input type="checkbox" className="sr-only" checked={marcada}
                            onChange={() => poner({ empresas: marcada ? form.empresas.filter((x) => x !== e.id) : [...form.empresas, e.id] })} />
                          {e.nombre}
                        </label>
                      );
                    })}
                  </div>
                )}
            </div>
          )}

          <Boton type="submit" variante="primario" cargando={creando} disabled={!listo}>
            <UserPlus className="size-4" aria-hidden />Crear usuario
          </Boton>
        </form>
      </Tarjeta>

      <Tarjeta>
        <TituloTarjeta titulo="Usuarios" descripcion="Desactivar a alguien cierra su sesión de inmediato." />
        <div className="overflow-x-auto px-5 pb-4 pt-3">
          {usuarios.error ? <p className="text-sm text-critico">{usuarios.error}</p>
            : !usuarios.datos ? <Esqueleto className="h-24" />
            : usuarios.datos.usuarios.length === 0 ? <Vacio titulo="Aún no hay usuarios" texto="Cree el primero con el formulario de arriba." />
            : (
              <table className="w-full min-w-[860px] text-left text-sm">
                <thead className="text-xs uppercase tracking-wider text-texto-3">
                  <tr><th className="py-2 pr-4">Usuario</th><th className="pr-4">Perfil</th><th className="pr-4">Organización</th>
                    <th className="pr-4">Alcance</th><th className="pr-4">Último ingreso</th><th className="pr-4">Estado</th><th /></tr>
                </thead>
                <tbody className="divide-y divide-borde">
                  {usuarios.datos.usuarios.map((u) => (
                    <tr key={u.id} className={cn(trabajando === u.id && "opacity-60")}>
                      <td className="py-3 pr-4"><p className="font-medium">{u.nombre}</p><p className="text-xs text-texto-3">{u.username} · {u.email}</p></td>
                      <td className="pr-4">{PERFILES[u.rol]?.nombre ?? u.rol}</td>
                      <td className="pr-4">{u.organizacion ?? <span className="text-texto-3">Equipo interno</span>}</td>
                      <td className="pr-4 text-texto-2">{u.rol !== "cliente" ? "—" : u.alcance === "organizacion" ? "Toda la organización" : u.empresas || "Sin empresas"}</td>
                      <td className="pr-4 text-texto-3">{u.ultimo_acceso ? fechaHora(u.ultimo_acceso) : "Nunca"}</td>
                      <td className="pr-4"><Insignia tono={u.activo ? "ok" : "neutro"}>{u.activo ? "Activo" : "Inactivo"}</Insignia></td>
                      <td className="whitespace-nowrap text-right">
                        {confirmar === u.id ? (
                          <span className="inline-flex gap-2">
                            <Boton variante="peligro" cargando={trabajando === u.id} onClick={() => restablecer(u.id)}>Sí, nueva clave</Boton>
                            <Boton variante="fantasma" onClick={() => setConfirmar(null)}>Cancelar</Boton>
                          </span>
                        ) : (
                          <span className="inline-flex gap-2">
                            <Boton onClick={() => { setConfirmar(u.id); setResultado(null); }}><KeyRound className="size-4" aria-hidden />Nueva clave</Boton>
                            <Boton variante="fantasma" disabled={trabajando === u.id} onClick={() => alternar(u)}>{u.activo ? "Desactivar" : "Activar"}</Boton>
                          </span>
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
