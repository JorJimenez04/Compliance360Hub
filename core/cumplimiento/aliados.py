"""
Aliados bancarios de cada organización (fase 2 de la migración, migración 045).

Dos niveles:
  aliados_bancarios   la entidad (banco, PSP, VASP…), una sola vez
  org_aliados         la relación de una organización con esa entidad

Todo cambio de estado, riesgo o debida diligencia exige motivo y queda en
org_aliados_historial. Uso interno (super_admin, compliance; el director solo lee).
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import Engine, text

TIPOS_ENTIDAD = {"banco": "Banco", "psp": "PSP / pasarela de pagos", "entidad_pagos": "Entidad de pagos (SEDPE)",
                 "corresponsal": "Corresponsal", "vasp": "VASP / exchange cripto", "otro": "Otro"}
ESTADOS = {"prospecto": "Prospecto", "onboarding": "En onboarding", "activo": "Activo",
           "suspendido": "Suspendido", "terminado": "Terminado"}
SERVICIOS = {"pay_in": "Pay-in", "pay_out": "Pay-out", "dispersion": "Dispersión", "recaudo": "Recaudo",
             "compensacion": "Cuenta de compensación", "cripto": "On/off-ramp cripto", "fx": "Cambio de divisas (FX)",
             "custodia": "Custodia"}
NIVELES = ("Alto", "Medio", "Bajo")
DD_ESTADOS = {"no_iniciada": "No iniciada", "en_proceso": "En proceso", "completa": "Completa", "rechazada": "Rechazada"}
DD_NIVELES = {"simplificada": "Simplificada", "estandar": "Estándar", "intensificada": "Intensificada"}
CATALOGOS = {"tipos_entidad": TIPOS_ENTIDAD, "estados": ESTADOS, "servicios": SERVICIOS, "niveles": NIVELES,
             "dd_estados": DD_ESTADOS, "dd_niveles": DD_NIVELES}

CAMPOS_ENTIDAD = ("nombre", "razon_social", "identificacion", "pais", "tipo_entidad", "regulado", "regulador",
                  "licencia", "sitio_web", "notas")
CAMPOS_RELACION = ("fecha_inicio", "vence_contrato", "vence_poliza", "vence_licencia", "servicios", "monedas", "proxima_revision", "dd_fecha", "dd_nivel", "exigencias",
                   "contacto_cumplimiento", "correo_cumplimiento", "telefono_cumplimiento", "contacto_comercial",
                   "correo_comercial", "notas")
MOTIVO_MINIMO = 10


class ErrorAliado(ValueError):
    pass


def _texto(v):
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


def _lista(v) -> list[str]:
    vistos: list[str] = []
    for x in v or []:
        x = _texto(x)
        if x and x not in vistos:
            vistos.append(x)
    return vistos


# ---------- Validación ----------
def _validar_entidad(datos: dict, parcial: bool) -> dict:
    v = {k: _texto(datos[k]) for k in CAMPOS_ENTIDAD if k in datos}
    if not parcial or "nombre" in v:
        if not v.get("nombre") or len(v["nombre"]) < 2:
            raise ErrorAliado("Indique el nombre del aliado.")
    if v.get("tipo_entidad") is not None and v["tipo_entidad"] not in TIPOS_ENTIDAD:
        raise ErrorAliado("Tipo de entidad no válido.")
    if "regulado" in v:
        v["regulado"] = bool(v["regulado"])
    return v


def _validar_relacion(datos: dict) -> dict:
    v = {k: datos[k] for k in CAMPOS_RELACION if k in datos}
    for k in ("contacto_cumplimiento", "correo_cumplimiento", "telefono_cumplimiento", "contacto_comercial",
              "correo_comercial", "notas", "dd_nivel"):
        if k in v:
            v[k] = _texto(v[k])
    for k in ("servicios", "monedas", "exigencias"):
        if k in v:
            v[k] = _lista(v[k])
    if "servicios" in v and any(s not in SERVICIOS for s in v["servicios"]):
        raise ErrorAliado("Algún servicio no es válido.")
    if "monedas" in v:
        v["monedas"] = [m.upper()[:5] for m in v["monedas"]]
    if v.get("dd_nivel") is not None and v["dd_nivel"] not in DD_NIVELES:
        raise ErrorAliado("Nivel de debida diligencia no válido.")
    for k in ("correo_cumplimiento", "correo_comercial"):
        if v.get(k) and "@" not in v[k]:
            raise ErrorAliado("Correo de contacto no válido.")
    return v


def _motivo(motivo: str | None) -> str:
    m = _texto(motivo)
    if not m or len(m) < MOTIVO_MINIMO:
        raise ErrorAliado(f"Explique el motivo del cambio (al menos {MOTIVO_MINIMO} caracteres).")
    return m


# ---------- Consultas ----------
_SELECT = """
    SELECT r.id, r.organizacion_id, r.aliado_id, r.estado, r.fecha_estado, r.fecha_inicio, r.servicios, r.monedas,
           r.nivel_riesgo, r.proxima_revision, r.dd_estado, r.dd_fecha, r.dd_nivel, r.exigencias,
           r.contacto_cumplimiento, r.correo_cumplimiento, r.telefono_cumplimiento, r.contacto_comercial,
           r.correo_comercial, r.notas, r.origen_aliado_id, r.actualizado_en,
           r.vence_contrato, r.vence_poliza, r.vence_licencia, r.carpeta_item_id, r.carpeta_web_url, r.carpeta_nombre,
           r.carpeta_revisada_en,
           b.nombre, b.razon_social, b.identificacion, b.pais, b.tipo_entidad, b.regulado, b.regulador,
           b.licencia, b.sitio_web, b.notas AS notas_entidad,
           (SELECT count(*) FROM org_aliados x WHERE x.aliado_id = b.id) AS organizaciones
      FROM org_aliados r JOIN aliados_bancarios b ON b.id = r.aliado_id
