"use client";

import { Fragment, useMemo, useState } from "react";
import { AlertTriangle, ChevronDown, ChevronRight, Users } from "lucide-react";
import { Aviso, Entrada, Esqueleto, Insignia, Tarjeta, TituloTarjeta, Vacio } from "@/components/ui/basicos";
import { useDatos } from "@/lib/useDatos";
import { entero, fecha, fechaHora, moneda, monedaCorta, porcentaje } from "@/lib/formato";
import { cn } from "@/lib/cn";
import { Kpi } from "@/components/monitoreo/tablero";

interface Beneficiario {
  id_beneficiario: string; nombre: string | null; otros_nombres: string[]; tipo_identificacion: string | null;
  tipo_persona: string | null; pagos: number; rechazos: number; monto: number; participacion: number;
  ticket_promedio: number; primer_pago: string | null; ultimo_pago: string | null; bancos: string[];
  cuentas: string[]; empresas: string[]; senales: string[];
}
interface Respuesta {
  total_beneficiarios: number; monto_total: number; pagos_total: number; desde: string | null; hasta: string | null;
  senales: Record<string, string>; beneficiarios: Beneficiario[];
}
interface Movimiento {
  fecha_hora: string; empresa: string; id_transaccion: string; tipo_transaccion: string; estado: string;
  exitosa: boolean; monto: number; banco: string | null; cuenta: string | null; nombre: string | null;
}

const POR_PAGINA = 50;

function Movimientos({ clienteId, idb }: { clienteId: number; idb: string }) {
  const { datos, error } = useDatos<{ movimientos: Movimiento[] }>(
    `/api/clientes/${clienteId}/beneficiarios/${encodeURIComponent(idb)}/movimientos`);
  if (error) return <p className="text-sm text-critico">{error}</p>;
  if (!datos) return <Esqueleto className="h-24" />;
  return (
    <div className="max-h-80 overflow-y-auto rounded-lg border border-borde/60 px-2">
    {datos.movimientos.length >= 200 && <p className="py-1 text-xs text-texto-3">Se muestran los 200 movimientos más recientes.</p>}
    <table className="w-full text-[12px]">
      <thead className="sticky top-0 bg-panel"><tr className="text-left text-texto-3">
        <th className="py-1 pr-3 font-medium">Fecha</th><th className="py-1 pr-3 font-medium">Transacción</th>
        <th className="py-1 pr-3 font-medium">Tipo</th><th className="py-1 pr-3 font-medium">Estado</th>
        <th className="py-1 pr-3 text-right font-medium">Monto</th><th className="py-1 pr-3 font-medium">Banco · cuenta</th>
        <th className="py-1 font-medium">Nombre reportado</th></tr></thead>
      <tbody>
        {datos.movimientos.map((m) => (
          <tr key={m.id_transaccion + m.fecha_hora} className="border-t border-borde/50">
            <td className="py-1 pr-3 text-texto-2">{fechaHora(m.fecha_hora)}</td>
            <td className="py-1 pr-3 font-mono text-texto-3">{m.id_transaccion}</td>
            <td className="py-1 pr-3 text-texto-2">{m.tipo_transaccion}</td>
            <td className={cn("py-1 pr-3", m.exitosa ? "text-texto-2" : "text-alerta")}>{m.estado}</td>
            <td className="cifra py-1 pr-3 text-right">{moneda(m.monto)}</td>
            <td className="py-1 pr-3 text-texto-2">{[m.banco, m.cuenta].filter(Boolean).join(" · ")}</td>
            <td className="py-1 text-texto-3">{m.nombre}</td>
          </tr>
        ))}
      </tbody>
    </table>
    </div>
  );
}

