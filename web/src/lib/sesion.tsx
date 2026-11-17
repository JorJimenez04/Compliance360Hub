"use client";

import { createContext, useContext } from "react";
import type { Perfil } from "./tipos";

export const ContextoSesion = createContext<Perfil | null>(null);

export function useSesion(): Perfil {
  const p = useContext(ContextoSesion);
  if (!p) throw new Error("useSesion fuera de la sesión");
  return p;
}
