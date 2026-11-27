"use client";

import { useMemo, useState } from "react";
import { AlertTriangle, ScrollText } from "lucide-react";
import { Aviso, Boton, Entrada, Esqueleto, Etiqueta, Insignia, Selector, Tarjeta, TituloTarjeta, Vacio } from "@/components/ui/basicos";
import { useDatos } from "@/lib/useDatos";
import { entero, fechaHora } from "@/lib/formato";

interface Registro {
  id: number; created_at: string; username: string; accion: string; entidad: string; entidad_id: number | null;
  descripcion: string; resultado: "exitoso" | "fallido" | "rechazado"; ip_address: string | null;
}
interface Respuesta {
  total: number; pagina: number; tamano: number; registros: Registro[];
  opciones: { usuarios: string[]; entidades: string[]; acciones: string[] };
}

const TONO_ACCION: Record<string, "acento" | "ok" | "alerta" | "serio" | "neutro"> = {
  CREATE: "ok", UPDATE: "acento", DELETE: "serio", LOGIN: "neutro", LOGOUT: "neutro", EXPORT: "alerta", READ: "neutro",
};
const VACIOS = { usuario: "", entidad: "", accion: "", resultado: "", texto: "", desde: "", hasta: "" };

/** Log de auditoría: quién hizo qué y cuándo. Inmutable; solo consulta. */
export default function Auditoria() {
  const [f, setF] = useState(VACIOS);
  const [aplicados, setAplicados] = useState(VACIOS);
  const [pagina, setPagina] = useState(1);
  const ruta = useMemo(() => {
    const q = new URLSearchParams({ pagina: String(pagina), tamano: "50" });
    Object.entries(aplicados).forEach(([k, v]) => v && q.set(k, v));
    return `/api/auditoria?${q.toString()}`;
  }, [aplicados, pagina]);
  const { datos, error, cargando } = useDatos<Respuesta>(ruta);
  const paginas = datos ? Math.max(1, Math.ceil(datos.total / datos.tamano)) : 1;
  const buscar = (e: React.FormEvent) => { e.preventDefault(); setAplicados(f); setPagina(1); };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Auditoría</h1>
        <p className="mt-1 text-sm text-texto-3">Registro inmutable de las acciones en la plataforma: quién hizo qué, cuándo y desde dónde.</p>
      </div>

      <Tarjeta>
        <form onSubmit={buscar} className="grid gap-3 px-5 py-4 md:grid-cols-4 xl:grid-cols-[2fr_repeat(5,1fr)_auto] xl:items-end">
          <div><Etiqueta htmlFor="a-texto">Buscar en la descripción</Etiqueta>
            <Entrada id="a-texto" placeholder="p. ej. CM Grupo Tecno" value={f.texto} onChange={(e) => setF({ ...f, texto: e.target.value })} /></div>
          <div><Etiqueta htmlFor="a-usuario">Usuario</Etiqueta>
            <Selector id="a-usuario" value={f.usuario} onChange={(e) => setF({ ...f, usuario: e.target.value })}>
              <option value="">Todos</option>{datos?.opciones.usuarios.map((x) => <option key={x}>{x}</option>)}</Selector></div>
          <div><Etiqueta htmlFor="a-entidad">Módulo</Etiqueta>
            <Selector id="a-entidad" value={f.entidad} onChange={(e) => setF({ ...f, entidad: e.target.value })}>
              <option value="">Todos</option>{datos?.opciones.entidades.map((x) => <option key={x}>{x}</option>)}</Selector></div>
          <div><Etiqueta htmlFor="a-accion">Acción</Etiqueta>
            <Selector id="a-accion" value={f.accion} onChange={(e) => setF({ ...f, accion: e.target.value })}>
              <option value="">Todas</option>{datos?.opciones.acciones.map((x) => <option key={x}>{x}</option>)}</Selector></div>
          <div><Etiqueta htmlFor="a-desde">Desde</Etiqueta>
            <Entrada id="a-desde" type="date" value={f.desde} onChange={(e) => setF({ ...f, desde: e.target.value })} /></div>
          <div><Etiqueta htmlFor="a-hasta">Hasta</Etiqueta>
            <Entrada id="a-hasta" type="date" value={f.hasta} onChange={(e) => setF({ ...f, hasta: e.target.value })} /></div>
          <div className="flex gap-2">
            <Boton type="submit" variante="primario">Buscar</Boton>
            <Boton type="button" variante="fantasma" onClick={() => { setF(VACIOS); setAplicados(VACIOS); setPagina(1); }}>Limpiar</Boton>
          </div>
        </form>
      </Tarjeta>

      {error && <Aviso tono="critico" icono={<AlertTriangle className="size-4" />}>{error}</Aviso>}
      <Tarjeta>
        <TituloTarjeta titulo={datos ? `${entero(datos.total)} registros` : "Registros"}
          descripcion={datos && datos.total > datos.tamano ? `Página ${pagina} de ${paginas}` : undefined} />
        {!datos ? <Esqueleto className="m-5 h-64" /> : !datos.registros.length
          ? <Vacio icono={<ScrollText className="size-8" />} titulo="Sin registros para estos filtros" /> : (
          <div className="overflow-x-auto px-2 pb-3 pt-2">
            <table className="w-full min-w-[960px] text-[13px]">
              <thead><tr className="text-left text-texto-3">
                <th className="px-3 py-2 font-medium">Fecha</th><th className="px-3 py-2 font-medium">Usuario</th>
                <th className="px-3 py-2 font-medium">Acción</th><th className="px-3 py-2 font-medium">Módulo</th>
                <th className="px-3 py-2 font-medium">Descripción</th><th className="px-3 py-2 font-medium">Resultado</th>
                <th className="px-3 py-2 font-medium">IP</th></tr></thead>
              <tbody className={cargando ? "opacity-60" : undefined}>
                {datos.registros.map((r) => (
                  <tr key={r.id} className="border-t border-borde/70 align-top">
                    <td className="whitespace-nowrap px-3 py-2.5 text-texto-2">{fechaHora(r.created_at)}</td>
                    <td className="px-3 py-2.5">{r.username}</td>
                    <td className="px-3 py-2.5"><Insignia tono={TONO_ACCION[r.accion] ?? "neutro"}>{r.accion}</Insignia></td>
                    <td className="px-3 py-2.5 text-texto-2">{r.entidad}{r.entidad_id != null && <span className="text-texto-3"> #{r.entidad_id}</span>}</td>
                    <td className="max-w-xl px-3 py-2.5 text-texto">{r.descripcion}</td>
                    <td className="px-3 py-2.5">{r.resultado === "exitoso" ? <span className="text-texto-3">Exitoso</span>
                      : <Insignia tono="serio">{r.resultado === "fallido" ? "Fallido" : "Rechazado"}</Insignia>}</td>
                    <td className="whitespace-nowrap px-3 py-2.5 font-mono text-xs text-texto-3">{r.ip_address ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {paginas > 1 && (
              <div className="flex items-center justify-end gap-2 px-3 pt-3">
                <Boton variante="fantasma" disabled={pagina <= 1} onClick={() => setPagina(pagina - 1)}>Anterior</Boton>
                <span className="text-sm text-texto-3">{pagina} / {paginas}</span>
                <Boton variante="fantasma" disabled={pagina >= paginas} onClick={() => setPagina(pagina + 1)}>Siguiente</Boton>
              </div>
            )}
          </div>
        )}
      </Tarjeta>
    </div>
  );
}
