"use client";

import { useState } from "react";
import { Save } from "lucide-react";
import { enviar, ErrorApi } from "@/lib/api";
import { Aviso, Boton, Entrada, Etiqueta, Selector } from "@/components/ui/basicos";
import type { Organizacion, PerfilGestionado, UsuarioGestionado } from "@/lib/tipos";
import { cn } from "@/lib/cn";

export const PERFILES: Record<PerfilGestionado, { nombre: string; descripcion: string }> = {
  cliente: { nombre: "Cliente", descripcion: "Equipo de la organización. Solo lectura: monitoreo y estado de su cumplimiento." },
  junta: { nombre: "Junta directiva", descripcion: "Tablero ejecutivo de su organización, sin datos personales." },
  compliance: { nombre: "Compliance (equipo interno)", descripcion: "Su equipo. Opera todas las organizaciones; no pertenece a ninguna." },
  director_cumplimiento: { nombre: "Director de cumplimiento", descripcion: "Responsable del compliance del grupo. Ve todas las organizaciones en solo lectura; no pertenece a ninguna." },
};

const esExterno = (r: PerfilGestionado) => r === "cliente" || r === "junta";

/** Ventana para editar un usuario: datos, perfil, organización y estado. Solo envía lo que cambió. */
export function EditarUsuario({ usuario, organizaciones, onCerrar, onGuardado }: {
  usuario: UsuarioGestionado; organizaciones: Organizacion[];
  onCerrar: () => void; onGuardado: (mensaje: string) => void;
}) {
  const [f, setF] = useState({
    nombre: usuario.nombre, email: usuario.email ?? "", username: usuario.username, rol: usuario.rol,
    organizacion_id: usuario.organizacion_id ? String(usuario.organizacion_id) : "", activo: usuario.activo,
    darOrganizacion: false,
  });
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const poner = (c: Partial<typeof f>) => setF((x) => ({ ...x, ...c }));

  const externo = esExterno(f.rol);
  const orgFinal = externo ? (f.organizacion_id ? Number(f.organizacion_id) : null) : null;
  const cambioRol = f.rol !== usuario.rol;
  const cambioOrg = orgFinal !== usuario.organizacion_id;
  const cambioUsuario = f.username.trim().toLowerCase() !== usuario.username.toLowerCase();
  const heredado = usuario.rol === "cliente" && usuario.alcance === "empresas" && f.rol === "cliente";
  // Organizaciones activas, más la actual aunque esté inactiva (para no perderla de la lista)
  const opciones = organizaciones.filter((o) => o.activa || o.id === usuario.organizacion_id);

  const cambios: Record<string, unknown> = {};
  if (f.nombre.trim() !== usuario.nombre) cambios.nombre = f.nombre.trim();
  if (f.email.trim().toLowerCase() !== (usuario.email ?? "").toLowerCase()) cambios.email = f.email.trim();
  if (cambioUsuario) cambios.username = f.username.trim();
  if (cambioRol) cambios.rol = f.rol;
  if (cambioOrg || cambioRol) cambios.organizacion_id = orgFinal;
  if (heredado && f.darOrganizacion) cambios.alcance = "organizacion";
  if (f.activo !== usuario.activo) cambios.activo = f.activo;
  const hayCambios = Object.keys(cambios).length > 0;
  const valido = f.nombre.trim().length >= 2 && f.email.includes("@") && /^[a-z0-9._-]{3,60}$/.test(f.username.trim().toLowerCase())
    && (!externo || orgFinal !== null);

  async function guardar() {
    setGuardando(true); setError(null);
    try {
      await enviar(`/api/usuarios/${usuario.id}`, cambios, "PATCH");
      onGuardado(`Usuario «${(cambios.username as string | undefined)?.toLowerCase() ?? usuario.username}» actualizado.`);
    } catch (e) {
      setError(e instanceof ErrorApi ? e.message : "No se pudo guardar.");
    } finally { setGuardando(false); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" role="dialog"
      aria-modal="true" aria-labelledby="titulo-editar">
      <div className="max-h-[92vh] w-full max-w-3xl space-y-5 overflow-y-auto rounded-2xl border border-borde-fuerte bg-panel p-6 shadow-2xl">
        <div>
          <h2 id="titulo-editar" className="text-lg font-semibold">Editar «{usuario.username}»</h2>
          <p className="mt-1 text-sm text-texto-3">La clave no se cambia aquí: use «Nueva clave».</p>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <div><Etiqueta htmlFor="e-nombre">Nombre completo</Etiqueta>
            <Entrada id="e-nombre" value={f.nombre} onChange={(e) => poner({ nombre: e.target.value })} /></div>
          <div><Etiqueta htmlFor="e-email">Correo</Etiqueta>
            <Entrada id="e-email" type="email" value={f.email} onChange={(e) => poner({ email: e.target.value })} /></div>
          <div><Etiqueta htmlFor="e-usuario">Usuario</Etiqueta>
            <Entrada id="e-usuario" value={f.username} onChange={(e) => poner({ username: e.target.value.toLowerCase().replace(/\s/g, "") })} />
            {cambioUsuario && <p className="mt-1 text-xs text-alerta">Desde ahora ingresará con «{f.username.trim()}». Avísele.</p>}</div>
        </div>

        <fieldset>
          <legend className="mb-2 text-[13px] font-medium text-texto-2">Perfil</legend>
          <div className="grid gap-2 md:grid-cols-2">
            {(Object.keys(PERFILES) as PerfilGestionado[]).map((p) => (
              <label key={p} className={cn("cursor-pointer rounded-lg border px-3 py-2.5 text-sm transition-colors",
                f.rol === p ? "border-acento bg-acento-tenue" : "border-borde-fuerte hover:border-texto-3")}>
                <input type="radio" name="e-perfil" className="sr-only" checked={f.rol === p} onChange={() => poner({ rol: p })} />
                <span className="font-medium">{PERFILES[p].nombre}</span>
                <span className="mt-0.5 block text-xs text-texto-3">{PERFILES[p].descripcion}</span>
              </label>
            ))}
          </div>
        </fieldset>

        {externo ? (
          <div className="grid gap-4 md:grid-cols-3">
            <div><Etiqueta htmlFor="e-org">Organización</Etiqueta>
              <Selector id="e-org" value={f.organizacion_id} onChange={(e) => poner({ organizacion_id: e.target.value })}>
                <option value="">Seleccione…</option>
                {opciones.map((o) => <option key={o.id} value={o.id}>{o.nombre}{o.activa ? "" : " (inactiva)"}</option>)}
              </Selector></div>
            <div className="text-[13px] text-texto-3 md:col-span-2">
              <p className="font-medium text-texto-2">Alcance</p>
              {f.rol === "cliente"
                ? heredado
                  ? <label className="mt-1 flex items-start gap-2">
                      <input type="checkbox" className="mt-0.5" checked={f.darOrganizacion} onChange={(e) => poner({ darOrganizacion: e.target.checked })} />
                      <span>Era de un cliente de su cliente y no tiene acceso. Marque para darle acceso a toda la organización.</span>
                    </label>
                  : <p>Toda la organización, en solo lectura (los clientes de sus clientes no tienen acceso).</p>
                : <p>Tablero ejecutivo de la organización, sin datos personales.</p>}
            </div>
          </div>
        ) : (
          <p className="text-[13px] text-texto-3">Equipo interno: no pertenece a ninguna organización{usuario.organizacion ? ` (se le quitará «${usuario.organizacion}»)` : ""}.</p>
        )}

        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={f.activo} onChange={(e) => poner({ activo: e.target.checked })} />
          Usuario activo <span className="text-xs text-texto-3">(desactivarlo cierra su sesión de inmediato)</span>
        </label>

        {(cambioRol || (cambioOrg && !cambioRol)) && (
          <Aviso tono="alerta">Al cambiar el perfil o la organización, su sesión abierta se cierra y deberá ingresar de nuevo.</Aviso>
        )}
        {error && <Aviso tono="critico">{error}</Aviso>}

        <div className="flex justify-end gap-2">
          <Boton variante="fantasma" onClick={onCerrar}>Cancelar</Boton>
          <Boton variante="primario" cargando={guardando} disabled={!hayCambios || !valido} onClick={guardar}>
            <Save className="size-4" aria-hidden />Guardar cambios</Boton>
        </div>
      </div>
    </div>
  );
}
