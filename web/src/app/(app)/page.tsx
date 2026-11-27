"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSesion } from "@/lib/sesion";

// Cada perfil aterriza en su primer módulo: la junta en su tablero, el resto en Monitoreo.
const RUTAS: Record<string, string> = {
  junta: "/junta", monitoreo: "/monitoreo", catalogo: "/catalogo", organizaciones: "/organizaciones", usuarios: "/usuarios", auditoria: "/auditoria",
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
