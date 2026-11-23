import type { Metadata } from "next";
import CatalogoCumplimiento from "@/components/cumplimiento/catalogo";

export const metadata: Metadata = { title: "Catálogo de cumplimiento" };

export default function PaginaCatalogo() {
  return <CatalogoCumplimiento />;
}
