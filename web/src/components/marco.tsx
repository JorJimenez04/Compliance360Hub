"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Activity, Building2, ExternalLink, LayoutDashboard, Users, Loader2, LogOut, Menu, X } from "lucide-react";
import { api, enviar, ErrorApi } from "@/lib/api";
import { ContextoSesion } from "@/lib/sesion";
import { ROLES_EXTERNOS, type Perfil } from "@/lib/tipos";
import { cn } from "@/lib/cn";

const ROLES: Record<string, string> = {
  super_admin: "Superadministrador", admin: "Administrador", compliance: "Cumplimiento",
  comercial: "Comercial", auditor: "Auditor", consulta: "Consulta", cliente: "Cliente", junta: "Junta directiva",
};

// Módulos ya migrados a la nueva interfaz. El resto sigue en la app actual (Streamlit).
const SECCIONES = [
  { titulo: "Gestión", items: [{ modulo: "junta", nombre: "Tablero ejecutivo", href: "/junta", icono: LayoutDashboard }] },
  { titulo: "Monitoreo", items: [{ modulo: "monitoreo", nombre: "Monitoreo transaccional", href: "/monitoreo", icono: Activity }] },
  { titulo: "Administración", items: [
    { modulo: "organizaciones", nombre: "Organizaciones", href: "/organizaciones", icono: Building2 },
    { modulo: "usuarios", nombre: "Usuarios", href: "/usuarios", icono: Users },
  ] },
] as const;

const APP_CLASICA = process.env.NEXT_PUBLIC_APP_CLASICA_URL;

export default function Marco({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const ruta = usePathname();
  const [perfil, setPerfil] = useState<Perfil | null>(null);
  const [menuAbierto, setMenuAbierto] = useState(false);
  const [falloServidor, setFalloServidor] = useState(false);
  const [intento, setIntento] = useState(0);

  useEffect(() => {
    setFalloServidor(false);
    api<Perfil>("/api/auth/yo")
      .then(setPerfil)
      .catch((e) => {
        if (e instanceof ErrorApi && e.estado === 401) router.replace(`/login?siguiente=${encodeURIComponent(ruta)}`);
        else setFalloServidor(true);
      });
  }, [router, ruta, intento]);

  useEffect(() => setMenuAbierto(false), [ruta]);

  async function salir() {
    try { await enviar("/api/auth/logout"); } finally { router.replace("/login"); }
  }

  if (!perfil && falloServidor)
    return (
      <div className="grid min-h-dvh place-items-center px-4 text-center">
        <div className="max-w-sm space-y-3">
          <p className="font-medium">No se pudo conectar con el servidor.</p>
          <p className="text-sm text-texto-3">Verifique que la API esté en ejecución e intente de nuevo.</p>
          <button onClick={() => setIntento((n) => n + 1)} className="rounded-lg border border-acento/30 bg-acento-tenue px-4 py-2 text-sm font-medium text-acento">
            Reintentar
          </button>
        </div>
      </div>
    );

  if (!perfil)
    return <div className="grid min-h-dvh place-items-center"><Loader2 className="size-5 animate-spin text-texto-3" aria-label="Cargando" /></div>;

  // Una ruta fuera de los módulos del perfil (p. ej. la junta abriendo /monitoreo por un enlace viejo)
  // vuelve al inicio, que lo lleva a su módulo. La API igual lo rechazaría: esto evita una pantalla de error.
  const rutaPermitida = ruta === "/" || SECCIONES.some((s) => s.items.some((i) => ruta.startsWith(i.href) && perfil.modulos.includes(i.modulo)));
  if (!rutaPermitida) {
    if (typeof window !== "undefined") router.replace("/");
    return <div className="grid min-h-dvh place-items-center"><Loader2 className="size-5 animate-spin text-texto-3" aria-label="Cargando" /></div>;
  }

  const iniciales = perfil.nombre.split(/\s+/).slice(0, 2).map((p) => p[0]).join("").toUpperCase();

  const barra = (
    <nav className="flex h-full flex-col" aria-label="Navegación principal">
      <div className="flex h-16 items-center gap-2.5 px-5">
        <div className="grid size-8 place-items-center rounded-lg border border-acento/30 bg-acento-tenue">
          <span className="text-sm font-bold text-acento">C</span>
        </div>
        <span className="font-semibold tracking-tight">Compliance360 <span className="text-texto-3">Hub</span></span>
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto px-3 py-4">
        {SECCIONES.map((s) => {
          const items = s.items.filter((i) => perfil.modulos.includes(i.modulo));
          if (!items.length) return null;
          return (
            <div key={s.titulo}>
              <p className="mb-1.5 px-2 text-[11px] font-semibold uppercase tracking-wider text-texto-3">{s.titulo}</p>
              {items.map((i) => {
                const activo = ruta.startsWith(i.href);
                return (
                  <Link key={i.href} href={i.href} aria-current={activo ? "page" : undefined}
                    className={cn("flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors",
                      activo ? "bg-acento-tenue text-acento" : "text-texto-2 hover:bg-panel-2 hover:text-texto")}>
                    <i.icono className="size-4" aria-hidden />{i.nombre}
                  </Link>
                );
              })}
            </div>
          );
        })}
        {APP_CLASICA && !ROLES_EXTERNOS.includes(perfil.rol) && (
          <div>
            <p className="mb-1.5 px-2 text-[11px] font-semibold uppercase tracking-wider text-texto-3">Otros módulos</p>
            <a href={APP_CLASICA} target="_blank" rel="noopener"
              className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-texto-2 hover:bg-panel-2 hover:text-texto">
              <ExternalLink className="size-4" aria-hidden />Aliados, clientes y más
            </a>
          </div>
        )}
      </div>

      <div className="border-t border-borde p-3">
        <div className="flex items-center gap-3 rounded-lg px-2 py-2">
          <div className="grid size-8 shrink-0 place-items-center rounded-full bg-panel-2 text-xs font-semibold text-texto-2">{iniciales}</div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{perfil.nombre}</p>
            <p className="truncate text-xs text-texto-3">
              {ROLES[perfil.rol] ?? perfil.rol}{perfil.organizacion?.nombre ? ` · ${perfil.organizacion.nombre}` : ""}
            </p>
          </div>
          <button onClick={salir} title="Cerrar sesión" aria-label="Cerrar sesión"
            className="rounded-md p-1.5 text-texto-3 hover:bg-panel-2 hover:text-texto">
            <LogOut className="size-4" />
          </button>
        </div>
      </div>
    </nav>
  );

  return (
    <ContextoSesion.Provider value={perfil}>
      <div className="min-h-dvh lg:pl-64">
        <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-borde bg-panel lg:block">{barra}</aside>

        {menuAbierto && (
          <div className="fixed inset-0 z-40 lg:hidden">
            <div className="absolute inset-0 bg-black/60" onClick={() => setMenuAbierto(false)} />
            <aside className="absolute inset-y-0 left-0 w-72 border-r border-borde bg-panel">
              <button onClick={() => setMenuAbierto(false)} aria-label="Cerrar menú" className="absolute right-3 top-4 p-1.5 text-texto-3"><X className="size-5" /></button>
              {barra}
            </aside>
          </div>
        )}

        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-borde bg-fondo/90 px-4 backdrop-blur lg:hidden">
          <button onClick={() => setMenuAbierto(true)} aria-label="Abrir menú" className="p-1.5 text-texto-2"><Menu className="size-5" /></button>
          <span className="font-semibold">Compliance360 Hub</span>
        </header>

        <main className="mx-auto max-w-[1440px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{children}</main>
      </div>
    </ContextoSesion.Provider>
  );
}
