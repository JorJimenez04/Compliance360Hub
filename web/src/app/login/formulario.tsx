"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertCircle } from "lucide-react";
import { Boton, Entrada, Etiqueta, Tarjeta } from "@/components/ui/basicos";
import { enviar } from "@/lib/api";

export default function FormularioLogin() {
  const router = useRouter();
  const params = useSearchParams();
  const [usuario, setUsuario] = useState("");
  const [clave, setClave] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);

  async function ingresar(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setCargando(true);
    try {
      await enviar("/api/auth/login", { username: usuario.trim(), password: clave });
      const sig = params.get("siguiente");
      router.replace(sig && sig.startsWith("/") && !sig.startsWith("//") ? sig : "/");   // "/" lleva a cada perfil a su primer módulo
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo ingresar.");
      setClave("");
      setCargando(false);
    }
  }

  return (
    <Tarjeta className="p-6">
      <form onSubmit={ingresar} className="space-y-4" noValidate>
        <div>
          <Etiqueta htmlFor="usuario">Usuario</Etiqueta>
          <Entrada id="usuario" autoComplete="username" autoFocus required value={usuario}
            onChange={(e) => setUsuario(e.target.value)} />
        </div>
        <div>
          <Etiqueta htmlFor="clave">Contraseña</Etiqueta>
          <Entrada id="clave" type="password" autoComplete="current-password" required value={clave}
            onChange={(e) => setClave(e.target.value)} />
        </div>
        {error && (
          <p role="alert" className="flex items-start gap-2 text-sm text-critico">
            <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />{error}
          </p>
        )}
        <Boton type="submit" variante="primario" className="h-10 w-full" cargando={cargando}
          disabled={!usuario.trim() || !clave}>Ingresar</Boton>
      </form>
    </Tarjeta>
  );
}
