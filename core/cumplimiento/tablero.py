"""
Tablero general de cumplimiento (decisiones 2026-11-28).

Vista informativa de TODA la operación para el director de cumplimiento (y el equipo
interno): cliente (organización: Adamo…) → subcliente (Paxum, CM Grupo Tecno…) →
beneficiarios. Reúne en una sola consulta:

  - movimientos del periodo: monto pagado, pagos, tasa de éxito, tendencia mensual;
  - cada subcliente: monto, participación, comparación con su perfil declarado, riesgo,
    documentos y beneficiarios representativos (documento enmascarado);
  - alertas (posible ROS, críticas sin atender), requerimientos, aliados y reportes UIAF;
  - avisos automáticos para el oficial y el director.

Todo se calcula con agregados en SQL: no se cargan las transacciones en memoria.
Un «pago» es un débito; «exitoso» si la transacción quedó exitosa (igual que en monitoreo).
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import Engine, text

from core.cumplimiento import aliados as ali
from core.cumplimiento import requerimientos as rq

ES_PAGO = "t.tipo_transaccion ILIKE 'd_bito%'"
ES_DEVOLUCION = "t.tipo_transaccion ILIKE 'cr_dito%'"
TOP_BENEFICIARIOS = 5
SOBRE_PERFIL = 0.20          # aviso si el promedio mensual supera el perfil declarado en más del 20 %
CONCENTRACION = 0.40         # aviso si los 3 primeros beneficiarios suman más del 40 % de lo pagado
DIAS_SIN_ATENDER = 5


def enmascarar_documento(doc) -> str | None:
    if not doc:
        return None
    d = str(doc).strip()
    return ("****" + d[-4:]) if len(d) > 4 else d


def _rango(conn, desde: date | None, hasta: date | None, org: int | None) -> tuple[date | None, date | None]:
    if desde and hasta:
        return desde, hasta
    f = conn.execute(text(
        "SELECT min(t.fecha), max(t.fecha) FROM tx_transacciones t JOIN tx_empresas e ON e.nombre_reporte = t.cliente "
        "WHERE (CAST(:o AS INTEGER) IS NULL OR e.organizacion_id = :o)"), {"o": org}).first()
    return desde or f[0], hasta or f[1]


def _meses(desde: date, hasta: date) -> int:
    return (hasta.year - desde.year) * 12 + hasta.month - desde.month + 1


def _movimientos(conn, desde: date, hasta: date, org: int | None) -> list[dict]:
    """Totales por empresa del reporte (con su subcliente y organización)."""
    return [dict(f._mapping) for f in conn.execute(text(f"""
        SELECT e.organizacion_id, e.cliente_id, e.nombre_reporte AS empresa,
               count(*) FILTER (WHERE {ES_PAGO})                       AS pagos_enviados,
               count(*) FILTER (WHERE {ES_PAGO} AND t.exitosa)         AS pagos_exitosos,
               COALESCE(sum(t.monto) FILTER (WHERE {ES_PAGO} AND t.exitosa), 0) AS monto_pagado,
               count(*) FILTER (WHERE {ES_DEVOLUCION})                 AS devoluciones,
               count(DISTINCT t.id_beneficiario) FILTER (WHERE {ES_PAGO} AND t.exitosa) AS beneficiarios,
               count(DISTINCT date_trunc('month', t.fecha)) FILTER (WHERE {ES_PAGO} AND t.exitosa) AS meses_activos,
               min(t.fecha) AS primera, max(t.fecha) AS ultima
          FROM tx_transacciones t JOIN tx_empresas e ON e.nombre_reporte = t.cliente
         WHERE t.fecha BETWEEN :d AND :h AND (CAST(:o AS INTEGER) IS NULL OR e.organizacion_id = :o)
         GROUP BY e.organizacion_id, e.cliente_id, e.nombre_reporte"""), {"d": desde, "h": hasta, "o": org})]


def _kpis(filas: list[dict]) -> dict:
    env = sum(f["pagos_enviados"] for f in filas)
    exi = sum(f["pagos_exitosos"] for f in filas)
    dev = sum(f["devoluciones"] for f in filas)
    monto = float(sum(f["monto_pagado"] for f in filas))
    return {"monto_pagado": monto, "pagos_exitosos": exi, "pagos_enviados": env,
            "ticket_promedio": monto / exi if exi else 0.0,
            "tasa_exito": min(max(exi - dev, 0) / env, 1.0) if env else None, "devoluciones": dev}


def _variacion(actual: float, anterior: float | None) -> float | None:
    return None if not anterior else (actual - anterior) / anterior


def _serie(conn, desde: date, hasta: date, org: int | None) -> list[dict]:
    return [{"mes": f[0].isoformat(), "monto_pagado": float(f[1] or 0), "pagos": f[2]} for f in conn.execute(text(f"""
        SELECT date_trunc('month', t.fecha)::date, sum(t.monto), count(*)
          FROM tx_transacciones t JOIN tx_empresas e ON e.nombre_reporte = t.cliente
         WHERE {ES_PAGO} AND t.exitosa AND t.fecha BETWEEN :d AND :h
           AND (CAST(:o AS INTEGER) IS NULL OR e.organizacion_id = :o)
         GROUP BY 1 ORDER BY 1"""), {"d": desde, "h": hasta, "o": org})]


def _top_beneficiarios(conn, desde: date, hasta: date, org: int | None) -> dict[int, list[dict]]:
    filas = conn.execute(text(f"""
        WITH b AS (
            SELECT e.cliente_id, t.id_beneficiario, max(t.beneficiario) AS nombre, max(t.tipo_persona) AS tipo_persona,
                   sum(t.monto) AS monto, count(*) AS pagos, max(t.fecha) AS ultimo
              FROM tx_transacciones t JOIN tx_empresas e ON e.nombre_reporte = t.cliente
             WHERE {ES_PAGO} AND t.exitosa AND t.fecha BETWEEN :d AND :h AND e.cliente_id IS NOT NULL
               AND (CAST(:o AS INTEGER) IS NULL OR e.organizacion_id = :o)
             GROUP BY e.cliente_id, t.id_beneficiario)
        SELECT * FROM (
            SELECT b.*, row_number() OVER (PARTITION BY cliente_id ORDER BY monto DESC) AS puesto,
                   sum(monto) OVER (PARTITION BY cliente_id) AS total
              FROM b) x
         WHERE puesto <= :n ORDER BY cliente_id, puesto"""), {"d": desde, "h": hasta, "o": org, "n": TOP_BENEFICIARIOS})
    top: dict[int, list[dict]] = {}
    for f in filas.mappings():
        top.setdefault(f["cliente_id"], []).append({
            "nombre": f["nombre"], "documento": enmascarar_documento(f["id_beneficiario"]), "tipo_persona": f["tipo_persona"],
            "monto": float(f["monto"]), "pagos": f["pagos"], "ultimo": f["ultimo"].isoformat() if f["ultimo"] else None,
            "participacion": float(f["monto"]) / float(f["total"]) if f["total"] else 0.0})
    return top


def _documentos(conn, ids: list[int]) -> dict[int, dict]:
    """Documentos propios exigidos por subcliente (sin llamar a OneDrive: lo ya reconocido)."""
    from core.cumplimiento import documentos as doc
    if not ids:
        return {}
    res: dict[int, dict] = {}
    clientes = conn.execute(text("SELECT id, tipo_persona, carpeta_onedrive FROM clientes WHERE id = ANY(:i)"),
                            {"i": ids}).mappings().all()
    for c in clientes:
        archivos = [a for a in doc._archivos_bd(conn, c["id"]) if a["id_beneficiario"] is None]
        filas, completo = doc._checklist(doc.PROPIOS.get(c["tipo_persona"], doc.PROPIOS["juridica"]), archivos)
        res[c["id"]] = {"cargados": sum(f["cargado"] for f in filas), "exigidos": len(filas),
                        "listo_para_banco": completo and bool(c["carpeta_onedrive"]),
                        "carpeta": bool(c["carpeta_onedrive"])}
    return res


def _alertas(conn, org: int | None, hoy: date) -> dict:
    p = {"o": org, "limite": hoy - timedelta(days=DIAS_SIN_ATENDER)}
    filtro = "(CAST(:o AS INTEGER) IS NULL OR a.organizacion_id = :o)"
    conteo = conn.execute(text(f"""
        SELECT a.organizacion_id,
               count(*) FILTER (WHERE a.estado IN ('nueva', 'en_analisis'))               AS abiertas,
               count(*) FILTER (WHERE a.estado = 'posible_ros')                           AS posible_ros,
               count(*) FILTER (WHERE a.estado = 'escalada')                              AS escaladas,
               count(*) FILTER (WHERE a.estado = 'nueva' AND a.prioridad IN ('Crítica', 'Alta')
                                  AND a.detectada_en::date <= :limite)                    AS sin_atender
          FROM cmp_alertas a WHERE {filtro} GROUP BY a.organizacion_id"""), p).mappings().all()
    ros = [dict(f._mapping) for f in conn.execute(text(f"""
        SELECT a.id, a.organizacion_id, a.titulo, a.prioridad, a.periodo, a.decidida_en, c.razon_social AS subcliente
          FROM cmp_alertas a JOIN tx_empresas e ON e.id = a.empresa_id LEFT JOIN clientes c ON c.id = e.cliente_id
         WHERE a.estado = 'posible_ros' AND {filtro} ORDER BY a.decidida_en DESC NULLS LAST LIMIT 20"""), p)]
    por_org = {f["organizacion_id"]: dict(f) for f in conteo}
    total = {k: sum(f[k] for f in conteo) for k in ("abiertas", "posible_ros", "escaladas", "sin_atender")}
    return {"total": total, "por_organizacion": por_org, "posible_ros": ros}


def _reportes(conn, desde: date, hasta: date, org: int | None) -> dict:
    filtro = "(CAST(:o AS INTEGER) IS NULL OR r.organizacion_id = :o)"
    lista = [dict(f._mapping) for f in conn.execute(text(f"""
        SELECT r.id, r.organizacion_id, o.nombre AS organizacion, r.tipo, r.periodo_desde, r.periodo_hasta,
               r.fecha_presentacion, r.radicado, c.razon_social AS subcliente, r.archivo_nombre
          FROM reportes_uiaf r JOIN organizaciones o ON o.id = r.organizacion_id LEFT JOIN clientes c ON c.id = r.cliente_id
         WHERE r.fecha_presentacion BETWEEN :d AND :h AND {filtro}
         ORDER BY r.fecha_presentacion DESC, r.id DESC"""), {"d": desde, "h": hasta, "o": org})]
    ultimo = {f[0]: f[1] for f in conn.execute(text(
        f"SELECT r.organizacion_id, max(r.fecha_presentacion) FROM reportes_uiaf r WHERE {filtro} GROUP BY 1"), {"o": org})}
    return {"lista": lista, "ros": sum(r["tipo"] == "ROS" for r in lista), "aros": sum(r["tipo"] == "AROS" for r in lista),
            "otros": sum(r["tipo"] == "otro" for r in lista), "ultimo_por_organizacion": ultimo}


def tablero(engine: Engine, desde: date | None = None, hasta: date | None = None,
            organizacion_id: int | None = None, hoy: date | None = None) -> dict:
    hoy = hoy or date.today()
    with engine.connect() as conn:
        orgs = [dict(f._mapping) for f in conn.execute(text(
            "SELECT id, nombre FROM organizaciones WHERE activa AND (CAST(:o AS INTEGER) IS NULL OR id = :o) ORDER BY nombre"),
            {"o": organizacion_id})]
        d, h = _rango(conn, desde, hasta, organizacion_id)
        sin_datos = d is None
        if sin_datos:
            d = h = hoy
        filas = _movimientos(conn, d, h, organizacion_id)
        comparar = bool(desde and hasta)
        anterior = None
        if comparar:
            dur = (h - d).days + 1
            anterior = _kpis(_movimientos(conn, d - timedelta(days=dur), d - timedelta(days=1), organizacion_id))
        serie = _serie(conn, d, h, organizacion_id)
        top = _top_beneficiarios(conn, d, h, organizacion_id)
        ids = sorted({f["cliente_id"] for f in filas if f["cliente_id"]})
        info = {f.id: dict(f._mapping) for f in conn.execute(text(
            "SELECT id, organizacion_id, razon_social, nivel_riesgo, perfil_volumen_mensual, perfil_operaciones_mes "
            "FROM clientes WHERE id = ANY(:i)"), {"i": ids})} if ids else {}
        docs = _documentos(conn, ids)
        alertas = _alertas(conn, organizacion_id, hoy)
        # Sin periodo elegido («todo»), reportes y requerimientos cubren toda la historia
        rd, rh = (d, h) if comparar else (date(2000, 1, 1), max(h, hoy))
        reportes = _reportes(conn, rd, rh, organizacion_id)

    kpis = _kpis(filas)
    if anterior is not None:
        kpis["variacion_monto"] = _variacion(kpis["monto_pagado"], anterior["monto_pagado"])
        kpis["variacion_pagos"] = _variacion(kpis["pagos_exitosos"], anterior["pagos_exitosos"])
    meses = _meses(d, h)

    # ── Subclientes por organización ──
    subclientes: dict[int, list[dict]] = {}
    total_org: dict[int, float] = {}
    for f in filas:
        total_org[f["organizacion_id"]] = total_org.get(f["organizacion_id"], 0.0) + float(f["monto_pagado"])
    agrupado: dict[tuple, dict] = {}
    for f in filas:
        clave = (f["organizacion_id"], f["cliente_id"] or f"empresa:{f['empresa']}")
        g = agrupado.setdefault(clave, {"organizacion_id": f["organizacion_id"], "cliente_id": f["cliente_id"],
                                        "empresas": [], "filas": []})
        g["empresas"].append(f["empresa"])
        g["filas"].append(f)
    for (oid, _), g in agrupado.items():
        k = _kpis(g["filas"])
        c = info.get(g["cliente_id"]) or {}
        meses_activos = max(max((f["meses_activos"] or 0) for f in g["filas"]), 1)
        promedio = k["monto_pagado"] / meses_activos
        perfil = float(c["perfil_volumen_mensual"]) if c.get("perfil_volumen_mensual") else None
        b = top.get(g["cliente_id"], [])
        subclientes.setdefault(oid, []).append({
            "cliente_id": g["cliente_id"], "nombre": c.get("razon_social") or f"Sin subcliente asignado ({', '.join(g['empresas'])})",
            "empresas": g["empresas"], **k, "beneficiarios": sum(f["beneficiarios"] for f in g["filas"]),
            "participacion": k["monto_pagado"] / total_org[oid] if total_org.get(oid) else 0.0,
            "promedio_mensual": promedio, "perfil_mensual": perfil,
            "desviacion_perfil": (promedio - perfil) / perfil if perfil else None,
            "nivel_riesgo": c.get("nivel_riesgo"), "documentos": docs.get(g["cliente_id"]),
            "top_beneficiarios": b, "concentracion_top3": sum(x["participacion"] for x in b[:3]) if b else None,
            "ultima": max(f["ultima"] for f in g["filas"]).isoformat()})
    for lista in subclientes.values():
        lista.sort(key=lambda s: -s["monto_pagado"])

    # ── Requerimientos (abiertos + recibidos en el periodo), aliados ──
    donde = "(q.estado = ANY(:abiertos) OR q.fecha_recibido BETWEEN :d AND :h)"
    params: dict = {"d": rd, "h": rh}
    if organizacion_id:
        donde += " AND q.organizacion_id = :o"
        params["o"] = organizacion_id
    reqs = rq._lista(engine, donde, params, hoy)
    for q in reqs:
        q["beneficiarios"] = [{**b, "id_beneficiario": enmascarar_documento(b["id_beneficiario"])} for b in q["beneficiarios"]]
    aliados = {o["id"]: ali.listar(engine, o["id"], hoy) for o in orgs}

    organizaciones = []
    for o in orgs:
        a = aliados[o["id"]]
        organizaciones.append({
            **o, "kpis": _kpis([f for f in filas if f["organizacion_id"] == o["id"]]),
            "subclientes": subclientes.get(o["id"], []),
            "alertas": alertas["por_organizacion"].get(o["id"], {"abiertas": 0, "posible_ros": 0, "escaladas": 0, "sin_atender": 0}),
            "aliados": a["resumen"],
            "aliados_atencion": [{"id": x["id"], "nombre": x["nombre"], "estado": x["estado"], "avisos": x["avisos"]}
                                 for x in a["aliados"] if x["avisos"] and x["estado"] in ("activo", "onboarding")],
            "ultimo_reporte_uiaf": reportes["ultimo_por_organizacion"].get(o["id"]),
        })

    resumen_req = rq.resumen(reqs)
    resultado = {
        "periodo": {"desde": d.isoformat(), "hasta": h.isoformat(), "meses": meses, "comparado": comparar,
                    "sin_datos": sin_datos},
        "kpis": kpis, "serie": serie, "organizaciones": organizaciones,
        "alertas": alertas["total"], "posible_ros": alertas["posible_ros"],
        "requerimientos": reqs, "resumen_requerimientos": resumen_req,
        "aliados": {k: sum(o["aliados"][k] for o in organizaciones) for k in ("activos", "diligencia_pendiente",
                                                                               "revision_vencida", "riesgo_alto")},
        "reportes_uiaf": reportes,
    }
    resultado["avisos"] = avisos(resultado)
    return resultado


def avisos(t: dict) -> list[dict]:
    """Recomendaciones automáticas para el oficial y el director, de la más a la menos urgente."""
    a: list[dict] = []

    def poner(prioridad: str, texto: str, enlace: str | None = None):
        a.append({"prioridad": prioridad, "texto": texto, "enlace": enlace})

    if t["alertas"]["posible_ros"]:
        poner("alta", f"{t['alertas']['posible_ros']} alerta(s) en «posible ROS»: decidir y, si corresponde, reportar a la UIAF.")
    if t["alertas"]["sin_atender"]:
        poner("alta", f"{t['alertas']['sin_atender']} alerta(s) críticas o altas sin atender hace más de {DIAS_SIN_ATENDER} días.")
    if t["resumen_requerimientos"]["atrasados"]:
        poner("alta", f"{t['resumen_requerimientos']['atrasados']} requerimiento(s) atrasado(s).")
    for o in t["organizaciones"]:
        base = f"/organizaciones/{o['id']}"
        for s in o["subclientes"]:
            enlace = f"{base}/clientes/{s['cliente_id']}" if s["cliente_id"] else None
            if not s["cliente_id"]:
                poner("media", f"{o['nombre']}: hay transacciones de {', '.join(s['empresas'])} sin subcliente asignado.")
                continue
            dv = s["desviacion_perfil"]
            if dv is not None and dv > SOBRE_PERFIL:
                poner("alta" if dv > 0.5 else "media",
                      f"{s['nombre']} opera {dv:.0%} por encima de su perfil declarado: actualizar el perfil transaccional y pedir soporte.", enlace)
            elif s["perfil_mensual"] is None and s["monto_pagado"] > 0:
                poner("media", f"{s['nombre']} opera sin perfil transaccional declarado.", enlace)
            if s["documentos"] and not s["documentos"]["listo_para_banco"] and s["monto_pagado"] > 0:
                poner("media", f"{s['nombre']} opera con documentación incompleta "
                               f"({s['documentos']['cargados']} de {s['documentos']['exigidos']}).", enlace)
            if not s["nivel_riesgo"] and s["monto_pagado"] > 0:
                poner("media", f"{s['nombre']} opera sin calificación de riesgo.", enlace)
            if s["concentracion_top3"] and s["concentracion_top3"] > CONCENTRACION:
                poner("baja", f"En {s['nombre']}, los 3 principales beneficiarios concentran el {s['concentracion_top3']:.0%} de lo pagado.", enlace)
        if o["aliados"]["diligencia_pendiente"]:
            poner("media", f"{o['nombre']}: {o['aliados']['diligencia_pendiente']} aliado(s) bancario(s) vigentes sin debida diligencia completa.",
                  f"{base}?tab=aliados")
        if o["aliados"]["revision_vencida"]:
            poner("media", f"{o['nombre']}: {o['aliados']['revision_vencida']} aliado(s) con la revisión vencida.", f"{base}?tab=aliados")
    orden = {"alta": 0, "media": 1, "baja": 2}
    return sorted(a, key=lambda x: orden[x["prioridad"]])
