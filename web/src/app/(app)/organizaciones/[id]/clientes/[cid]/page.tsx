import type { Metadata } from "next";
import Expediente360 from "@/components/cumplimiento/expediente";

export const metadata: Metadata = { title: "Expediente 360" };

export default async function PaginaCliente({ params }: { params: Promise<{ id: string; cid: string }> }) {
  const { id, cid } = await params;
  return <Expediente360 organizacionId={Number(id)} clienteId={Number(cid)} />;
}
