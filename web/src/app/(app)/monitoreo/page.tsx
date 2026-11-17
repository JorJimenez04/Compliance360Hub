import { Suspense } from "react";
import type { Metadata } from "next";
import Monitoreo from "@/components/monitoreo/monitoreo";

export const metadata: Metadata = { title: "Monitoreo transaccional" };

export default function PaginaMonitoreo() {
  return <Suspense><Monitoreo /></Suspense>;
}
