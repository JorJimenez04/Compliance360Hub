import type { Metadata } from "next";
import Junta from "@/components/junta/junta";

export const metadata: Metadata = { title: "Tablero ejecutivo" };

export default function PaginaJunta() {
  return <Junta />;
}
