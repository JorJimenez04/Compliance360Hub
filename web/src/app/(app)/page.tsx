"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSesion } from "@/lib/sesion";

// Cada perfil aterriza en su primer módulo: el director en el tablero de cumplimiento, la junta en el suyo, el resto en Monitoreo.
const RUTAS: Record<string, string> = {
  tablero: "/tablero", junta: "/junta", monitoreo: "/monitoreo", catalogo: "/catalogo", organizaciones: "/organizaciones", usuarios: "/usuarios", auditoria: "/auditoria",
};

export default function Inicio() {
  const { modulos } = useSesion();
  const router = useRouter();
  useEffect(() => {
    const destino = modulos.map((m) => RUTAS[m]).find(Boolean);
    if (destino) router.replace(destino);
  }, [modulos, router]);
  return modulos.length ? null : <p className="text-sm text-texto-3">Su perfil aún no tiene módulos habilitados.</p>;
}
