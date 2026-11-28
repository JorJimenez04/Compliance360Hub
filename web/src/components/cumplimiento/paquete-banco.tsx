"use client";

import { useState } from "react";
import { PackageOpen } from "lucide-react";
import { Aviso, Boton } from "@/components/ui/basicos";
import { ErrorApi } from "@/lib/api";
import { descargar } from "@/lib/descargas";

/** Botón «Paquete para el banco»: ZIP con el resumen KYC en PDF y los documentos del subcliente. */
export function BotonPaqueteBanco({ clienteId, compacto = false }: { clienteId: number; compacto?: boolean }) {
  const [cargando, setCargando] = useState(false);
  const [fallo, setFallo] = useState<string | null>(null);
  async function bajar() {
    setCargando(true); setFallo(null);
    try { await descargar(`/api/clientes/${clienteId}/paquete-banco`, "paquete-banco.zip"); }
    catch (e) { setFallo(e instanceof ErrorApi ? e.message : "No se pudo generar el paquete."); }
    finally { setCargando(false); }
  }
  return (
    <span className="inline-flex flex-col items-end gap-1">
      <Boton className="whitespace-nowrap" variante={compacto ? "fantasma" : "secundario"} cargando={cargando} onClick={bajar}
        title="ZIP con el resumen KYC en PDF y los documentos de su carpeta">
        <PackageOpen className="size-4" aria-hidden />Paquete para el banco</Boton>
      {fallo && <Aviso tono="critico">{fallo}</Aviso>}
    </span>
  );
}
