"use client";

import { useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle, Database, RefreshCw } from "lucide-react";
import { Aviso, Boton, Esqueleto, Insignia, Selector, Tarjeta, Vacio, tonoRiesgo } from "@/components/ui/basicos";
import { useDatos } from "@/lib/useDatos";
import { useSesion } from "@/lib/sesion";
import { entero, haceCuanto, fechaHora } from "@/lib/formato";
import type { Opciones, Resumen } from "@/lib/tipos";
import { cn } from "@/lib/cn";
import { BarraFiltros, filtrosDesdeUrl, type Filtros } from "./filtros";
import VistaTablero from "./tablero";
import VistaTransacciones from "./transacciones";
import VistaRiesgo from "./riesgo";
import VistaCargas from "./cargas";
import VistaEmpresas from "./empresas";

// externo: lo ve también el cliente. El resto es interno (Cumplimiento): riesgo, cargas y enlaces.
const VISTAS = [
  { id: "tablero", nombre: "Tablero", externo: true },
  { id: "transacciones", nombre: "Transacciones", externo: true },
  { id: "riesgo", nombre: "Riesgo", externo: false },
  { id: "cargas", nombre: "Cargas", externo: false },
  { id: "empresas", nombre: "Empresas", externo: false, soloCarga: true },
] as const;
type Vista = (typeof VISTAS)[number]["id"];

export default function Monitoreo() {
  const router = useRouter();
  const ruta = usePathname();
  const params = useSearchParams();
  const resumen = useDatos<Resumen>("/api/monitoreo/resumen");
  const esCliente = useSesion().rol === "cliente";

  const vistas = VISTAS.filter((v) => (!esCliente || v.externo) && (!("soloCarga" in v) || resumen.datos?.puede_cargar));
  const vista = (vistas.find((v) => v.id === params.get("vista"))?.id ?? "tablero") as Vista;

  const empresas = useMemo(() => (resumen.datos?.empresas ?? []).filter((e) => e.activa && (e.transacciones ?? 0) > 0), [resumen.datos]);
  const idParam = Number(params.get("empresa"));
  const empresa = empresas.find((e) => e.id === idParam) ?? [...empresas].sort((a, b) => (b.transacciones ?? 0) - (a.transacciones ?? 0))[0];

  const opciones = useDatos<Opciones>(empresa ? `/api/monitoreo/empresas/${empresa.id}/opciones` : null);
  const filtros = useMemo(() => filtrosDesdeUrl(params, opciones.datos), [params, opciones.datos]);

  const cambiar = useCallback((cambios: Record<string, string | string[] | null>) => {
    const q = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(cambios)) {
      q.delete(k);
      if (Array.isArray(v)) v.forEach((x) => q.append(k, x));
      else if (v) q.set(k, v);
    }
    router.replace(`${ruta}?${q.toString()}`, { scroll: false });
  }, [params, router, ruta]);

  const ponerFiltros = (f: Partial<Filtros>) => cambiar({
    periodo: f.periodo ?? null, desde: f.periodo === "personalizado" ? f.desde ?? null : null,
    hasta: f.periodo === "personalizado" ? f.hasta ?? null : null, estado: f.estados ?? [],
  });

  const usaFiltros = vista === "tablero" || vista === "transacciones" || vista === "riesgo";

  return (
    <div className="space-y-6">
      {/* Encabezado */}
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Monitoreo transaccional</h1>
          <p className="mt-1 text-sm text-texto-3">
            {resumen.datos?.ultima_carga
              ? <>Datos de AdamoPay actualizados {haceCuanto(resumen.datos.ultima_carga)} <span className="text-texto-3/70">({fechaHora(resumen.datos.ultima_carga)})</span></>
              : esCliente ? "Pagos, devoluciones y fondeos de su empresa."
              : "Pagos, devoluciones y fondeos por empresa, con alertas de riesgo."}
          </p>
        </div>
        {empresas.length > 1 && vista !== "cargas" && vista !== "empresas" && (
          <div className="flex items-center gap-3">
            <label htmlFor="empresa" className="text-sm text-texto-3">Empresa</label>
            <Selector id="empresa" className="w-72" value={empresa?.id ?? ""}
              onChange={(e) => cambiar({ empresa: e.target.value })}>
              {empresas.map((e) => <option key={e.id} value={e.id}>{e.nombre} · {entero(e.transacciones)} mov.</option>)}
            </Selector>
          </div>
        )}
      </div>

      {/* Pestañas */}
      <div className="flex gap-1 overflow-x-auto border-b border-borde" role="tablist">
        {vistas.map((v) => (
          <button key={v.id} role="tab" aria-selected={vista === v.id} onClick={() => cambiar({ vista: v.id === "tablero" ? null : v.id })}
            className={cn("-mb-px whitespace-nowrap border-b-2 px-3.5 pb-3 pt-1 text-sm transition-colors",
              vista === v.id ? "border-acento font-medium text-texto" : "border-transparent text-texto-3 hover:text-texto-2")}>
            {v.nombre}
          </button>
        ))}
      </div>

      {resumen.error && <Aviso tono="critico" icono={<AlertTriangle className="size-4" />} titulo="No se pudo cargar el módulo">
        {resumen.error} <button className="ml-1 underline" onClick={resumen.recargar}>Reintentar</button></Aviso>}

      {vista === "cargas" ? <VistaCargas puedeCargar={!!resumen.datos?.puede_cargar} alCargar={resumen.recargar} />
        : vista === "empresas" ? <VistaEmpresas alCambiar={resumen.recargar} />
        : resumen.cargando && !resumen.datos ? <Esqueleto className="h-96 w-full rounded-tarjeta" />
        : !empresa ? (
          <Tarjeta>
            <Vacio icono={<Database className="size-8" />} titulo="Aún no hay transacciones cargadas"
              texto={esCliente ? "Todavía no hay transacciones disponibles para su empresa. Si cree que es un error, comuníquese con su contacto en AdamoPay."
                : "Cuando se cargue el «Historial de pagos» de AdamoPay de una empresa —automáticamente desde OneDrive o de forma manual— verá aquí su tablero."}
              accion={esCliente ? undefined : <Boton onClick={() => cambiar({ vista: "cargas" })}><RefreshCw className="size-4" />Ir a Cargas</Boton>} />
          </Tarjeta>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-medium">{empresa.nombre}</span>
              {!esCliente && (empresa.enlazada
                ? <>{empresa.nit && <span className="text-texto-3">NIT {empresa.nit}</span>}
                    <Insignia tono={tonoRiesgo(empresa.nivel_riesgo)}>Riesgo {empresa.nivel_riesgo ?? "sin calificar"}</Insignia></>
                : <Insignia>Sin enlazar a un cliente</Insignia>)}
            </div>
            {usaFiltros && opciones.datos && (
              <BarraFiltros filtros={filtros} opciones={opciones.datos} onCambio={ponerFiltros} />
            )}
            {opciones.cargando && !opciones.datos ? <Esqueleto className="h-96 w-full rounded-tarjeta" />
              : opciones.datos && filtros && (
                vista === "tablero" ? <VistaTablero empresaId={empresa.id} filtros={filtros} continuidad={opciones.datos.continuidad} />
                : vista === "transacciones" ? <VistaTransacciones empresaId={empresa.id} filtros={filtros} />
                : <VistaRiesgo empresaId={empresa.id} filtros={filtros} />
              )}
          </>
        )}
    </div>
  );
}
