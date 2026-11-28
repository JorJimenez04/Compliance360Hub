"use client";

import { Suspense } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { Esqueleto, Insignia, tonoRiesgo } from "@/components/ui/basicos";
import { useDatos } from "@/lib/useDatos";
import type { Ficha } from "@/lib/tipos";
import { cn } from "@/lib/cn";
import FichaOrganizacion from "./ficha";
import ClientesOrganizacion from "./clientes";
import AliadosOrganizacion from "./aliados";
import RequerimientosOrganizacion from "./requerimientos";
import ReportesUiaf from "./reportes-uiaf";
import CarpetaCompliance from "./carpeta-compliance";
import { ListaAlertas } from "@/components/cumplimiento/alertas";

const PESTANAS = [
  { id: "clientes", nombre: "Clientes" },
  { id: "aliados", nombre: "Aliados bancarios" },
  { id: "requerimientos", nombre: "Requerimientos" },
  { id: "reportes", nombre: "Reportes UIAF" },
  { id: "alertas", nombre: "Alertas y casos" },
  { id: "ficha", nombre: "Ficha de la organización" },
] as const;

function Vista({ id }: { id: number }) {
  const params = useSearchParams();
  const router = useRouter();
  const ruta = usePathname();
  const ficha = useDatos<Ficha>(`/api/organizaciones/${id}`);
  const pestana = PESTANAS.find((p) => p.id === params.get("tab"))?.id ?? "clientes";
  const ir = (t: string) => router.replace(`${ruta}?tab=${t}`, { scroll: false });

  return (
    <div className="space-y-6">
      <div>
        <Link href="/organizaciones" className="mb-2 inline-flex items-center gap-1.5 text-sm text-texto-3 hover:text-texto">
          <ArrowLeft className="size-4" aria-hidden />Organizaciones</Link>
        {!ficha.datos ? <Esqueleto className="h-9 w-64" /> : (
          <>
            <h1 className="text-2xl font-semibold tracking-tight">{ficha.datos.nombre}</h1>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-texto-3">
              {ficha.datos.nit && <span>NIT {ficha.datos.nit}</span>}
              <Insignia tono={tonoRiesgo(ficha.datos.nivel_riesgo)}>Riesgo {ficha.datos.nivel_riesgo}</Insignia>
              {ficha.datos.oficial_principal && <span>Oficial: {ficha.datos.oficial_principal}</span>}
              {!ficha.datos.activa && <Insignia>Inactiva</Insignia>}
            </div>
          </>
        )}
      </div>
      <div className="flex gap-1 overflow-x-auto border-b border-borde" role="tablist">
        {PESTANAS.map((p) => (
          <button key={p.id} role="tab" aria-selected={pestana === p.id} onClick={() => ir(p.id)}
            className={cn("-mb-px whitespace-nowrap border-b-2 px-3.5 pb-3 pt-1 text-sm transition-colors",
              pestana === p.id ? "border-acento font-medium text-texto" : "border-transparent text-texto-3 hover:text-texto-2")}>
            {p.nombre}
          </button>
        ))}
      </div>
      {pestana === "clientes" ? <ClientesOrganizacion organizacionId={id} />
        : pestana === "aliados" ? <AliadosOrganizacion organizacionId={id} nombre={ficha.datos?.nombre} />
        : pestana === "reportes" ? <ReportesUiaf organizacionId={id} />
        : pestana === "requerimientos" ? <RequerimientosOrganizacion key={`${params.get("req")}-${params.get("nuevo")}`} organizacionId={id} nombre={ficha.datos?.nombre}
            abrir={params.get("req") ? Number(params.get("req")) : null} prellenar={params.get("nuevo")} />
        : pestana === "alertas" ? <ListaAlertas ruta={`/api/organizaciones/${id}/alertas`} />
        : <div className="space-y-6"><CarpetaCompliance organizacionId={id} /><FichaOrganizacion id={id} embebida /></div>}
    </div>
  );
}

export default function OrganizacionVista({ id }: { id: number }) {
  return <Suspense><Vista id={id} /></Suspense>;
}
