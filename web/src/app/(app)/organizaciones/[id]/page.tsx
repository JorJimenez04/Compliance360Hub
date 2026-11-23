import type { Metadata } from "next";
import FichaOrganizacion from "@/components/organizaciones/ficha";

export const metadata: Metadata = { title: "Ficha de la organización" };

export default async function PaginaFicha({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <FichaOrganizacion id={Number(id)} />;
}
