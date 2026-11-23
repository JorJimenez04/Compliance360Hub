"use client";

import { Activity, FileCheck2, LayoutDashboard, ShieldCheck } from "lucide-react";
import { Tarjeta, TituloTarjeta, Vacio } from "@/components/ui/basicos";
import { useSesion } from "@/lib/sesion";

// Fase 4: el tablero ejecutivo se construye sobre el expediente (fase 2) y la reportería UIAF (fase 3).
// Mientras tanto, la junta ya puede ingresar y ve qué va a encontrar aquí.
const SECCIONES = [
  { icono: Activity, titulo: "Pagos", texto: "Volumen transaccional por empresa, riel y periodo, con su tendencia." },
  { icono: ShieldCheck, titulo: "Gestión de cumplimiento", texto: "Alertas atendidas y tiempos de respuesta, reportes a la UIAF presentados a tiempo." },
  { icono: FileCheck2, titulo: "Expedientes", texto: "Clientes listos para un requerimiento bancario, documentos por vencer y vencidos." },
];

export default function Junta() {
  const { organizacion } = useSesion();
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Tablero ejecutivo</h1>
        <p className="mt-1 text-sm text-texto-3">{organizacion?.nombre ?? "Su organización"} · cifras consolidadas, sin datos personales.</p>
      </div>
      <Tarjeta>
        <Vacio icono={<LayoutDashboard className="size-8" />} titulo="El tablero ejecutivo está en construcción"
          texto="Aquí verá la gestión de pagos y de cumplimiento de su organización. Le avisaremos cuando esté disponible." />
      </Tarjeta>
      <div className="grid gap-4 md:grid-cols-3">
        {SECCIONES.map((s) => (
          <Tarjeta key={s.titulo} className="pb-4">
            <TituloTarjeta titulo={s.titulo} descripcion={s.texto} accion={<s.icono className="size-5 text-texto-3" aria-hidden />} />
          </Tarjeta>
        ))}
      </div>
    </div>
  );
}
