"use client";

import { useMemo, useState } from "react";
import { AlertTriangle, Check, Copy, KeyRound, Lock, Pencil, UserPlus } from "lucide-react";
import { enviar, ErrorApi } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";
import { useSesion } from "@/lib/sesion";
import { fechaHora } from "@/lib/formato";
import { Aviso, Boton, Entrada, Esqueleto, Etiqueta, Insignia, Selector, Tarjeta, TituloTarjeta, Vacio } from "@/components/ui/basicos";
import type { Alcance, Organizacion, PerfilGestionado, UsuarioGestionado, UsuarioInterno } from "@/lib/tipos";
import { cn } from "@/lib/cn";
import { CampoClave, claveValida, SelectorModoClave, type ModoClave } from "./clave";
import { EditarUsuario, PERFILES } from "./editar";

interface Resultado { username: string; clave_temporal: string | null; titulo: string }

const VACIO = { username: "", nombre: "", email: "", rol: "cliente" as PerfilGestionado, organizacion_id: "", alcance: "organizacion" as Alcance, empresas: [] as number[] };

export default function Usuarios() {
  const { rol } = useSesion();
  const esSuper = rol === "super_admin";
  const usuarios = useDatos<{ usuarios: UsuarioGestionado[]; internos?: UsuarioInterno[] }>(esSuper ? "/api/usuarios" : null);
  const orgs = useDatos<{ organizaciones: Organizacion[] }>(esSuper ? "/api/organizaciones" : null);
  const [form, setForm] = useState(VACIO);
  const [creando, setCreando] = useState(false);
  const [trabajando, setTrabajando] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [copiado, setCopiado] = useState(false);
  const [modoClave, setModoClave] = useState<ModoClave>("generar");
  const [clave, setClave] = useState("");
  const [clave2, setClave2] = useState("");
  // «Nueva clave» de un usuario existente: ventana con la misma elección (generar o escribir)
  const [cambiar, setCambiar] = useState<UsuarioGestionado | null>(null);
  const [modoCambio, setModoCambio] = useState<ModoClave>("generar");
  const [claveCambio, setClaveCambio] = useState("");
  const [claveCambio2, setClaveCambio2] = useState("");
  const [editar, setEditar] = useState<UsuarioGestionado | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [errorForm, setErrorForm] = useState<string | null>(null);

  const activas = useMemo(() => (orgs.datos?.organizaciones ?? []).filter((o) => o.activa), [orgs.datos]);

  if (!esSuper) return <p className="text-sm text-texto-3">Su rol no tiene acceso a esta sección.</p>;

  const externo = form.rol === "cliente" || form.rol === "junta";
  const listo = form.username.trim().length >= 3 && form.nombre.trim().length >= 2 && form.email.includes("@")
    && (!externo || form.organizacion_id) && (modoClave === "generar" || claveValida(clave, clave2));

  async function crear(ev: React.FormEvent) {
    ev.preventDefault();
    setCreando(true); setError(null); setErrorForm(null); setAviso(null); setResultado(null); setCopiado(false);
    try {
      const cuerpo = {
        username: form.username.trim(), nombre: form.nombre.trim(), email: form.email.trim(), rol: form.rol,
        organizacion_id: externo ? Number(form.organizacion_id) : null,
        alcance: form.rol === "cliente" ? form.alcance : null,
        empresas: [],
        clave: modoClave === "escribir" ? clave : null,
      };
      const r = await enviar<{ username: string; clave_temporal: string | null }>("/api/usuarios", cuerpo);
      setResultado({ ...r, titulo: `Usuario «${r.username}» creado` });
      setForm(VACIO); setClave(""); setClave2(""); setModoClave("generar");
      await usuarios.recargar();
    } catch (e) {
      // El error se muestra junto al botón: es donde está mirando quien acaba de pulsarlo
      setErrorForm(e instanceof ErrorApi ? e.message : "No se pudo crear el usuario.");
    } finally { setCreando(false); }
  }

  async function restablecer(id: number) {
    setTrabajando(id); setError(null); setCopiado(false);
    try {
      const r = await enviar<{ username: string; clave_temporal: string | null }>(`/api/usuarios/${id}/restablecer-clave`,
        { clave: modoCambio === "escribir" ? claveCambio : null });
      setResultado({ ...r, titulo: r.clave_temporal ? `Nueva clave de «${r.username}»` : `Clave asignada a «${r.username}»` });
      setCambiar(null); setClaveCambio(""); setClaveCambio2("");
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
    try {
      await navigator.clipboard.writeText(resultado.clave_temporal
        ? `Usuario: ${resultado.username}\nClave: ${resultado.clave_temporal}` : resultado.username);
      setCopiado(true);
    } catch { /* se puede seleccionar y copiar a mano */ }
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

      {error && !cambiar && <Aviso tono="critico" icono={<AlertTriangle className="size-4" />}>{error}</Aviso>}
      {aviso && <Aviso tono="ok" icono={<Check className="size-4" />}>{aviso}</Aviso>}

      {editar && (
        <EditarUsuario usuario={editar} organizaciones={orgs.datos?.organizaciones ?? []} onCerrar={() => setEditar(null)}
          onGuardado={async (m) => { setEditar(null); setAviso(m); await usuarios.recargar(); }} />
      )}

      {resultado && (
        // Ventana al centro: la clave solo se ve una vez y no puede pasar desapercibida
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" role="dialog"
          aria-modal="true" aria-labelledby="titulo-clave">
          <div className="w-full max-w-lg rounded-2xl border border-acento/40 bg-panel p-6 shadow-2xl">
            <div className="flex items-start gap-3">
              <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-acento-tenue text-acento"><KeyRound className="size-5" aria-hidden /></span>
              <div>
                <h2 id="titulo-clave" className="text-lg font-semibold">{resultado.titulo}</h2>
                <p className="mt-1 text-sm text-texto-3">{resultado.clave_temporal
                  ? <>Esta clave se muestra <strong className="text-texto">una sola vez</strong>. Cópiela ahora y entréguela por mensajería, no dictada.</>
                  : <>Quedó con la clave que usted escribió. Entréguele su usuario y esa clave por mensajería, no dictada.</>}</p>
              </div>
            </div>
            <div className="mt-5 space-y-1.5 rounded-xl border border-borde-fuerte bg-fondo p-4">
              <p className="text-xs text-texto-3">Usuario</p>
              <p className="select-all font-mono text-base">{resultado.username}</p>
              {resultado.clave_temporal && <>
                <p className="pt-2 text-xs text-texto-3">Clave temporal</p>
                <p className="select-all break-all font-mono text-2xl tracking-widest text-acento">{resultado.clave_temporal}</p>
              </>}
            </div>
            <p className="mt-3 text-xs text-texto-3">El usuario no distingue mayúsculas. Si genera otra clave, esta deja de funcionar.</p>
            <div className="mt-5 flex flex-wrap justify-end gap-2">
              <Boton variante="primario" onClick={copiar}>
                {copiado ? <Check className="size-4" aria-hidden /> : <Copy className="size-4" aria-hidden />}{copiado ? "Copiado" : resultado.clave_temporal ? "Copiar usuario y clave" : "Copiar usuario"}</Boton>
              <Boton onClick={() => { if (copiado || !resultado.clave_temporal || window.confirm("¿Cerrar sin copiar? La clave no se podrá volver a ver.")) setResultado(null); }}>
                Listo, ya la entregué</Boton>
            </div>
          </div>
        </div>
      )}

      {cambiar && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" role="dialog"
          aria-modal="true" aria-labelledby="titulo-cambio">
          <div className="w-full max-w-xl space-y-4 rounded-2xl border border-borde-fuerte bg-panel p-6 shadow-2xl">
            <div>
              <h2 id="titulo-cambio" className="text-lg font-semibold">Nueva clave para «{cambiar.username}»</h2>
              <p className="mt-1 text-sm text-texto-3">La clave actual deja de funcionar en cuanto confirme.</p>
            </div>
            <SelectorModoClave modo={modoCambio} onModo={setModoCambio} />
            {modoCambio === "escribir" && <CampoClave idBase="cambio" clave={claveCambio} confirmacion={claveCambio2}
              onClave={setClaveCambio} onConfirmacion={setClaveCambio2} />}
            {error && <Aviso tono="critico">{error}</Aviso>}
            <div className="flex justify-end gap-2">
              <Boton variante="fantasma" onClick={() => { setCambiar(null); setError(null); }}>Cancelar</Boton>
              <Boton variante="primario" cargando={trabajando === cambiar.id}
                disabled={modoCambio === "escribir" && !claveValida(claveCambio, claveCambio2)} onClick={() => restablecer(cambiar.id)}>
                <KeyRound className="size-4" aria-hidden />{modoCambio === "generar" ? "Generar clave" : "Asignar clave"}</Boton>
            </div>
          </div>
        </div>
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
                value={form.username} onChange={(e) => poner({ username: e.target.value.toLowerCase().replace(/\s/g, "") })} placeholder="nombre.apellido" />
              <p className="mt-1 text-xs text-texto-3">Se guarda en minúsculas; al ingresar no importan las mayúsculas.</p></div>
          </div>

          {externo && (
            <div className="grid gap-4 md:grid-cols-3">
              <div><Etiqueta htmlFor="u-org">Organización</Etiqueta>
                <Selector id="u-org" required value={form.organizacion_id} onChange={(e) => poner({ organizacion_id: e.target.value, empresas: [] })}>
                  <option value="">Seleccione…</option>
                  {activas.map((o) => <option key={o.id} value={o.id}>{o.nombre}</option>)}
                </Selector></div>
              {form.rol === "cliente" && (
                <p className="text-[13px] text-texto-3 md:col-span-2">Ve en solo lectura la operación de toda la organización (monitoreo, cartera y transacciones). No ve alertas, casos, riesgo ni reportes UIAF.</p>
              )}
            </div>
          )}

          <div className="space-y-3">
            <Etiqueta>Clave de acceso</Etiqueta>
            <SelectorModoClave modo={modoClave} onModo={setModoClave} />
            {modoClave === "escribir" && <CampoClave idBase="nueva" clave={clave} confirmacion={clave2} onClave={setClave} onConfirmacion={setClave2} />}
          </div>

          {errorForm && <Aviso tono="critico" icono={<AlertTriangle className="size-4" />}>{errorForm}</Aviso>}
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
                      <td className="pr-4 text-texto-2">{u.rol !== "cliente" ? "—" : u.alcance === "organizacion" ? "Toda la organización" : "Sin acceso (cliente de cliente)"}</td>
                      <td className="pr-4 text-texto-3">{u.ultimo_acceso ? fechaHora(u.ultimo_acceso) : "Nunca"}</td>
                      <td className="pr-4"><Insignia tono={u.activo ? "ok" : "neutro"}>{u.activo ? "Activo" : "Inactivo"}</Insignia></td>
                      <td className="whitespace-nowrap text-right">
                        <span className="inline-flex gap-2">
                          <Boton onClick={() => { setEditar(u); setAviso(null); setError(null); }}><Pencil className="size-4" aria-hidden />Editar</Boton>
                          <Boton onClick={() => { setCambiar(u); setModoCambio("generar"); setClaveCambio(""); setClaveCambio2(""); setResultado(null); setError(null); }}>
                            <KeyRound className="size-4" aria-hidden />Nueva clave</Boton>
                          <Boton variante="fantasma" disabled={trabajando === u.id} onClick={() => alternar(u)}>{u.activo ? "Desactivar" : "Activar"}</Boton>
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
        </div>
      </Tarjeta>

      {(usuarios.datos?.internos?.length ?? 0) > 0 && (
        <Tarjeta>
          <TituloTarjeta titulo="Cuentas internas" descripcion="Administración de la plataforma. Se muestran para saber quién usa cada usuario o correo; no se editan desde aquí." />
          <div className="overflow-x-auto px-5 pb-4 pt-3">
            <table className="w-full min-w-[700px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wider text-texto-3">
                <tr><th className="py-2 pr-4">Usuario</th><th className="pr-4">Perfil</th><th className="pr-4">Último ingreso</th><th className="pr-4">Estado</th><th /></tr>
              </thead>
              <tbody className="divide-y divide-borde">
                {usuarios.datos!.internos!.map((u) => (
                  <tr key={u.id}>
                    <td className="py-3 pr-4"><p className="font-medium">{u.nombre}</p><p className="text-xs text-texto-3">{u.username} · {u.email ?? "sin correo"}</p></td>
                    <td className="pr-4">{u.rol === "super_admin" ? "Super admin" : u.rol === "admin" ? "Admin" : u.rol}</td>
                    <td className="pr-4 text-texto-3">{u.ultimo_acceso ? fechaHora(u.ultimo_acceso) : "Nunca"}</td>
                    <td className="pr-4"><Insignia tono={u.activo ? "ok" : "neutro"}>{u.activo ? "Activo" : "Inactivo"}</Insignia></td>
                    <td className="text-right"><Insignia><Lock className="size-3" aria-hidden />Solo lectura</Insignia></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Tarjeta>
      )}
    </div>
  );
}
