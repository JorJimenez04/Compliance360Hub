import type { Metadata } from "next";
import OrganizacionVista from "@/components/organizaciones/organizacion";

export const metadata: Metadata = { title: "Organización" };

export default async function PaginaFicha({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <OrganizacionVista id={Number(id)} />;
}
