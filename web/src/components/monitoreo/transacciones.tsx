"use client";

import { Fragment, useEffect, useState } from "react";
import { AlertTriangle, ChevronDown, ChevronLeft, ChevronRight, Download, Inbox, Search } from "lucide-react";
import { Aviso, Boton, Entrada, Esqueleto, Insignia, Tarjeta, Vacio } from "@/components/ui/basicos";
import { query } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";
import { useSesion } from "@/lib/sesion";
import { entero, fechaHora, moneda } from "@/lib/formato";
import type { PaginaTx, Transaccion } from "@/lib/tipos";
import { cn } from "@/lib/cn";
import { paramsFiltros, type Filtros } from "./filtros";

const TAMANO = 50;

function tonoMovimiento(t: Transaccion) {
  const m = t.movimiento.toLowerCase();
  if (m.includes("devol")) return "serio" as const;
  if (m.includes("fondeo") || m.includes("recarga")) return "acento" as const;
  if (t.exitosa === false) return "critico" as const;
  return "neutro" as const;
}

export default function VistaTransacciones({ empresaId, filtros }: { empresaId: number; filtros: Filtros }) {
  const esCliente = useSesion().rol === "cliente";
  const [texto, setTexto] = useState("");
  const [buscar, setBuscar] = useState("");
  const [pagina, setPagina] = useState(1);
  const [abierta, setAbierta] = useState<number | null>(null);

  useEffect(() => { const t = setTimeout(() => setBuscar(texto.trim()), 350); return () => clearTimeout(t); }, [texto]);
  useEffect(() => { setPagina(1); setAbierta(null); }, [empresaId, filtros, buscar]);

  const base = { ...paramsFiltros(filtros), texto: buscar };
  const { datos, error, cargando } = useDatos<PaginaTx>(
    `/api/monitoreo/empresas/${empresaId}/transacciones${query({ ...base, pagina, tamano: TAMANO })}`);
  const paginas = datos ? Math.max(1, Math.ceil(datos.total / TAMANO)) : 1;

  return (
    <Tarjeta>
      <div className="flex flex-col gap-3 border-b border-borde px-5 py-4 md:flex-row md:items-center md:justify-between">
        <div className="relative w-full md:max-w-sm">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-texto-3" aria-hidden />
          <Entrada value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Buscar beneficiario, documento, referencia o descripción"
            className="pl-9" aria-label="Buscar transacciones" />
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[13px] text-texto-3">{datos ? `${entero(datos.total)} movimientos` : "…"}</span>
          {!esCliente && (
            <a href={`/api/monitoreo/empresas/${empresaId}/transacciones.csv${query(base)}`} download
              title="Descarga con documentos y cuentas completos. Queda registrada en la auditoría.">
              <Boton type="button" tabIndex={-1}><Download className="size-4" />Descargar CSV</Boton>
            </a>
          )}
        </div>
      </div>

      {error && <div className="p-5"><Aviso tono="critico" icono={<AlertTriangle className="size-4" />}>{error}</Aviso></div>}

      {!datos && cargando ? <div className="space-y-2 p-5">{Array.from({ length: 8 }, (_, i) => <Esqueleto key={i} className="h-10" />)}</div>
        : datos && datos.total === 0 ? <Vacio icono={<Inbox className="size-8" />} titulo="No hay movimientos con estos filtros" texto="Pruebe con otro período, otro estado u otra búsqueda." />
        : datos && (
          <div className={cn("overflow-x-auto transition-opacity", cargando && "opacity-60")}>
            <table className="w-full min-w-[960px] text-[13px]">
              <thead>
                <tr className="text-left text-texto-3">
                  <th className="w-8" />
                  <th className="px-3 py-2.5 font-medium">Fecha</th><th className="px-3 py-2.5 font-medium">Movimiento</th>
                  <th className="px-3 py-2.5 font-medium">Beneficiario</th><th className="px-3 py-2.5 font-medium">Banco</th>
                  <th className="px-3 py-2.5 font-medium">Cuenta</th><th className="px-3 py-2.5 text-right font-medium">Monto</th>
                  <th className="px-3 py-2.5 text-right font-medium">Saldo</th><th className="px-3 py-2.5 font-medium">Estado</th>
                </tr>
              </thead>
              <tbody>
                {datos.filas.map((t, i) => (
                  <Fragment key={i}>
                    <tr onClick={() => setAbierta(abierta === i ? null : i)} aria-expanded={abierta === i}
                      className="cursor-pointer border-t border-borde/70 hover:bg-panel-2/60">
                      <td className="pl-3 text-texto-3"><ChevronDown className={cn("size-4 transition-transform", abierta !== i && "-rotate-90")} aria-hidden /></td>
                      <td className="whitespace-nowrap px-3 py-2.5 text-texto-2">{fechaHora(t.fecha_hora)}</td>
                      <td className="px-3 py-2.5"><Insignia tono={tonoMovimiento(t)} className="capitalize">{t.movimiento}</Insignia></td>
                      <td className="px-3 py-2.5"><span className="block max-w-[240px] truncate">{t.beneficiario ?? "—"}</span>
                        <span className="mono text-[12px] text-texto-3">{[t.tipo_identificacion, t.id_beneficiario].filter(Boolean).join(" ") || "—"}</span></td>
                      <td className="px-3 py-2.5 text-texto-2">{t.banco ?? "—"}</td>
                      <td className="mono px-3 py-2.5 text-texto-3">{t.numero_cuenta ?? "—"}</td>
                      <td className="cifra px-3 py-2.5 text-right text-texto">{moneda(t.monto)}</td>
                      <td className="cifra px-3 py-2.5 text-right text-texto-3">{moneda(t.saldo)}</td>
                      <td className="px-3 py-2.5 text-texto-2">{t.estado ?? "—"}</td>
                    </tr>
                    {abierta === i && (
                      <tr className="bg-fondo/60">
                        <td />
                        <td colSpan={8} className="px-3 pb-4 pt-1">
                          <dl className="grid gap-x-8 gap-y-2 text-[13px] sm:grid-cols-2 lg:grid-cols-4">
                            <Dato n="ID de transacción" v={t.id_transaccion} mono />
                            <Dato n="Referencia externa" v={t.referencia_externa} mono />
                            <Dato n="Tipo en AdamoPay" v={t.tipo_transaccion} />
                            <Dato n="Comisión" v={t.comision == null ? null : moneda(t.comision)} mono />
                            <Dato n="Tipo de cuenta" v={t.tipo_cuenta} />
                            {t.motivo_devolucion && <Dato n="Motivo de devolución" v={t.motivo_devolucion} />}
                            <div className="sm:col-span-2 lg:col-span-4"><Dato n="Descripción" v={t.descripcion} /></div>
                          </dl>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}

      {datos && datos.total > TAMANO && (
        <div className="flex items-center justify-between border-t border-borde px-5 py-3 text-[13px] text-texto-3">
          <span>Página {entero(pagina)} de {entero(paginas)}</span>
          <div className="flex gap-2">
            <Boton variante="fantasma" disabled={pagina <= 1} onClick={() => setPagina(pagina - 1)}><ChevronLeft className="size-4" />Anterior</Boton>
            <Boton variante="fantasma" disabled={pagina >= paginas} onClick={() => setPagina(pagina + 1)}>Siguiente<ChevronRight className="size-4" /></Boton>
          </div>
        </div>
      )}
    </Tarjeta>
  );
}

function Dato({ n, v, mono }: { n: string; v: string | null | undefined; mono?: boolean }) {
  return <div><dt className="text-texto-3">{n}</dt><dd className={cn("break-words text-texto-2", mono && "mono")}>{v || "—"}</dd></div>;
}
