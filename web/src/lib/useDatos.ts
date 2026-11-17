"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

/** Carga una ruta GET de la API; vuelve a cargar cuando cambia la ruta. */
export function useDatos<T>(ruta: string | null) {
  const [datos, setDatos] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(Boolean(ruta));
  const vigente = useRef(0);

  const cargar = useCallback(async () => {
    if (!ruta) return;
    const n = ++vigente.current;
    setCargando(true);
    setError(null);
    try {
      const d = await api<T>(ruta);
      if (n === vigente.current) setDatos(d);
    } catch (e) {
      if (n === vigente.current) setError(e instanceof Error ? e.message : "Error al cargar.");
    } finally {
      if (n === vigente.current) setCargando(false);
    }
  }, [ruta]);

  useEffect(() => { void cargar(); }, [cargar]);

  return { datos, error, cargando, recargar: cargar };
}
