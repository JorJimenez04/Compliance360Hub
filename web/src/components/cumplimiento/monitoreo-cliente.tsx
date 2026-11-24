"use client";

import { useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Activity } from "lucide-react";
import { Esqueleto, Selector, Tarjeta, Vacio } from "@/components/ui/basicos";
import { useDatos } from "@/lib/useDatos";
import type { Opciones } from "@/lib/tipos";
import { cn } from "@/lib/cn";
import { BarraFiltros, filtrosDesdeUrl, type Filtros } from "@/components/monitoreo/filtros";
import VistaTablero from "@/components/monitoreo/tablero";
import VistaTransacciones from "@/components/monitoreo/transacciones";
import VistaRiesgo from "@/components/monitoreo/riesgo";

const VISTAS = [
  { id: "tablero", nombre: "Tablero" },
  { id: "transacciones", nombre: "Transacciones" },
  { id: "riesgo", nombre: "Riesgo" },
] as const;

/** El módulo de Monitoreo transaccional, dentro del perfil del cliente y filtrado a sus empresas. */
export default function MonitoreoCliente({ empresas }: { empresas: { id: number; nombre: string; activa: boolean }[] }) {
  const params = useSearchParams();
  const router = useRouter();
  const ruta = usePathname();
  const idParam = Number(params.get("empresa"));
  const empresa = empresas.find((e) => e.id === idParam) ?? empresas[0];
  const vista = VISTAS.find((v) => v.id === params.get("sub"))?.id ?? "tablero";
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

  if (!empresa)
    return <Tarjeta><Vacio icono={<Activity className="size-8" />} titulo="Sin empresas monitoreadas"
      texto="Este cliente aún no está enlazado con transacciones de AdamoPay." /></Tarjeta>;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex gap-1 rounded-lg border border-borde p-0.5" role="tablist">
          {VISTAS.map((v) => (
            <button key={v.id} role="tab" aria-selected={vista === v.id} onClick={() => cambiar({ sub: v.id === "tablero" ? null : v.id })}
              className={cn("rounded-md px-3 py-1.5 text-sm", vista === v.id ? "bg-panel-2 font-medium text-texto" : "text-texto-3 hover:text-texto-2")}>
              {v.nombre}
            </button>
          ))}
        </div>
        {empresas.length > 1 && (
          <Selector aria-label="Empresa" className="w-64" value={empresa.id} onChange={(e) => cambiar({ empresa: e.target.value })}>
            {empresas.map((e) => <option key={e.id} value={e.id}>{e.nombre}</option>)}
          </Selector>
        )}
      </div>
      {opciones.datos && <BarraFiltros filtros={filtros} opciones={opciones.datos} onCambio={ponerFiltros} />}
      {!opciones.datos ? <Esqueleto className="h-96" />
        : !filtros ? <Tarjeta><Vacio icono={<Activity className="size-8" />} titulo="Sin transacciones cargadas" /></Tarjeta>
        : vista === "tablero" ? <VistaTablero empresaId={empresa.id} filtros={filtros} continuidad={opciones.datos.continuidad} />
        : vista === "transacciones" ? <VistaTransacciones empresaId={empresa.id} filtros={filtros} />
        : <VistaRiesgo empresaId={empresa.id} filtros={filtros} />}
    </div>
  );
}