"""


def _avisos(r: dict, hoy: date, documentos: dict | None = None) -> list[dict]:
    """Lo que el oficial debe atender en esta relación (sirve también para el tablero)."""
    a: list[dict] = []
    if documentos and r["estado"] != "terminado":
        for f in documentos["filas"]:
            if f["estado_vence"] == "vencido":
                a.append({"tono": "critico", "texto": f"{f['nombre']}: venció el {f['vence'].isoformat()}"})
            elif f["estado_vence"] == "por_vencer":
                a.append({"tono": "alerta", "texto": f"{f['nombre']}: vence el {f['vence'].isoformat()}"})
        faltan = [f["nombre"] for f in documentos["filas"] if f["exigido"] and not f["cargado"]]
        if documentos["carpeta"] and faltan and r["estado"] in ("activo", "onboarding"):
            a.append({"tono": "alerta", "texto": "Faltan documentos: " + ", ".join(faltan)})
    vigente = r["estado"] in ("activo", "onboarding")
    if vigente and r["dd_estado"] != "completa":
        a.append({"tono": "alerta" if r["estado"] == "onboarding" else "critico",
                  "texto": f"Debida diligencia {DD_ESTADOS[r['dd_estado']].lower()} y la relación "
                           f"{'ya está activa' if r['estado'] == 'activo' else 'en onboarding'}"})
    if r["estado"] == "activo" and r["dd_estado"] == "rechazada":
        a.append({"tono": "critico", "texto": "Opera con la diligencia rechazada"})
    if vigente and not r["nivel_riesgo"]:
        a.append({"tono": "alerta", "texto": "Sin calificación de riesgo"})
    if r["proxima_revision"] and r["estado"] != "terminado":
        if r["proxima_revision"] < hoy:
            a.append({"tono": "critico", "texto": f"Revisión vencida desde {r['proxima_revision'].isoformat()}"})
        elif r["proxima_revision"] <= hoy + timedelta(days=30):
            a.append({"tono": "alerta", "texto": f"Revisión el {r['proxima_revision'].isoformat()}"})
    elif vigente and r["nivel_riesgo"]:
        a.append({"tono": "alerta", "texto": "Sin fecha de próxima revisión"})
    if vigente and not r["tipo_entidad"]:
        a.append({"tono": "neutro", "texto": "Falta el tipo de entidad"})
    if vigente and not r["servicios"]:
        a.append({"tono": "neutro", "texto": "Faltan los servicios que presta"})
    return a


def _fila(f) -> dict:
    d = dict(f._mapping)
    d["servicios"], d["monedas"], d["exigencias"] = list(d["servicios"] or []), list(d["monedas"] or []), list(d["exigencias"] or [])
    return d


def listar(engine: Engine, organizacion_id: int, hoy: date | None = None) -> dict:
    hoy = hoy or date.today()
    with engine.connect() as conn:
        filas = [_fila(f) for f in conn.execute(text(_SELECT + " WHERE r.organizacion_id = :o ORDER BY "
                 "array_position(ARRAY['activo','onboarding','prospecto','suspendido','terminado'], r.estado), lower(b.nombre)"),
                 {"o": organizacion_id})]
    from core.cumplimiento.carpeta_compliance import estado_documentos_aliado
    with engine.connect() as conn:
        for r in filas:
            r["documentos"] = estado_documentos_aliado(conn, r, hoy)
            r["avisos"] = _avisos(r, hoy, r["documentos"])
    vigentes = [r for r in filas if r["estado"] in ("activo", "onboarding")]
    resumen = {
        "total": len(filas),
        "activos": sum(r["estado"] == "activo" for r in filas),
        "diligencia_pendiente": sum(r["dd_estado"] != "completa" for r in vigentes),
        "revision_vencida": sum(bool(r["proxima_revision"] and r["proxima_revision"] < hoy) for r in filas
                                if r["estado"] != "terminado"),
        "riesgo_alto": sum(r["nivel_riesgo"] == "Alto" for r in vigentes),
        "documentos_vencidos": sum(any(f["estado_vence"] == "vencido" for f in r["documentos"]["filas"]) for r in filas
                                   if r["estado"] != "terminado"),
        "documentos_por_vencer": sum(any(f["estado_vence"] == "por_vencer" for f in r["documentos"]["filas"]) for r in filas
                                     if r["estado"] != "terminado"),
    }
    return {"aliados": filas, "resumen": resumen}


def obtener(engine: Engine, organizacion_id: int, relacion_id: int, hoy: date | None = None) -> dict:
    with engine.connect() as conn:
        f = conn.execute(text(_SELECT + " WHERE r.id = :r AND r.organizacion_id = :o"),
                         {"r": relacion_id, "o": organizacion_id}).first()
        if f is None:
            raise LookupError("El aliado no existe en esta organización.")
        r = _fila(f)
        r["historial"] = [dict(h._mapping) for h in conn.execute(text(
            "SELECT campo, valor_anterior, valor_nuevo, motivo, usuario, fecha FROM org_aliados_historial "
            "WHERE relacion_id = :r ORDER BY fecha DESC, id DESC"), {"r": relacion_id})]
        r["otras_organizaciones"] = [dict(o._mapping) for o in conn.execute(text(
            "SELECT o.nombre, x.estado FROM org_aliados x JOIN organizaciones o ON o.id = x.organizacion_id "
            "WHERE x.aliado_id = :a AND x.organizacion_id <> :o ORDER BY o.nombre"),
            {"a": r["aliado_id"], "o": organizacion_id})]
    from core.cumplimiento.carpeta_compliance import estado_documentos_aliado
    with engine.connect() as conn:
        r["documentos"] = estado_documentos_aliado(conn, r, hoy)
    r["avisos"] = _avisos(r, hoy or date.today(), r["documentos"])
    return r


def buscar_catalogo(engine: Engine, termino: str) -> list[dict]:
    """Para el alta: si el aliado ya existe (p. ej. es aliado de otra organización), se reutiliza."""
    t = _texto(termino) or ""
    if len(t) < 2:
        return []
    with engine.connect() as conn:
        return [dict(f._mapping) for f in conn.execute(text(
            "SELECT id, nombre, razon_social, identificacion, pais, tipo_entidad FROM aliados_bancarios "
            "WHERE nombre ILIKE :t OR razon_social ILIKE :t OR identificacion ILIKE :t ORDER BY lower(nombre) LIMIT 10"),
            {"t": f"%{t}%"})]


# ---------- Escritura ----------
def _historial(conn, relacion_id: int, campo: str, antes, despues, motivo: str | None, usuario: str) -> None:
    conn.execute(text("INSERT INTO org_aliados_historial (relacion_id, campo, valor_anterior, valor_nuevo, motivo, usuario) "
                      "VALUES (:r, :c, :a, :d, :m, :u)"),
                 {"r": relacion_id, "c": campo, "a": antes, "d": despues, "m": motivo, "u": usuario})


def crear(engine: Engine, organizacion_id: int, datos: dict, usuario: str) -> int:
    """Alta de un aliado para la organización. Usa la entidad existente si viene `aliado_id`
    o si ya hay una con el mismo nombre; si no, la crea."""
    rel = _validar_relacion(datos)
    estado = datos.get("estado") or "prospecto"
    if estado not in ESTADOS:
        raise ErrorAliado("Estado no válido.")
    nivel = _texto(datos.get("nivel_riesgo"))
    if nivel is not None and nivel not in NIVELES:
        raise ErrorAliado("Nivel de riesgo no válido.")
    with engine.begin() as conn:
        aliado_id = datos.get("aliado_id")
        if aliado_id:
            if not conn.scalar(text("SELECT 1 FROM aliados_bancarios WHERE id = :a"), {"a": aliado_id}):
                raise ErrorAliado("El aliado elegido no existe.")
        else:
            ent = _validar_entidad(datos, parcial=False)
            aliado_id = conn.scalar(text("SELECT id FROM aliados_bancarios WHERE lower(nombre) = lower(:n)"),
                                    {"n": ent["nombre"]})
            if not aliado_id:
                cols = list(ent) + ["creado_por"]
                aliado_id = conn.scalar(text(
                    f"INSERT INTO aliados_bancarios ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)}) RETURNING id"),
                    {**ent, "creado_por": usuario})
        if conn.scalar(text("SELECT 1 FROM org_aliados WHERE organizacion_id = :o AND aliado_id = :a"),
                       {"o": organizacion_id, "a": aliado_id}):
            raise ErrorAliado("Ese aliado ya está registrado en esta organización.")
        cols = list(rel) + ["organizacion_id", "aliado_id", "estado", "nivel_riesgo", "creado_por"]
        rid = conn.scalar(text(
            f"INSERT INTO org_aliados ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)}) RETURNING id"),
            {**rel, "organizacion_id": organizacion_id, "aliado_id": aliado_id, "estado": estado,
             "nivel_riesgo": nivel, "creado_por": usuario})
        _historial(conn, rid, "alta", None, ESTADOS[estado], _texto(datos.get("motivo")), usuario)
        return rid


def actualizar(engine: Engine, organizacion_id: int, relacion_id: int, entidad: dict, relacion: dict) -> dict:
    """Datos de la entidad (compartidos con otras organizaciones) y de la relación.
    Estado, riesgo y diligencia no van aquí: van por `cambiar`, con motivo."""
    ent = _validar_entidad(entidad, parcial=True)
    rel = _validar_relacion(relacion)
    with engine.begin() as conn:
        aliado_id = conn.scalar(text("SELECT aliado_id FROM org_aliados WHERE id = :r AND organizacion_id = :o"),
                                {"r": relacion_id, "o": organizacion_id})
        if not aliado_id:
            raise LookupError("El aliado no existe en esta organización.")
        if ent.get("nombre") and conn.scalar(text(
                "SELECT 1 FROM aliados_bancarios WHERE lower(nombre) = lower(:n) AND id <> :a"),
                {"n": ent["nombre"], "a": aliado_id}):
            raise ErrorAliado("Ya existe otro aliado con ese nombre.")
        if ent:
            conn.execute(text(f"UPDATE aliados_bancarios SET {', '.join(f'{k} = :{k}' for k in ent)}, "
                              "actualizado_en = CURRENT_TIMESTAMP WHERE id = :a"), {**ent, "a": aliado_id})
        if rel:
            conn.execute(text(f"UPDATE org_aliados SET {', '.join(f'{k} = :{k}' for k in rel)}, "
                              "actualizado_en = CURRENT_TIMESTAMP WHERE id = :r"), {**rel, "r": relacion_id})
    return {"entidad": sorted(ent), "relacion": sorted(rel)}


def cambiar(engine: Engine, organizacion_id: int, relacion_id: int, datos: dict, usuario: str) -> list[str]:
    """Estado, riesgo y/o diligencia, con motivo obligatorio y registro en el historial."""
    motivo = _motivo(datos.get("motivo"))
    with engine.begin() as conn:
        f = conn.execute(text("SELECT estado, nivel_riesgo, proxima_revision, dd_estado, dd_fecha, dd_nivel FROM org_aliados "
                              "WHERE id = :r AND organizacion_id = :o FOR UPDATE"),
                         {"r": relacion_id, "o": organizacion_id}).mappings().first()
        if f is None:
            raise LookupError("El aliado no existe en esta organización.")
        sets: dict = {}
        hechos: list[str] = []
        if datos.get("estado") is not None and datos["estado"] != f["estado"]:
            if datos["estado"] not in ESTADOS:
                raise ErrorAliado("Estado no válido.")
            sets.update(estado=datos["estado"], fecha_estado=date.today())
            _historial(conn, relacion_id, "estado", ESTADOS[f["estado"]], ESTADOS[datos["estado"]], motivo, usuario)
            hechos.append(f"estado {ESTADOS[f['estado']]} → {ESTADOS[datos['estado']]}")
        if datos.get("nivel_riesgo") is not None and datos["nivel_riesgo"] != f["nivel_riesgo"]:
            if datos["nivel_riesgo"] not in NIVELES:
                raise ErrorAliado("Nivel de riesgo no válido.")
            sets["nivel_riesgo"] = datos["nivel_riesgo"]
            _historial(conn, relacion_id, "riesgo", f["nivel_riesgo"], datos["nivel_riesgo"], motivo, usuario)
            hechos.append(f"riesgo {f['nivel_riesgo'] or 'sin calificar'} → {datos['nivel_riesgo']}")
        if "proxima_revision" in datos and datos["proxima_revision"] != f["proxima_revision"]:
            sets["proxima_revision"] = datos["proxima_revision"]
            if datos.get("nivel_riesgo") is None or datos["nivel_riesgo"] == f["nivel_riesgo"]:
                _historial(conn, relacion_id, "revision", str(f["proxima_revision"] or ""),
                           str(datos["proxima_revision"] or ""), motivo, usuario)
            hechos.append("próxima revisión")
        if datos.get("dd_estado") is not None and datos["dd_estado"] != f["dd_estado"]:
            if datos["dd_estado"] not in DD_ESTADOS:
                raise ErrorAliado("Estado de diligencia no válido.")
            sets["dd_estado"] = datos["dd_estado"]
            if datos["dd_estado"] == "completa" and not datos.get("dd_fecha") and not f["dd_fecha"]:
                sets["dd_fecha"] = date.today()
            _historial(conn, relacion_id, "diligencia", DD_ESTADOS[f["dd_estado"]], DD_ESTADOS[datos["dd_estado"]],
                       motivo, usuario)
            hechos.append(f"diligencia {DD_ESTADOS[f['dd_estado']]} → {DD_ESTADOS[datos['dd_estado']]}")
        for k in ("dd_fecha", "dd_nivel"):
            if k in datos and datos[k] != f[k]:
                if k == "dd_nivel" and datos[k] is not None and datos[k] not in DD_NIVELES:
                    raise ErrorAliado("Nivel de debida diligencia no válido.")
                sets[k] = datos[k]
        if not sets:
            raise ErrorAliado("No hay cambios para registrar.")
        conn.execute(text(f"UPDATE org_aliados SET {', '.join(f'{k} = :{k}' for k in sets)}, "
                          "actualizado_en = CURRENT_TIMESTAMP WHERE id = :r"), {**sets, "r": relacion_id})
    return hechos or ["datos de la diligencia"]
