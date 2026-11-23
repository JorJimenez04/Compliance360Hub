import { Suspense } from "react";
import type { Metadata } from "next";
import FormularioLogin from "./formulario";

export const metadata: Metadata = { title: "Ingresar" };

export default function PaginaLogin() {
  return (
    <main className="relative grid min-h-dvh place-items-center overflow-hidden px-4">
      <div aria-hidden className="pointer-events-none absolute inset-0"
        style={{ background: "radial-gradient(600px 380px at 50% 18%, #5fe9d014, transparent 70%)" }} />
      <div className="relative w-full max-w-[380px]">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 grid size-11 place-items-center rounded-xl border border-acento/30 bg-acento-tenue">
            <span className="text-lg font-bold text-acento">C</span>
          </div>
          <h1 className="text-xl font-semibold tracking-tight">Compliance360 Hub</h1>
          <p className="mt-1 text-sm text-texto-3">Ingrese con su usuario</p>
        </div>
        <Suspense>
          <FormularioLogin />
        </Suspense>
        <p className="mt-6 text-center text-xs text-texto-3">Acceso restringido y auditado</p>
      </div>
    </main>
  );
}
