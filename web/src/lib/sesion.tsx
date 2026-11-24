"use client";

import { createContext, useContext } from "react";
import { ROLES_GESTION, type Perfil } from "./tipos";

export const ContextoSesion = createContext<Perfil | null>(null);

export function useSesion(): Perfil {
  const p = useContext(ContextoSesion);
  if (!p) throw new Error("useSesion fuera de la sesión");
  return p;
}

/** ¿Puede este perfil modificar? (crear, editar, gestionar alertas, revisar carpetas, cargar). */
export function usePuedeGestionar(): boolean {
  return ROLES_GESTION.includes(useSesion().rol);
}
