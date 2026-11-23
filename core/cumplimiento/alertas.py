"""
Alertas del monitoreo transaccional, persistidas y gestionables (migración 040).

Ciclo mensual: cada empresa monitoreada se evalúa mes a mes con el motor de riesgo
existente (GAFI/UIAF) y con las reglas de perfil declarado. Cada hallazgo queda como UNA
alerta por (empresa, regla, mes): si se vuelve a evaluar, se actualizan sus cifras pero
nunca se reabre ni se pierde la decisión que tomó el analista.

Uso interno del equipo de cumplimiento: este módulo NO valida permisos; lo hace la API.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import Engine, text

from core.monitoreo_tx.domain import metricas
from core.monitoreo_tx.domain.entidades import FiltrosTransacciones
from core.monitoreo_tx.repositorio import TransaccionesRepo

logger = logging.getLogger(__name__)

ESTADOS = ("nueva", "en_analisis", "descartada", "escalada", "posible_ros")
ABIERTAS = ("nueva", "en_analisis", "escalada")
CON_DECISION = ("descartada", "escalada", "posible_ros")
NOMBRE_ESTADO = {"nueva": "Nueva", "en_analisis": "En análisis", "descartada": "Descartada",
                 "escalada": "Escalada", "posible_ros": "Posible ROS"}
# Transiciones permitidas (un caso «Posible ROS» pasa a la reportería UIAF, fase 3)
TRANSICIONES = {
    "nueva": {"en_analisis", "descartada", "escalada"},
    "en_analisis": {"descartada", "escalada", "posible_ros"},
    "escalada": {"en_analisis", "posible_ros", "descartada"},
    "descartada": {"en_analisis"},          # reabrir exige nota
    "posible_ros": set(),
}
_ORDEN_PRIORIDAD = {"Crítica": 0, "Alta": 1, "Media": 2, "Baja": 3}
# Holgura sobre el perfil declarado antes de alertar
TOLERANCIA_VOLUMEN = 1.5
TOLERANCIA_OPERACIONES = 1.5
TOLERANCIA_TICKET = 2.0


class ErrorAlerta(ValueError):
    pass


@dataclass(frozen=True)
class ResumenEvaluacion:
    empresas: int
    meses: int
    nuevas: int
    actualizadas: int

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _meses(hasta: date, n: int) -> list[tuple[date, date]]:
    """Los n meses calendario que terminan en el mes de `hasta` (inicio, fin)."""
    salida, inicio = [], hasta.replace(day=1)
    for _ in range(n):
        fin = (inicio.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        salida.append((inicio, fin))
        inicio = (inicio - timedelta(days=1)).replace(day=1)
    return list(reversed(salida))


def _co(valor) -> str:
    """Entero con separador de miles colombiano: 135.193.674."""
    return f"{float(valor):,.0f}".replace(",", ".")


def _veces(real, declarado) -> str:
    """Razón con un decimal y coma decimal: 1,7."""
    return f"{float(real) / float(declarado):.1f}".replace(".", ",")


def _reglas_perfil(kpis: metricas.KPIs, perfil: dict) -> list[dict]:
    """Comportamiento del mes frente a lo que el cliente declaró en su perfil."""
    alertas = []
    vol, ops, ticket = (perfil.get("perfil_volumen_mensual"), perfil.get("perfil_operaciones_mes"),
                        perfil.get("perfil_ticket_promedio"))
    if vol and kpis.monto_pagado > float(vol) * TOLERANCIA_VOLUMEN:
        alertas.append({"regla": "PERF-VOL", "tipo": "Perfil", "prioridad": "Alta",
                        "titulo": "Volumen mensual por encima del perfil declarado",
                        "descripcion": f"Pagó ${_co(kpis.monto_pagado)} en el mes frente a ${_co(vol)} declarados "
                                       f"({_veces(kpis.monto_pagado, vol)} veces).",
                        "valor_detectado": kpis.monto_pagado, "umbral": float(vol) * TOLERANCIA_VOLUMEN,
                        "accion_requerida": "Solicitar soporte del aumento y actualizar el perfil o escalar",
                        "requiere_reporte_uiaf": False, "dias_para_accion": 5})
    if ops and kpis.pagos_exitosos > ops * TOLERANCIA_OPERACIONES:
        alertas.append({"regla": "PERF-OPS", "tipo": "Perfil", "prioridad": "Media",
                        "titulo": "Número de operaciones por encima del perfil declarado",
                        "descripcion": f"{_co(kpis.pagos_exitosos)} pagos en el mes frente a {_co(ops)} declarados.",
                        "valor_detectado": float(kpis.pagos_exitosos), "umbral": ops * TOLERANCIA_OPERACIONES,
                        "accion_requerida": "Validar la causa del aumento de operaciones",
                        "requiere_reporte_uiaf": False, "dias_para_accion": 10})
    if ticket and kpis.ticket_promedio > float(ticket) * TOLERANCIA_TICKET:
        alertas.append({"regla": "PERF-TKT", "tipo": "Perfil", "prioridad": "Media",
                        "titulo": "Ticket promedio por encima del perfil declarado",
                        "descripcion": f"Ticket de ${_co(kpis.ticket_promedio)} frente a ${_co(ticket)} declarados.",
                        "valor_detectado": kpis.ticket_promedio, "umbral": float(ticket) * TOLERANCIA_TICKET,
                        "accion_requerida": "Revisar las operaciones de mayor valor del mes",
                        "requiere_reporte_uiaf": False, "dias_para_accion": 10})
    return alertas


def _alertas_motor(df, nombre: str) -> list[dict]:
    """Alertas del motor GAFI/UIAF existente; la regla es el prefijo de su id (FRAG, VOL…)."""
    from core.monitoreo_tx.characterization.base_characterization import caracterizar_cliente_gafi
    from core.monitoreo_tx.risk_analysis import analizar_riesgo_cliente
    legado = metricas.a_formato_legacy(df)
    resultado = analizar_riesgo_cliente(legado, caracterizar_cliente_gafi(legado), nombre)
    salida = []
    for a in resultado.get("alertas", []):
        salida.append({**a, "regla": str(a.get("id_alerta", "OTRA")).split("-")[0] or "OTRA"})
    return salida


def evaluar(engine: Engine, empresa_ids: list[int] | None = None, meses: int = 3,
            usuario: str = "sistema") -> ResumenEvaluacion:
    """Evalúa los últimos `meses` meses con datos de cada empresa (todas si empresa_ids es None)."""
    repo = TransaccionesRepo(engine)
    with engine.connect() as conn:
        q = ("SELECT e.id, e.nombre_reporte, e.organizacion_id, c.perfil_volumen_mensual, c.perfil_operaciones_mes, "
             "c.perfil_ticket_promedio FROM tx_empresas e LEFT JOIN clientes c ON c.id = e.cliente_id WHERE e.activa")
        params = {}
        if empresa_ids is not None:
            q += " AND e.id = ANY(:ids)"
            params["ids"] = list(empresa_ids)
        empresas = conn.execute(text(q), params).mappings().all()
    nuevas = actualizadas = meses_evaluados = 0
    for e in empresas:
        _, fecha_max = repo.rango_fechas(e["nombre_reporte"])
        if fecha_max is None:
            continue
        for inicio, fin in _meses(fecha_max, meses):
            df = repo.consultar(e["nombre_reporte"], FiltrosTransacciones(desde=inicio, hasta=fin))
            if df.empty:
                continue
            meses_evaluados += 1
            try:
                hallazgos = _alertas_motor(df, e["nombre_reporte"])
            except Exception:
                logger.exception("Motor de riesgo falló para %s %s", e["nombre_reporte"], inicio)
                hallazgos = []
            hallazgos += _reglas_perfil(metricas.calcular_kpis(df), dict(e))
            n, a = _guardar(engine, e["id"], e["organizacion_id"], inicio, hallazgos, usuario)
            nuevas, actualizadas = nuevas + n, actualizadas + a
    return ResumenEvaluacion(len(empresas), meses_evaluados, nuevas, actualizadas)


def _num(v) -> float | None:
    """El motor entrega tipos de numpy; la base necesita números de Python."""
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _guardar(engine: Engine, empresa_id: int, organizacion_id: int, periodo: date, hallazgos: list[dict],
             usuario: str) -> tuple[int, int]:
    nuevas = actualizadas = 0
    with engine.begin() as conn:
        for h in hallazgos:
            prioridad = h.get("prioridad") if h.get("prioridad") in _ORDEN_PRIORIDAD else "Media"
            fila = conn.execute(text(
                "INSERT INTO cmp_alertas (organizacion_id, empresa_id, regla, periodo, tipo, prioridad, titulo, "
                "descripcion, accion_requerida, valor_detectado, umbral, requiere_reporte_uiaf, fecha_limite) "
                "VALUES (:o, :e, :r, :p, :t, :pr, :ti, :d, :ac, :v, :u, :uiaf, CURRENT_DATE + :dias) "
                "ON CONFLICT (empresa_id, regla, periodo) DO UPDATE SET "
                "  tipo = EXCLUDED.tipo, prioridad = EXCLUDED.prioridad, titulo = EXCLUDED.titulo, "
                "  descripcion = EXCLUDED.descripcion, accion_requerida = EXCLUDED.accion_requerida, "
                "  valor_detectado = EXCLUDED.valor_detectado, umbral = EXCLUDED.umbral, "
                "  requiere_reporte_uiaf = EXCLUDED.requiere_reporte_uiaf, actualizada_en = CURRENT_TIMESTAMP "
                "RETURNING id, (xmax = 0) AS insertada"),
                {"o": organizacion_id, "e": empresa_id, "r": h["regla"][:20], "p": periodo, "t": h.get("tipo"),
                 "pr": prioridad, "ti": h.get("titulo") or h["regla"], "d": h.get("descripcion"),
                 "ac": h.get("accion_requerida"), "v": _num(h.get("valor_detectado")), "u": _num(h.get("umbral")),
                 "uiaf": bool(h.get("requiere_reporte_uiaf")), "dias": int(h.get("dias_para_accion") or 7)},
            ).mappings().one()
            if fila["insertada"]:
                nuevas += 1
                conn.execute(text("INSERT INTO cmp_alerta_eventos (alerta_id, usuario, accion, estado_nuevo, nota) "
                                  "VALUES (:a, :u, 'detectada', 'nueva', :n)"),
                             {"a": fila["id"], "u": usuario, "n": h.get("descripcion")})
            else:
                actualizadas += 1
    return nuevas, actualizadas


# =========================
# Consulta y gestión
# =========================
_COLUMNAS = ("a.id, a.organizacion_id, a.empresa_id, e.nombre_reporte AS empresa, e.cliente_id, a.regla, a.periodo, "
             "a.tipo, a.prioridad, a.titulo, a.descripcion, a.accion_requerida, a.valor_detectado, a.umbral, "
             "a.requiere_reporte_uiaf, a.detectada_en, a.actualizada_en, a.fecha_limite, a.estado, a.analista_id, "
             "u.nombre_completo AS analista, a.justificacion, a.decidida_por, a.decidida_en")


def listar(engine: Engine, organizacion_id: int, cliente_id: int | None = None,
           estados: list[str] | None = None, limite: int = 500) -> list[dict]:
    q = (f"SELECT {_COLUMNAS} FROM cmp_alertas a JOIN tx_empresas e ON e.id = a.empresa_id "
         "LEFT JOIN usuarios u ON u.id = a.analista_id WHERE a.organizacion_id = :o")
    params: dict = {"o": organizacion_id, "lim": limite}
    if cliente_id is not None:
        q += " AND e.cliente_id = :c"
        params["c"] = cliente_id
    if estados:
        q += " AND a.estado = ANY(:est)"
        params["est"] = list(estados)
    q += (" ORDER BY CASE WHEN a.estado = ANY(:abiertas) THEN 0 ELSE 1 END, "
          "CASE a.prioridad WHEN 'Crítica' THEN 0 WHEN 'Alta' THEN 1 WHEN 'Media' THEN 2 ELSE 3 END, "
          "a.periodo DESC, a.id DESC LIMIT :lim")
    params["abiertas"] = list(ABIERTAS)
    with engine.connect() as conn:
        return [dict(f) for f in conn.execute(text(q), params).mappings()]


def obtener(engine: Engine, alerta_id: int) -> dict | None:
    with engine.connect() as conn:
        f = conn.execute(text(f"SELECT {_COLUMNAS} FROM cmp_alertas a JOIN tx_empresas e ON e.id = a.empresa_id "
                              "LEFT JOIN usuarios u ON u.id = a.analista_id WHERE a.id = :id"),
                         {"id": alerta_id}).mappings().first()
    return dict(f) if f else None


def eventos(engine: Engine, alerta_id: int) -> list[dict]:
    with engine.connect() as conn:
        return [dict(f) for f in conn.execute(text(
            "SELECT id, usuario, accion, estado_anterior, estado_nuevo, nota, creado_en FROM cmp_alerta_eventos "
            "WHERE alerta_id = :a ORDER BY creado_en, id"), {"a": alerta_id}).mappings()]


def gestionar(engine: Engine, alerta_id: int, usuario: str, *, estado: str | None = None,
              justificacion: str | None = None, analista_id: int | None = None, quitar_analista: bool = False,
              nota: str | None = None) -> dict:
    """Cambia estado, asigna analista o agrega una nota. Todo queda en cmp_alerta_eventos."""
    justificacion = (justificacion or "").strip() or None
    nota = (nota or "").strip() or None
    with engine.begin() as conn:
        a = conn.execute(text("SELECT id, estado, analista_id FROM cmp_alertas WHERE id = :id FOR UPDATE"),
                         {"id": alerta_id}).mappings().first()
        if not a:
            raise LookupError("La alerta no existe.")
        cambio_estado = False
        if estado is not None and estado != a["estado"]:
            if estado not in ESTADOS:
                raise ErrorAlerta("Estado no válido.")
            if estado not in TRANSICIONES[a["estado"]]:
                raise ErrorAlerta(f"No se puede pasar de «{NOMBRE_ESTADO[a['estado']]}» a «{NOMBRE_ESTADO[estado]}».")
            if estado in CON_DECISION and (not justificacion or len(justificacion) < 10):
                raise ErrorAlerta("Para descartar, escalar o marcar como posible ROS escriba la justificación "
                                  "(mínimo 10 caracteres).")
            if a["estado"] == "descartada" and not (justificacion or nota):
                raise ErrorAlerta("Para reabrir una alerta descartada indique el motivo.")
            if estado in CON_DECISION:
                conn.execute(text("UPDATE cmp_alertas SET estado = :e, justificacion = :j, decidida_por = :u, "
                                  "decidida_en = CURRENT_TIMESTAMP, actualizada_en = CURRENT_TIMESTAMP WHERE id = :id"),
                             {"e": estado, "j": justificacion, "u": usuario, "id": alerta_id})
            else:
                conn.execute(text("UPDATE cmp_alertas SET estado = :e, justificacion = NULL, decidida_por = NULL, "
                                  "decidida_en = NULL, actualizada_en = CURRENT_TIMESTAMP WHERE id = :id"),
                             {"e": estado, "id": alerta_id})
            conn.execute(text("INSERT INTO cmp_alerta_eventos (alerta_id, usuario, accion, estado_anterior, estado_nuevo, nota) "
                              "VALUES (:a, :u, 'estado', :ea, :en, :n)"),
                         {"a": alerta_id, "u": usuario, "ea": a["estado"], "en": estado, "n": justificacion or nota})
            cambio_estado = True
        if analista_id is not None or quitar_analista:
            nuevo = None if quitar_analista else analista_id
            nombre_analista = "sin asignar"
            if nuevo is not None:
                nombre_analista = conn.scalar(text(
                    "SELECT COALESCE(nombre_completo, username) FROM usuarios WHERE id = :id AND activo = 1 "
                    "AND organizacion_id IS NULL AND rol IN ('super_admin', 'admin', 'compliance')"), {"id": nuevo})
                if not nombre_analista:
                    raise ErrorAlerta("El analista debe ser un usuario activo del equipo interno.")
            if nuevo != a["analista_id"]:
                conn.execute(text("UPDATE cmp_alertas SET analista_id = :n, actualizada_en = CURRENT_TIMESTAMP WHERE id = :id"),
                             {"n": nuevo, "id": alerta_id})
                conn.execute(text("INSERT INTO cmp_alerta_eventos (alerta_id, usuario, accion, nota) "
                                  "VALUES (:a, :u, 'asignacion', :n)"),
                             {"a": alerta_id, "u": usuario, "n": f"Analista: {nombre_analista}"})
        if nota and not cambio_estado:
            conn.execute(text("INSERT INTO cmp_alerta_eventos (alerta_id, usuario, accion, nota) VALUES (:a, :u, 'nota', :n)"),
                         {"a": alerta_id, "u": usuario, "n": nota})
    return obtener(engine, alerta_id)


def evaluar_por_nombres(engine: Engine, nombres: list[str] | None, usuario: str = "sistema") -> ResumenEvaluacion | None:
    """Tras una carga: evalúa las empresas cargadas (todas si nombres es None). Nunca lanza: una falla
    aquí no debe deshacer ni ocultar una carga que sí terminó bien."""
    try:
        ids = None
        if nombres is not None:
            with engine.connect() as conn:
                ids = list(conn.scalars(text("SELECT id FROM tx_empresas WHERE nombre_reporte = ANY(:n)"),
                                        {"n": list(nombres)}))
            if not ids:
                return None
        return evaluar(engine, ids, usuario=usuario)
    except Exception:
        logger.exception("No se pudieron evaluar las alertas tras la carga")
        return None


def evaluar_en_segundo_plano(engine: Engine, nombres: list[str] | None, usuario: str = "sistema") -> None:
    import threading
    threading.Thread(target=evaluar_por_nombres, args=(engine, nombres, usuario), daemon=True,
                     name="evaluar-alertas").start()
