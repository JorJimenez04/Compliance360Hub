import type { Metadata } from "next";
import Organizaciones from "@/components/organizaciones/organizaciones";

export const metadata: Metadata = { title: "Organizaciones" };

export default function PaginaOrganizaciones() {
  return <Organizaciones />;
}
