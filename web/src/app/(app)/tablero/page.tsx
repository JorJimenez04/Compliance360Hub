import type { Metadata } from "next";
import TableroCumplimiento from "@/components/tablero/tablero";

export const metadata: Metadata = { title: "Tablero de cumplimiento" };

export default function PaginaTablero() {
  return <TableroCumplimiento />;
}
