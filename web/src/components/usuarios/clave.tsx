"use client";

import { useState } from "react";
import { Check, Eye, EyeOff, X } from "lucide-react";
import { Entrada, Etiqueta } from "@/components/ui/basicos";
import { cn } from "@/lib/cn";

export type ModoClave = "generar" | "escribir";

/** Las mismas reglas que valida la API (api/claves.py). */
export function reglasClave(c: string, confirmacion: string) {
  return [
    { ok: c.length >= 12, texto: "Al menos 12 caracteres" },
    { ok: /[a-z]/.test(c) && /[A-Z]/.test(c), texto: "Mayúscula y minúscula" },
    { ok: /\d/.test(c), texto: "Al menos un número" },
    { ok: c.length > 0 && c === c.trim(), texto: "Sin espacios al inicio o al final" },
    { ok: c.length > 0 && c === confirmacion, texto: "Las dos casillas coinciden" },
  ];
}

export const claveValida = (c: string, confirmacion: string) => reglasClave(c, confirmacion).every((r) => r.ok);

export function SelectorModoClave({ modo, onModo }: { modo: ModoClave; onModo: (m: ModoClave) => void }) {
  const opcion = (m: ModoClave, titulo: string, texto: string) => (
    <button type="button" onClick={() => onModo(m)} aria-pressed={modo === m}
      className={cn("rounded-lg border px-3 py-2 text-left transition-colors",
        modo === m ? "border-acento bg-acento-tenue" : "border-borde-fuerte hover:border-acento/60")}>
      <p className="text-sm font-medium text-texto">{titulo}</p>
      <p className="text-xs text-texto-3">{texto}</p>
    </button>
  );
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {opcion("generar", "Generar automáticamente", "La plataforma crea una clave segura y se la muestra una vez.")}
      {opcion("escribir", "Escribirla yo", "Usted define la clave que le entregará al usuario.")}
    </div>
  );
}

export function CampoClave({ idBase, clave, confirmacion, onClave, onConfirmacion }: {
  idBase: string; clave: string; confirmacion: string; onClave: (v: string) => void; onConfirmacion: (v: string) => void;
}) {
  const [ver, setVer] = useState(false);
  const tipo = ver ? "text" : "password";
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div><Etiqueta htmlFor={`${idBase}-1`}>Clave</Etiqueta>
          <div className="relative">
            <Entrada id={`${idBase}-1`} type={tipo} autoComplete="new-password" className="pr-10 font-mono"
              value={clave} onChange={(e) => onClave(e.target.value)} />
            <button type="button" onClick={() => setVer(!ver)} aria-label={ver ? "Ocultar clave" : "Mostrar clave"}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-texto-3 hover:text-texto">
              {ver ? <EyeOff className="size-4" /> : <Eye className="size-4" />}</button>
          </div></div>
        <div><Etiqueta htmlFor={`${idBase}-2`}>Repita la clave</Etiqueta>
          <Entrada id={`${idBase}-2`} type={tipo} autoComplete="new-password" className="font-mono"
            value={confirmacion} onChange={(e) => onConfirmacion(e.target.value)} /></div>
      </div>
      <ul className="grid gap-1 text-xs sm:grid-cols-3">
        {reglasClave(clave, confirmacion).map((r) => (
          <li key={r.texto} className={cn("flex items-center gap-1.5", r.ok ? "text-ok" : "text-texto-3")}>
            {r.ok ? <Check className="size-3.5" aria-hidden /> : <X className="size-3.5" aria-hidden />}{r.texto}</li>
        ))}
      </ul>
    </div>
  );
}
