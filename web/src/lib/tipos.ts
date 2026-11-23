// Contratos de la API (api/rutas/*.py)

export type Modulo = "monitoreo" | "auditoria" | "usuarios" | "organizaciones" | "junta";

export interface Perfil {
  id: number; username: string; nombre: string; rol: string; email: string | null; modulos: Modulo[];
  /** Solo usuarios externos (cliente, junta): su organización. Los internos ven todas. */
  organizacion: { id: number; nombre: string | null } | null;
}

export const ROLES_EXTERNOS = ["cliente", "junta"];

export interface Organizacion {
  id: number; nombre: string; nit?: string | null; activa?: boolean; notas?: string | null;
  empresas?: number; clientes?: number; usuarios?: number; creada?: string | null;
}

export type PerfilGestionado = "cliente" | "junta" | "compliance";
export type Alcance = "organizacion" | "empresas";

export interface UsuarioGestionado {
  id: number; username: string; nombre: string; email: string | null; rol: PerfilGestionado; activo: boolean;
  ultimo_acceso: string | null; organizacion_id: number | null; organizacion: string | null;
  alcance: Alcance | null; empresas_ids: number[]; empresas: string;
}

export interface Empresa {
  id: number; nombre_reporte: string; nombre: string; activa: boolean; enlazada: boolean;
  cliente_id: number | null; razon_social: string | null; nit: string | null;
  nivel_riesgo: string | null; transacciones: number | null;
  /** Solo para internos (al cliente llega null) */
  organizacion_id: number | null;
}

export interface Resumen { ultima_carga: string | null; empresas: Empresa[]; puede_cargar: boolean }

export interface Continuidad {
  movimientos: number; no_inicial: number | null; no_final: number | null; faltantes: number;
  ejemplos_faltantes: string[]; descuadres_saldo: number; ejemplos_descuadre: number[];
  saldos_verificados: number; completa: boolean; parcial: boolean; resumen: string;
}

export interface Opciones { fecha_min: string | null; fecha_max: string | null; estados: string[]; continuidad: Continuidad | null }

export interface Kpis {
  pagos_enviados: number; pagos_exitosos: number; monto_pagado: number; ticket_promedio: number;
  tasa_exito: number; devoluciones: number; monto_devuelto: number; fondeos: number; monto_fondeado: number;
  total_movimientos: number; tasa_devolucion: number;
}

export interface FilaRanking {
  posicion: number; beneficiario: string; id_beneficiario: string | null; pagos: number;
  monto: number; pct: number; ultimo_pago: string | null;
}

export interface Tablero {
  vacio: boolean;
  kpis: Kpis; kpis_anterior: Kpis | null; beneficiarios: number;
  dia_pico: { fecha: string; monto: number } | null;
  granularidad: "Diaria" | "Semanal" | "Mensual";
  serie: { periodo: string; monto: number; pagos: number }[];
  composicion: { clave: string; categoria: string; movimientos: number; monto: number; pct: number }[];
  rangos: { rango: string; pagos: number; monto: number; pct: number }[];
  bancos: { banco: string; pagos: number; monto: number; pct: number }[];
  ranking_monto: FilaRanking[]; ranking_pagos: FilaRanking[];
  actividad: { dias: string[]; horas: number[]; valores: number[][] };
  motivos_devolucion: { motivo: string; devoluciones: number; monto: number; pct: number }[];
  devoluciones_recientes: { fecha_hora: string; beneficiario: string; id_beneficiario: string | null;
    banco: string | null; numero_cuenta: string | null; monto: number; motivo: string }[];
}

export interface Transaccion {
  fecha_hora: string; id_transaccion: string | null; referencia_externa: string | null; tipo_transaccion: string;
  movimiento: string; beneficiario: string | null; tipo_identificacion: string | null; id_beneficiario: string | null;
  banco: string | null; tipo_cuenta: string | null; numero_cuenta: string | null; monto: number;
  comision: number | null; saldo: number | null; estado: string | null; exitosa: boolean | null;
  descripcion: string | null; motivo_devolucion: string | null;
}

export interface PaginaTx { total: number; pagina: number; tamano: number; filas: Transaccion[] }

export interface Alerta {
  id_alerta: string; tipo: string; prioridad: "Crítica" | "Alta" | "Media" | "Baja" | string; titulo: string;
  descripcion: string; accion_requerida: string; requiere_reporte_uiaf: boolean; dias_para_accion: number;
}

export interface Riesgo {
  cliente: string;
  scoring: { score_total: number; score_gafi: number; score_uiaf: number; score_operativo: number;
    nivel_riesgo: string; factores_criticos: string[] };
  alertas: Alerta[];
  matriz_riesgo: { riesgo_inherente: Record<string, number>; riesgo_residual: Record<string, number>;
    controles_aplicados: string[]; gaps_control: string[]; apetito_riesgo_superado: boolean };
  recomendaciones: string[]; requiere_due_diligence_reforzada: boolean; requiere_escalamiento: boolean;
  proximo_review: string;
}

export interface Carga {
  id: number; fecha: string; archivo: string | null; resultado: string; usuario: string | null;
  empresas: number; leidas: number; nuevas: number; actualizadas: number; rechazadas: number;
  faltantes: number; descuadres_saldo: number; mensaje: string | null;
}

export interface Nube {
  configurada: boolean; delegado: boolean; lista: boolean; descripcion: string | null;
  conexion: { cuenta: string; conectado_por: string | null; conectado_en: string | null; renovado_en: string | null } | null;
  revisiones: { id: number; fecha: string; resultado: string; usuario: string | null; mensaje: string | null;
    nuevos: number; cargados: number; errores: number }[];
  archivos: { fecha: string; empresa: string | null; nombre: string; resultado: string; mensaje: string }[];
}

export interface ClienteOpcion { id: number; razon_social: string; nit: string | null; nivel_riesgo: string | null; organizacion_id: number }
