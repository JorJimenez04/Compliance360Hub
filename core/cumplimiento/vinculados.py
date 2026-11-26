"""
Personas vinculadas, contratos y calificación de riesgo del cliente (migrados de la app anterior).

Usa las mismas tablas que la app Streamlit (migraciones 028–032), así que lo que ya se
registró allá aparece aquí sin mover datos:

  cliente_personas          representantes, accionistas, beneficiarios finales, directores…
  cliente_contratos         un contrato por empresa del grupo, con su estado y contactos
  contrato_servicios        servicios activos de cada contrato
  cliente_historial_riesgo  cada calificación de riesgo, con motivo y responsable
  cliente_documentos        documentos registrados en la app anterior (solo consulta)
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Engine, text

ROLES_PERSONA = ("Representante Legal", "Director", "Accionista", "Beneficiario Final (UBO)", "Apoderado", "Otro")
TIPOS_DOCUMENTO = ("CC", "CE", "NIT", "Pasaporte", "PPT", "Otro")
EMPRESAS_GRUPO = ("Holdings BPO", "Adamo Services", "Paycop")
ESTADOS_CONTRATO = ("Prospecto", "Activo", "Suspendido", "Terminado")
SERVICIOS = ("Dispersión", "Monetización", "Monitoreo de Transacciones", "Compliance 360")
NIVELES = ("Alto", "Medio", "Bajo")          # la calificación nueva usa tres niveles (decisión de Jorge)


class ErrorVinculado(ValueError):
    pass


def _texto(v):
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


# ---------- Personas vinculadas ----------
CAMPOS_PERSONA = ("nombre_completo", "tipo_documento", "numero_documento", "nacionalidad", "rol",
                  "pct_participacion", "es_pep", "en_listas_restriccion", "fecha_verificacion", "notas")


def _validar_persona(datos: dict, parcial: bool) -> dict:
    v = {k: _texto(datos[k]) for k in CAMPOS_PERSONA if k in datos}
    if not parcial or "nombre_completo" in v:
        if not v.get("nombre_completo") or len(v["nombre_completo"]) < 3:
            raise ErrorVinculado("Indique el nombre completo de la persona.")
    if not parcial or "rol" in v:
        if v.get("rol") not in ROLES_PERSONA:
            raise ErrorVinculado("Rol no válido.")
    if v.get("tipo_documento") is not None and v["tipo_documento"] not in TIPOS_DOCUMENTO:
        raise ErrorVinculado("Tipo de documento no válido.")
    if v.get("pct_participacion") is not None and not 0 <= float(v["pct_participacion"]) <= 100:
        raise ErrorVinculado("La participación debe estar entre 0 y 100 %.")
    for b in ("es_pep", "en_listas_restriccion"):
        if b in v:
            v[b] = 1 if v[b] else 0
    if not parcial:
        v.setdefault("nacionalidad", "Colombia")
    return v


def _participacion_total(conn, cliente_id: int, excluir: int | None = None) -> float:
    return float(conn.scalar(text(
        "SELECT COALESCE(SUM(pct_participacion), 0) FROM cliente_personas WHERE cliente_id = :c AND activo = 1 "
        "AND rol = 'Accionista' AND id IS DISTINCT FROM :x"), {"c": cliente_id, "x": excluir}))


def _controlar_participacion(conn, cliente_id: int, persona_id: int | None, v: dict, rol_actual: str | None) -> None:
    rol = v.get("rol", rol_actual)
    if rol == "Accionista" and v.get("pct_participacion") is not None:
        total = _participacion_total(conn, cliente_id, persona_id) + float(v["pct_participacion"])
        if total > 100.0001:
            raise ErrorVinculado(f"Los accionistas sumarían {total:.2f} %: revise las participaciones.")


def listar_personas(engine: Engine, cliente_id: int, incluir_inactivas: bool = False) -> list[dict]:
    with engine.connect() as conn:
        filas = conn.execute(text(
            "SELECT id, nombre_completo, tipo_documento, numero_documento, nacionalidad, rol, pct_participacion, "
            "es_pep, en_listas_restriccion, fecha_verificacion, activo, notas, creado_por, created_at, updated_at "
            "FROM cliente_personas WHERE cliente_id = :c AND (activo = 1 OR :todas) "
            "ORDER BY activo DESC, array_position(:orden, rol), nombre_completo"),
            {"c": cliente_id, "todas": incluir_inactivas, "orden": list(ROLES_PERSONA)}).mappings().all()
    return [{**dict(f), "pct_participacion": float(f["pct_participacion"]) if f["pct_participacion"] is not None else None,
             "es_pep": bool(f["es_pep"]), "en_listas_restriccion": bool(f["en_listas_restriccion"]),
             "activo": bool(f["activo"])} for f in filas]


def crear_persona(engine: Engine, cliente_id: int, datos: dict, usuario: str) -> int:
    v = _validar_persona(datos, parcial=False)
    with engine.begin() as conn:
        _controlar_participacion(conn, cliente_id, None, v, None)
        cols = list(v)                                  # claves de una lista fija, no de la petición
        return conn.execute(text(
            f"INSERT INTO cliente_personas ({', '.join(cols)}, cliente_id, creado_por) "
            f"VALUES ({', '.join(':' + c for c in cols)}, :cliente_id, :u) RETURNING id"),
            {**v, "cliente_id": cliente_id, "u": usuario}).scalar_one()


def actualizar_persona(engine: Engine, cliente_id: int, persona_id: int, datos: dict) -> dict:
    v = _validar_persona(datos, parcial=True)
    if "activo" in datos:
        v["activo"] = 1 if datos["activo"] else 0
    if not v:
        raise ErrorVinculado("No hay cambios.")
    with engine.begin() as conn:
        actual = conn.execute(text("SELECT rol, nombre_completo FROM cliente_personas WHERE id = :p AND cliente_id = :c"),
                              {"p": persona_id, "c": cliente_id}).mappings().first()
        if actual is None:
            raise LookupError("La persona no existe.")
        if v.get("activo", 1):
            _controlar_participacion(conn, cliente_id, persona_id, v, actual["rol"])
        sets = ", ".join(f"{k} = :{k}" for k in v)
        conn.execute(text(f"UPDATE cliente_personas SET {sets} WHERE id = :p"), {**v, "p": persona_id})
    return {"nombre": actual["nombre_completo"]}


def resumen_personas(personas: list[dict]) -> dict:
    activas = [p for p in personas if p["activo"]]
    return {
        "total": len(activas),
        "pep": sum(p["es_pep"] for p in activas),
        "en_listas": sum(p["en_listas_restriccion"] for p in activas),
        "participacion_accionistas": round(sum(p["pct_participacion"] or 0 for p in activas if p["rol"] == "Accionista"), 2),
        "tiene_representante": any(p["rol"] == "Representante Legal" for p in activas),
        "tiene_beneficiario_final": any(p["rol"] == "Beneficiario Final (UBO)" for p in activas),
    }


# ---------- Contratos y servicios ----------
CAMPOS_CONTRATO = ("estado", "fecha_inicio", "fecha_vencimiento", "contrato_firmado", "fecha_firma", "numero_contrato",
                   "contacto_operativo", "email_operativo", "telefono_operativo", "contacto_compliance",
                   "email_compliance", "sla_contratado", "volumen_mensual_cop", "num_transacciones_mes", "notas")


def listar_contratos(engine: Engine, cliente_id: int) -> list[dict]:
    with engine.connect() as conn:
        contratos = [dict(f) for f in conn.execute(text(
            "SELECT * FROM cliente_contratos WHERE cliente_id = :c ORDER BY array_position(:orden, empresa_grupo)"),
            {"c": cliente_id, "orden": list(EMPRESAS_GRUPO)}).mappings()]
        servicios = conn.execute(text(
            "SELECT contrato_id, servicio, estado, fecha_activacion, fecha_terminacion FROM contrato_servicios "
            "WHERE contrato_id = ANY(:ids) ORDER BY array_position(:orden, servicio)"),
            {"ids": [c["id"] for c in contratos], "orden": list(SERVICIOS)}).mappings().all()
    hoy = date.today()
    for c in contratos:
        c["contrato_firmado"] = bool(c["contrato_firmado"])
        c["servicios"] = [dict(s) for s in servicios if s["contrato_id"] == c["id"]]
        venc = c.get("fecha_vencimiento")
        c["dias_para_vencer"] = (venc - hoy).days if venc else None
    return contratos


def guardar_contrato(engine: Engine, cliente_id: int, empresa_grupo: str, datos: dict, usuario: str) -> int:
    if empresa_grupo not in EMPRESAS_GRUPO:
        raise ErrorVinculado("Empresa del grupo no válida.")
    v = {k: _texto(datos[k]) for k in CAMPOS_CONTRATO if k in datos}
    if "estado" in v and v["estado"] not in ESTADOS_CONTRATO:
        raise ErrorVinculado("Estado de contrato no válido.")
    if "contrato_firmado" in v:
        v["contrato_firmado"] = 1 if v["contrato_firmado"] else 0
    for n in ("volumen_mensual_cop", "num_transacciones_mes"):
        if v.get(n) is not None and float(v[n]) < 0:
            raise ErrorVinculado("Los volúmenes no pueden ser negativos.")
    if v.get("fecha_inicio") and v.get("fecha_vencimiento") and str(v["fecha_vencimiento"]) < str(v["fecha_inicio"]):
        raise ErrorVinculado("El vencimiento no puede ser anterior al inicio.")
    servicios = datos.get("servicios")
    if servicios is not None and any(s not in SERVICIOS for s in servicios):
        raise ErrorVinculado("Servicio no válido.")
    cols = list(v)
    with engine.begin() as conn:
        actualiza = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols) or "empresa_grupo = EXCLUDED.empresa_grupo"
        cid = conn.execute(text(
            f"INSERT INTO cliente_contratos (cliente_id, empresa_grupo, creado_por{''.join(', ' + c for c in cols)}) "
            f"VALUES (:cliente_id, :empresa, :u{''.join(', :' + c for c in cols)}) "
            f"ON CONFLICT (cliente_id, empresa_grupo) DO UPDATE SET {actualiza} RETURNING id"),
            {**v, "cliente_id": cliente_id, "empresa": empresa_grupo, "u": usuario}).scalar_one()
        if servicios is not None:
            for s in SERVICIOS:
                if s in servicios:
                    conn.execute(text(
                        "INSERT INTO contrato_servicios (contrato_id, servicio, estado, fecha_activacion, creado_por) "
                        "VALUES (:c, :s, 'Activo', CURRENT_DATE, :u) ON CONFLICT (contrato_id, servicio) DO UPDATE "
                        "SET estado = 'Activo', fecha_terminacion = NULL, "
                        "    fecha_activacion = COALESCE(contrato_servicios.fecha_activacion, CURRENT_DATE)"),
                        {"c": cid, "s": s, "u": usuario})
                else:
                    conn.execute(text(
                        "UPDATE contrato_servicios SET estado = 'Terminado', fecha_terminacion = CURRENT_DATE "
                        "WHERE contrato_id = :c AND servicio = :s AND estado <> 'Terminado'"), {"c": cid, "s": s})
    return cid


# ---------- Calificación de riesgo ----------
def historial_riesgo(engine: Engine, cliente_id: int) -> list[dict]:
    with engine.connect() as conn:
        return [dict(f) for f in conn.execute(text(
            "SELECT id, puntaje_anterior, puntaje_nuevo, nivel_anterior, nivel_nuevo, motivo, observaciones, "
            "registrado_por, registrado_en FROM cliente_historial_riesgo WHERE cliente_id = :c "
            "ORDER BY registrado_en DESC, id DESC"), {"c": cliente_id}).mappings()]


def registrar_calificacion(conn, cliente_id: int, *, nivel_nuevo: str, puntaje_nuevo: int | None,
                           motivo: str | None, observaciones: str | None, usuario: str) -> None:
    """Escribe la calificación en el historial y en la ficha (dentro de la transacción del llamador)."""
    actual = conn.execute(text("SELECT nivel_riesgo, puntaje_riesgo, es_pep FROM clientes WHERE id = :c FOR UPDATE"),
                          {"c": cliente_id}).mappings().first()
    if actual is None:
        raise LookupError("El cliente no existe.")
    puntaje = puntaje_nuevo if puntaje_nuevo is not None else (actual["puntaje_riesgo"] or 0)
    conn.execute(text(
        "INSERT INTO cliente_historial_riesgo (cliente_id, puntaje_anterior, puntaje_nuevo, nivel_anterior, nivel_nuevo, "
        "  motivo, observaciones, era_pep, registrado_por) VALUES (:c, :pa, :pn, :na, :nn, :m, :o, :pep, :u)"),
        {"c": cliente_id, "pa": actual["puntaje_riesgo"], "pn": puntaje, "na": actual["nivel_riesgo"], "nn": nivel_nuevo,
         "m": motivo, "o": observaciones, "pep": actual["es_pep"] or 0, "u": usuario})
    conn.execute(text(
        "UPDATE clientes SET nivel_riesgo = :n, puntaje_riesgo = :p, fecha_ultima_calificacion = CURRENT_DATE, "
        "updated_at = CURRENT_TIMESTAMP WHERE id = :c"), {"n": nivel_nuevo, "p": puntaje, "c": cliente_id})


def calificar(engine: Engine, cliente_id: int, nivel: str, puntaje: int | None, motivo: str | None,
              observaciones: str | None, usuario: str, proxima_revision: date | None = None) -> None:
    if nivel not in NIVELES:
        raise ErrorVinculado("Nivel no válido: use Alto, Medio o Bajo.")
    if puntaje is not None and not 0 <= int(puntaje) <= 100:
        raise ErrorVinculado("El puntaje debe estar entre 0 y 100.")
    motivo = _texto(motivo)
    if not motivo or len(motivo) < 10:
        raise ErrorVinculado("Explique el motivo de la calificación (mínimo 10 caracteres).")
    with engine.begin() as conn:
        registrar_calificacion(conn, cliente_id, nivel_nuevo=nivel, puntaje_nuevo=puntaje, motivo=motivo,
                               observaciones=_texto(observaciones), usuario=usuario)
        if proxima_revision:
            conn.execute(text("UPDATE clientes SET proxima_revision = :r WHERE id = :c"),
                         {"r": proxima_revision, "c": cliente_id})


# ---------- Documentos de la app anterior ----------
def documentos_anteriores(engine: Engine, cliente_id: int) -> list[dict]:
    with engine.connect() as conn:
        if not conn.scalar(text("SELECT to_regclass('cliente_documentos') IS NOT NULL")):
            return []
        return [dict(f) for f in conn.execute(text(
            "SELECT id, titulo, carpeta, estado, formato, url, version, fecha_emision, creado_por, updated_at "
            "FROM cliente_documentos WHERE cliente_id = :c ORDER BY carpeta, titulo"), {"c": cliente_id}).mappings()]