/** A quién le paga el cliente: beneficiarios tomados de sus transacciones, con señales de revisión. */
export default function BeneficiariosCliente({ clienteId }: { clienteId: number }) {
  const { datos, error } = useDatos<Respuesta>(`/api/clientes/${clienteId}/beneficiarios`);
  const [buscar, setBuscar] = useState("");
  const [soloSenales, setSoloSenales] = useState(false);
  const [abierto, setAbierto] = useState<string | null>(null);
  const [pagina, setPagina] = useState(1);

  const filas = useMemo(() => {
    const f = buscar.trim().toLowerCase();
    return (datos?.beneficiarios ?? []).filter((b) => (!soloSenales || b.senales.length)
      && (!f || b.id_beneficiario.includes(f) || (b.nombre ?? "").toLowerCase().includes(f)));
  }, [datos, buscar, soloSenales]);

  if (error) return <Aviso tono="critico" icono={<AlertTriangle className="size-4" />}>{error}</Aviso>;
  if (!datos) return <Esqueleto className="h-96" />;
  if (!datos.total_beneficiarios)
    return <Tarjeta><Vacio icono={<Users className="size-8" />} titulo="Sin beneficiarios"
      texto="Este cliente aún no tiene pagos a beneficiarios en sus transacciones." /></Tarjeta>;

  const conSenales = datos.beneficiarios.filter((b) => b.senales.length).length;
  const top10 = datos.beneficiarios.slice(0, 10).reduce((s, b) => s + b.participacion, 0);
  const visibles = filas.slice(0, pagina * POR_PAGINA);

  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi titulo="Beneficiarios" valor={entero(datos.total_beneficiarios)} detalle={<>{fecha(datos.desde)} – {fecha(datos.hasta)}</>} />
        <Kpi titulo="Monto pagado" valor={monedaCorta(datos.monto_total)} detalle={<>{entero(datos.pagos_total)} pagos exitosos</>} />
        <Kpi titulo="Concentración top 10" valor={porcentaje(top10)} detalle="del monto pagado" />
        <Kpi titulo="Con señales de revisión" valor={entero(conSenales)} detalle={conSenales ? "revise abajo" : "ninguna señal"} />
      </div>

      <Tarjeta>
        <TituloTarjeta titulo="Beneficiarios del cliente" descripcion="Tomados de sus transacciones, agrupados por documento. Abra uno para ver sus movimientos. Las cuentas se muestran enmascaradas."
          accion={<div className="flex items-center gap-2">
            <button type="button" onClick={() => { setSoloSenales(!soloSenales); setPagina(1); }}
              className={cn("rounded-md border px-2.5 py-1 text-xs", soloSenales ? "border-acento bg-acento-tenue text-texto" : "border-borde-fuerte text-texto-3")}>
              Solo con señales</button>
            <Entrada aria-label="Buscar beneficiario" placeholder="Nombre o documento…" className="w-56" value={buscar}
              onChange={(e) => { setBuscar(e.target.value); setPagina(1); }} />
          </div>} />
        <div className="overflow-x-auto px-2 pb-3 pt-3">
          <table className="w-full min-w-[960px] text-[13px]">
            <thead><tr className="text-left text-texto-3">
              <th className="w-6 px-2 py-2" /><th className="px-2 py-2 font-medium">Beneficiario</th>
              <th className="px-2 py-2 text-right font-medium">Pagos</th><th className="px-2 py-2 text-right font-medium">Monto</th>
              <th className="px-2 py-2 text-right font-medium">Participación</th><th className="px-2 py-2 font-medium">Primer / último pago</th>
              <th className="px-2 py-2 font-medium">Bancos · cuentas</th><th className="px-2 py-2 font-medium">Señales</th></tr></thead>
            <tbody>
              {visibles.map((b) => {
                const ver = abierto === b.id_beneficiario;
                return (
                  <Fragment key={b.id_beneficiario}>
                    <tr className="cursor-pointer border-t border-borde/70 hover:bg-panel-2/60" onClick={() => setAbierto(ver ? null : b.id_beneficiario)}>
                      <td className="px-2 py-2.5 text-texto-3">{ver ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}</td>
                      <td className="px-2 py-2.5">
                        <p className="font-medium text-texto">{b.nombre ?? "Sin nombre"}</p>
                        <p className="text-xs text-texto-3">{b.tipo_identificacion ?? "Doc."} {b.id_beneficiario}{b.tipo_persona && <> · {b.tipo_persona}</>}</p>
                      </td>
                      <td className="cifra whitespace-nowrap px-2 py-2.5 text-right">{entero(b.pagos)}{b.rechazos > 0 && <span className="ml-1 text-xs text-alerta">+{b.rechazos} rech.</span>}</td>
                      <td className="cifra whitespace-nowrap px-2 py-2.5 text-right">{monedaCorta(b.monto)}</td>
                      <td className="cifra whitespace-nowrap px-2 py-2.5 text-right">{porcentaje(b.participacion)}</td>
                      <td className="whitespace-nowrap px-2 py-2.5 text-texto-2">{fecha(b.primer_pago)} – {fecha(b.ultimo_pago)}</td>
                      <td className="px-2 py-2.5 text-texto-2">{b.bancos.join(", ") || "—"}<span className="text-texto-3"> · {b.cuentas.length} cta.</span></td>
                      <td className="px-2 py-2.5">
                        <div className="flex flex-wrap gap-1">
                          {b.senales.map((s) => <span key={s} title={datos.senales[s]}><Insignia tono="serio">{datos.senales[s]}</Insignia></span>)}
                        </div>
                      </td>
                    </tr>
                    {ver && (
                      <tr className="bg-fondo/40">
                        <td />
                        <td colSpan={7} className="space-y-2 px-2 pb-3 pt-1">
                          <p className="text-xs text-texto-3">
                            Ticket promedio {moneda(b.ticket_promedio)} · Cuentas: {b.cuentas.join(", ") || "—"}
                            {b.otros_nombres.length > 0 && <> · También reportado como: {b.otros_nombres.join(", ")}</>}
                            {b.empresas.length > 1 && <> · Empresas: {b.empresas.join(", ")}</>}
                          </p>
                          <Movimientos clienteId={clienteId} idb={b.id_beneficiario} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
          {!filas.length && <p className="px-3 py-6 text-center text-sm text-texto-3">Ningún beneficiario coincide.</p>}
          {filas.length > visibles.length && (
            <div className="pt-3 text-center">
              <button type="button" className="text-sm text-acento hover:underline" onClick={() => setPagina(pagina + 1)}>
                Ver más ({entero(filas.length - visibles.length)} restantes)</button>
            </div>
          )}
        </div>
      </Tarjeta>
    </div>
  );
}
