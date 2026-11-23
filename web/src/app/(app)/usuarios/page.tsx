import type { Metadata } from "next";
import Usuarios from "@/components/usuarios/usuarios";

export const metadata: Metadata = { title: "Usuarios" };

export default function PaginaUsuarios() {
  return <Usuarios />;
}
