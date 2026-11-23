"use client";

import { useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle, ArrowLeft, Database, RefreshCw } from "lucide-react";
import { Aviso, Boton, Esqueleto, Insignia, Selector, Tarjeta, Vacio, tonoRiesgo } from "@/components/ui/basicos";
import { useDatos } from "@/lib/useDatos";
import { useSesion } from "@/lib/sesion";
import { entero, haceCuanto, fechaHora } from "@/lib/formato";
import { ROLES_EXTERNOS, type Opciones, type Organizacion, type Resumen } from "@/lib/tipos";
import { cn } from "@/lib/cn";
import { BarraFiltros, filtrosDesdeUrl, type Filtros } from "./filtros";
import VistaTablero from "./tablero";
import VistaTransacciones from "./transacciones";
import VistaRiesgo from "./riesgo";
import VistaCargas from "./cargas";
import VistaEmpresas from "./empresas";
import VistaCartera from "./cartera";

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
  const sesion = useSesion();
  const esCliente = ROLES_EXTERNOS.includes(sesion.rol);
  // Internos: selector de organización (?org=). El cliente no elige: la API le da solo la suya.
  const orgs = useDatos<{ organizaciones: Organizacion[] }>(esCliente ? null : "/api/organizaciones");
  const orgParam = esCliente ? "" : params.get("org") ?? "";
  const resumen = useDatos<Resumen>(`/api/monitoreo/resumen${orgParam ? `?organizacion_id=${orgParam}` : ""}`);

  const vistas = VISTAS.filter((v) => (!esCliente || v.externo) && (!("soloCarga" in v) || resumen.datos?.puede_cargar));
  const vista = (vistas.find((v) => v.id === params.get("vista"))?.id ?? "tablero") as Vista;

  const empresas = useMemo(() => (resumen.datos?.empresas ?? []).filter((e) => e.activa && (e.transacciones ?? 0) > 0), [resumen.datos]);
  const idParam = Number(params.get("empresa"));
  const elegida = empresas.find((e) => e.id === idParam);
  // Tablero sin empresa elegida y con varias empresas: vista de cartera (todas a la vista).
  // Transacciones y Riesgo siempre trabajan sobre una empresa: si no hay una elegida, la de más movimientos.
  const enCartera = vista === "tablero" && !elegida && empresas.length > 1;
  const empresa = enCartera ? undefined
    : elegida ?? [...empresas].sort((a, b) => (b.transacciones ?? 0) - (a.transacciones ?? 0))[0];

  const opciones = useDatos<Opciones>(empresa ? `/api/monitoreo/empresas/${empresa.id}/opciones` : null);
  const opcionesCartera = useDatos<Opciones>(enCartera
    ? `/api/monitoreo/cartera/opciones${orgParam ? `?organizacion_id=${orgParam}` : ""}` : null);
  const opcionesActivas = enCartera ? opcionesCartera.datos : opciones.datos;
  const filtros = useMemo(() => filtrosDesdeUrl(params, opcionesActivas), [params, opcionesActivas]);

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
        <div className="flex flex-wrap items-center gap-3">
        {!esCliente && (orgs.datos?.organizaciones.length ?? 0) > 1 && vista !== "cargas" && (
          <div className="flex items-center gap-3">
            <label htmlFor="organizacion" className="text-sm text-texto-3">Organización</label>
            <Selector id="organizacion" className="w-56" value={orgParam}
              onChange={(e) => cambiar({ org: e.target.value || null, empresa: null })}>
              <option value="">Todas</option>
              {orgs.datos!.organizaciones.map((o) => <option key={o.id} value={o.id}>{o.nombre}</option>)}
            </Selector>
          </div>
        )}
        {empresas.length > 1 && vista !== "cargas" && vista !== "empresas" && (
          <div className="flex items-center gap-3">
            <label htmlFor="empresa" className="text-sm text-texto-3">Empresa</label>
            <Selector id="empresa" className="w-72" value={empresa?.id ?? ""}
              onChange={(e) => cambiar({ empresa: e.target.value || null })}>
              {vista === "tablero" && <option value="">Todas las empresas</option>}
              {empresas.map((e) => <option key={e.id} value={e.id}>{e.nombre} · {entero(e.transacciones)} mov.</option>)}
            </Selector>
          </div>
        )}
        </div>
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
        : vista === "empresas" ? <VistaEmpresas alCambiar={resumen.recargar} organizacionId={orgParam || null}
            organizaciones={orgs.datos?.organizaciones ?? []} puedeMover={sesion.rol === "super_admin"} />
        : resumen.cargando && !resumen.datos ? <Esqueleto className="h-96 w-full rounded-tarjeta" />
        : enCartera ? (
          <>
            {opcionesCartera.datos && <BarraFiltros filtros={filtros} opciones={opcionesCartera.datos} onCambio={ponerFiltros} />}
            {!filtros ? <Esqueleto className="h-96 w-full rounded-tarjeta" />
              : <VistaCartera filtros={filtros} organizacionId={orgParam || null} esCliente={esCliente}
                  onAbrir={(id) => cambiar({ empresa: String(id) })} />}
          </>
        )
        : !empresa ? (
          <Tarjeta>
            <Vacio icono={<Database className="size-8" />} titulo="Aún no hay transacciones cargadas"
              texto={esCliente ? "Todavía no hay transacciones disponibles para su organización. Si cree que es un error, comuníquese con su oficial de cumplimiento."
                : "Cuando se cargue el «Historial de pagos» de AdamoPay de una empresa —automáticamente desde OneDrive o de forma manual— verá aquí su tablero."}
              accion={esCliente ? undefined : <Boton onClick={() => cambiar({ vista: "cargas" })}><RefreshCw className="size-4" />Ir a Cargas</Boton>} />
          </Tarjeta>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              {vista === "tablero" && empresas.length > 1 && (
                <button onClick={() => cambiar({ empresa: null })}
                  className="mr-2 inline-flex items-center gap-1.5 rounded-lg border border-borde-fuerte px-2.5 py-1 text-[13px] text-texto-2 hover:border-texto-3 hover:text-texto">
                  <ArrowLeft className="size-3.5" aria-hidden />Todas las empresas
                </button>
              )}
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
