"""
Requerimientos de compliance (fase 2, parte B; migración 046).

Lo que se le pide a una organización o a uno de sus clientes. Cada requerimiento:
  - tiene un consecutivo REQ-AAAA-NNN por organización;
  - se dirige a la organización o a uno de SUS clientes (nunca a otro);
  - si lo pide un aliado bancario, queda enlazado a la relación de ESA organización;
  - pasa por Recibido → En preparación → En revisión del oficial → Enviado → Cerrado,
    o «Requiere seguimiento» si el solicitante vuelve a preguntar;
  - «Enviado» exige el resumen de la respuesta; cerrar o pasar a seguimiento exige motivo;
  - todo queda en requerimiento_eventos.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Engine, text

ORIGENES = {"aliado": "Aliado bancario", "director": "Director de cumplimiento", "regulador": "Regulador", "auditoria": "Auditoría",
            "oficial": "Oficial de cumplimiento", "otro": "Otro"}
TIPOS = {"kyc_kyb": "KYC / KYB de un cliente", "rfi_transacciones": "RFI de transacciones",
         "recertificacion_aml": "Recertificación AML", "reporte_periodico": "Reporte periódico",
         "actualizacion_documental": "Actualización documental", "otro": "Otro"}
CANALES = {"correo": "Correo", "portal": "Portal del solicitante", "reunion": "Reunión", "oficio": "Oficio", "otro": "Otro"}
PRIORIDADES = {"alta": "Alta", "media": "Media", "baja": "Baja"}
ESTADOS = {"recibido": "Recibido", "en_preparacion": "En preparación", "en_revision": "En revisión del oficial",
           "enviado": "Enviado", "cerrado": "Cerrado", "seguimiento": "Requiere seguimiento"}
ABIERTOS = ("recibido", "en_preparacion", "en_revision", "seguimiento")
CATALOGOS = {"origenes": ORIGENES, "tipos": TIPOS, "canales": CANALES, "prioridades": PRIORIDADES, "estados": ESTADOS}
DIAS_POR_VENCER = 3
MINIMO = 10

CAMPOS = ("dirigido_a", "cliente_id", "origen", "relacion_aliado_id", "origen_detalle", "solicitante", "canal", "tipo",
          "asunto", "descripcion", "referencias_tx", "fecha_recibido", "fecha_limite", "prioridad", "responsable",
          "carpeta_evidencias")


class ErrorRequerimiento(ValueError):
    pass


def _texto(v):
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


# ---------- Validación ----------
def _validar(conn, organizacion_id: int, datos: dict, actual: dict | None = None) -> dict:
    """Valida los campos que vienen, con el estado final resultante (actual + cambios)."""
    v = {k: _texto(datos[k]) for k in CAMPOS if k in datos}
    if "referencias_tx" in v:
        v["referencias_tx"] = [r for r in dict.fromkeys(_texto(x) for x in (datos["referencias_tx"] or [])) if r]
    final = {**(actual or {}), **v}

    if not final.get("asunto") or len(final["asunto"]) < 5:
        raise ErrorRequerimiento("Indique el asunto del requerimiento (al menos 5 caracteres).")
    if final.get("tipo") not in TIPOS:
        raise ErrorRequerimiento("Tipo de requerimiento no válido.")
    if final.get("origen") not in ORIGENES:
        raise ErrorRequerimiento("Origen no válido.")
    if final.get("canal") is not None and final["canal"] not in CANALES:
        raise ErrorRequerimiento("Canal no válido.")
    if final.get("prioridad", "media") not in PRIORIDADES:
        raise ErrorRequerimiento("Prioridad no válida.")
    if not final.get("fecha_recibido"):
        raise ErrorRequerimiento("Indique la fecha en que se recibió.")
    if final["fecha_recibido"] > date.today():
        raise ErrorRequerimiento("La fecha de recibido no puede ser futura.")
    if final.get("fecha_limite") and final["fecha_limite"] < final["fecha_recibido"]:
        raise ErrorRequerimiento("La fecha límite no puede ser anterior a la de recibido.")

    # A quién: la organización o uno de SUS clientes
    if final.get("dirigido_a") not in ("organizacion", "cliente"):
        raise ErrorRequerimiento("Indique a quién se dirige: la organización o uno de sus clientes.")
    if final["dirigido_a"] == "organizacion":
        v["cliente_id"] = final["cliente_id"] = None
    else:
        if not final.get("cliente_id"):
            raise ErrorRequerimiento("Elija el cliente al que se dirige.")
        if not conn.scalar(text("SELECT 1 FROM clientes WHERE id = :c AND organizacion_id = :o"),
                           {"c": final["cliente_id"], "o": organizacion_id}):
            raise ErrorRequerimiento("El cliente no pertenece a esta organización.")

    # De quién: si es un aliado, debe ser aliado de ESTA organización
    if final["origen"] == "aliado":
        if not final.get("relacion_aliado_id"):
            raise ErrorRequerimiento("Elija el aliado bancario que lo pidió.")
        if not conn.scalar(text("SELECT 1 FROM org_aliados WHERE id = :r AND organizacion_id = :o"),
                           {"r": final["relacion_aliado_id"], "o": organizacion_id}):
            raise ErrorRequerimiento("Ese aliado no es aliado de esta organización.")
    else:
        v["relacion_aliado_id"] = final["relacion_aliado_id"] = None
    if final.get("carpeta_evidencias") and not str(final["carpeta_evidencias"]).startswith("https://"):
        raise ErrorRequerimiento("El enlace de la carpeta debe empezar por https://")
    return v


def _beneficiarios(datos) -> list[dict] | None:
    """Beneficiarios involucrados: [{id_beneficiario, nombre, actividad, notas}]. None = no se tocan."""
    if datos is None:
        return None
    vistos: dict[str, dict] = {}
    for b in datos:
        nombre = _texto(b.get("nombre"))
        if not nombre:
            raise ErrorRequerimiento("Cada beneficiario necesita un nombre.")
        doc = _texto(b.get("id_beneficiario"))
        vistos.setdefault((doc or nombre).lower(), {"id_beneficiario": doc, "nombre": nombre,
                                                    "actividad": _texto(b.get("actividad")), "notas": _texto(b.get("notas"))})
    if len(vistos) > 50:
        raise ErrorRequerimiento("Máximo 50 beneficiarios por requerimiento.")
    return list(vistos.values())


def _guardar_beneficiarios(conn, rid: int, lista: list[dict]) -> None:
    conn.execute(text("DELETE FROM requerimiento_beneficiarios WHERE requerimiento_id = :r"), {"r": rid})
    for b in lista:
        conn.execute(text("INSERT INTO requerimiento_beneficiarios (requerimiento_id, id_beneficiario, nombre, actividad, notas) "
                          "VALUES (:r, :id_beneficiario, :nombre, :actividad, :notas)"), {"r": rid, **b})


def _evento(conn, rid: int, tipo: str, antes, despues, comentario, usuario: str) -> None:
    conn.execute(text("INSERT INTO requerimiento_eventos (requerimiento_id, tipo, valor_anterior, valor_nuevo, comentario, usuario) "
                      "VALUES (:r, :t, :a, :d, :c, :u)"),
                 {"r": rid, "t": tipo, "a": antes, "d": despues, "c": comentario, "u": usuario})


def _consecutivo(conn, organizacion_id: int, anio: int) -> str:
    # Bloquea la organización para que dos altas simultáneas no tomen el mismo número
    conn.execute(text("SELECT id FROM organizaciones WHERE id = :o FOR UPDATE"), {"o": organizacion_id})
    n = conn.scalar(text("SELECT COALESCE(max(split_part(consecutivo, '-', 3)::int), 0) FROM requerimientos "
                         "WHERE organizacion_id = :o AND consecutivo LIKE :p"),
                    {"o": organizacion_id, "p": f"REQ-{anio}-%"})
    return f"REQ-{anio}-{n + 1:03d}"


# ---------- Escritura ----------
def crear(engine: Engine, organizacion_id: int, datos: dict, usuario: str, clave_origen: str | None = None) -> dict:
    with engine.begin() as conn:
        base = {"prioridad": "media", "responsable": usuario, "referencias_tx": []}
        v = {**base, **_validar(conn, organizacion_id, {**base, **datos})}
        consecutivo = _consecutivo(conn, organizacion_id, v["fecha_recibido"].year)
        cols = list(v) + ["organizacion_id", "consecutivo", "creado_por", "clave_origen"]
        rid = conn.scalar(text(f"INSERT INTO requerimientos ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)}) RETURNING id"),
                          {**v, "organizacion_id": organizacion_id, "consecutivo": consecutivo, "creado_por": usuario,
                           "clave_origen": clave_origen})
        _evento(conn, rid, "alta", None, ESTADOS["recibido"], _texto(datos.get("comentario")), usuario)
        bens = _beneficiarios(datos.get("beneficiarios"))
        if bens:
            _guardar_beneficiarios(conn, rid, bens)
    return {"id": rid, "consecutivo": consecutivo}


def _actual(conn, organizacion_id: int, rid: int) -> dict:
    f = conn.execute(text("SELECT * FROM requerimientos WHERE id = :r AND organizacion_id = :o FOR UPDATE"),
                     {"r": rid, "o": organizacion_id}).mappings().first()
    if f is None:
        raise LookupError("El requerimiento no existe en esta organización.")
    return dict(f)


def actualizar(engine: Engine, organizacion_id: int, rid: int, datos: dict, usuario: str) -> list[str]:
    with engine.begin() as conn:
        actual = _actual(conn, organizacion_id, rid)
        v = _validar(conn, organizacion_id, datos, {k: actual[k] for k in CAMPOS})
        cambios = [k for k in v if v[k] != actual[k]]
        if cambios:
            conn.execute(text(f"UPDATE requerimientos SET {', '.join(f'{k} = :{k}' for k in cambios)}, "
                              "actualizado_en = CURRENT_TIMESTAMP WHERE id = :r"), {**{k: v[k] for k in cambios}, "r": rid})
        bens = _beneficiarios(datos.get("beneficiarios"))
        if bens is not None:
            antes = [dict(f._mapping) for f in conn.execute(text(
                "SELECT id_beneficiario, nombre, actividad, notas FROM requerimiento_beneficiarios "
                "WHERE requerimiento_id = :r ORDER BY id"), {"r": rid})]
            if antes != bens:
                _guardar_beneficiarios(conn, rid, bens)
                cambios.append("beneficiarios")
        if cambios:
            _evento(conn, rid, "edicion", None, ", ".join(cambios), None, usuario)
    return cambios


def cambiar_estado(engine: Engine, organizacion_id: int, rid: int, estado: str, usuario: str, *,
                   comentario: str | None = None, fecha_envio: date | None = None,
                   resumen_respuesta: str | None = None) -> None:
    if estado not in ESTADOS:
        raise ErrorRequerimiento("Estado no válido.")
    comentario, resumen = _texto(comentario), _texto(resumen_respuesta)
    with engine.begin() as conn:
        actual = _actual(conn, organizacion_id, rid)
        if estado == actual["estado"]:
            raise ErrorRequerimiento("El requerimiento ya está en ese estado.")
        sets: dict = {"estado": estado}
        if estado == "enviado":
            if not resumen or len(resumen) < MINIMO:
                raise ErrorRequerimiento(f"Resuma lo que se envió (al menos {MINIMO} caracteres).")
            envio = fecha_envio or date.today()
            if envio < actual["fecha_recibido"] or envio > date.today():
                raise ErrorRequerimiento("La fecha de envío debe estar entre la de recibido y hoy.")
            sets.update(fecha_envio=envio, resumen_respuesta=resumen)
        elif estado in ("cerrado", "seguimiento"):
            if not comentario or len(comentario) < MINIMO:
                raise ErrorRequerimiento(f"Explique el motivo (al menos {MINIMO} caracteres).")
        conn.execute(text(f"UPDATE requerimientos SET {', '.join(f'{k} = :{k}' for k in sets)}, "
                          "actualizado_en = CURRENT_TIMESTAMP WHERE id = :r"), {**sets, "r": rid})
        _evento(conn, rid, "estado", ESTADOS[actual["estado"]], ESTADOS[estado],
                resumen if estado == "enviado" and not comentario else comentario, usuario)


def agregar_nota(engine: Engine, organizacion_id: int, rid: int, comentario: str, usuario: str) -> None:
    c = _texto(comentario)
    if not c or len(c) < 3:
        raise ErrorRequerimiento("Escriba la nota.")
    with engine.begin() as conn:
        _actual(conn, organizacion_id, rid)
        _evento(conn, rid, "nota", None, None, c, usuario)
        conn.execute(text("UPDATE requerimientos SET actualizado_en = CURRENT_TIMESTAMP WHERE id = :r"), {"r": rid})


# ---------- Consultas ----------
_SELECT = """
    SELECT q.*, c.razon_social AS cliente, b.nombre AS aliado, o.nombre AS organizacion,
           (SELECT COALESCE(json_agg(json_build_object('id_beneficiario', x.id_beneficiario, 'nombre', x.nombre,
                                                       'actividad', x.actividad, 'notas', x.notas) ORDER BY x.id), '[]')
              FROM requerimiento_beneficiarios x WHERE x.requerimiento_id = q.id) AS beneficiarios
      FROM requerimientos q
      JOIN organizaciones o ON o.id = q.organizacion_id
      LEFT JOIN clientes c ON c.id = q.cliente_id
      LEFT JOIN org_aliados r ON r.id = q.relacion_aliado_id
      LEFT JOIN aliados_bancarios b ON b.id = r.aliado_id
"""


def _situacion(q: dict, hoy: date) -> dict:
    """Semáforo de plazo: atrasado, por vencer, a tiempo, sin plazo; y si se envió fuera de plazo."""
    lim = q["fecha_limite"]
    abierto = q["estado"] in ABIERTOS
    if not abierto:
        fuera = bool(lim and q["fecha_envio"] and q["fecha_envio"] > lim)
        return {"plazo": "fuera_de_plazo" if fuera else "cumplido", "dias": None, "abierto": False}
    if not lim:
        return {"plazo": "sin_plazo", "dias": None, "abierto": True}
    dias = (lim - hoy).days
    plazo = "atrasado" if dias < 0 else "por_vencer" if dias <= DIAS_POR_VENCER else "a_tiempo"
    return {"plazo": plazo, "dias": dias, "abierto": True}


def _lista(engine: Engine, donde: str, params: dict, hoy: date | None) -> list[dict]:
    hoy = hoy or date.today()
    with engine.connect() as conn:
        filas = [dict(f._mapping) for f in conn.execute(text(
            _SELECT + f" WHERE {donde} ORDER BY (q.estado = ANY(:abiertos)) DESC, q.fecha_limite NULLS LAST, q.id DESC"),
            {**params, "abiertos": list(ABIERTOS)})]
    for q in filas:
        q["referencias_tx"] = list(q["referencias_tx"] or [])
        q.update(_situacion(q, hoy))
        # Evidencias (solo si la carpeta del requerimiento se encontró en la carpeta Compliance)
        q["sin_evidencia_respuesta"] = (q["estado"] in ("enviado", "cerrado") and q.get("carpeta_item_id") is not None
                                        and not q.get("ev_respuesta"))
    return filas


def resumen(filas: list[dict]) -> dict:
    return {
        "abiertos": sum(q["abierto"] for q in filas),
        "atrasados": sum(q["plazo"] == "atrasado" for q in filas),
        "por_vencer": sum(q["plazo"] == "por_vencer" for q in filas),
        "fuera_de_plazo": sum(q["plazo"] == "fuera_de_plazo" for q in filas),
        "sin_evidencia_respuesta": sum(bool(q.get("sin_evidencia_respuesta")) for q in filas),
        "total": len(filas),
    }


def listar(engine: Engine, organizacion_id: int, hoy: date | None = None) -> dict:
    filas = _lista(engine, "q.organizacion_id = :o", {"o": organizacion_id}, hoy)
    return {"requerimientos": filas, "resumen": resumen(filas)}


def por_cliente(engine: Engine, cliente_id: int, hoy: date | None = None) -> list[dict]:
    return _lista(engine, "q.cliente_id = :c", {"c": cliente_id}, hoy)


def por_aliado(engine: Engine, organizacion_id: int, relacion_id: int, hoy: date | None = None) -> list[dict]:
    return _lista(engine, "q.organizacion_id = :o AND q.relacion_aliado_id = :r", {"o": organizacion_id, "r": relacion_id}, hoy)


def obtener(engine: Engine, organizacion_id: int, rid: int, hoy: date | None = None) -> dict:
    filas = _lista(engine, "q.id = :r AND q.organizacion_id = :o", {"r": rid, "o": organizacion_id}, hoy)
    if not filas:
        raise LookupError("El requerimiento no existe en esta organización.")
    q = filas[0]
    with engine.connect() as conn:
        q["eventos"] = [dict(e._mapping) for e in conn.execute(text(
            "SELECT tipo, valor_anterior, valor_nuevo, comentario, usuario, fecha FROM requerimiento_eventos "
            "WHERE requerimiento_id = :r ORDER BY fecha DESC, id DESC"), {"r": rid})]
    return q


def opciones(engine: Engine, organizacion_id: int) -> dict:
    """Clientes y aliados de la organización, para el formulario."""
    with engine.connect() as conn:
        clientes = [dict(f._mapping) for f in conn.execute(text(
            "SELECT id, razon_social FROM clientes WHERE organizacion_id = :o ORDER BY razon_social"), {"o": organizacion_id})]
        aliados = [dict(f._mapping) for f in conn.execute(text(
            "SELECT r.id, b.nombre, r.estado FROM org_aliados r JOIN aliados_bancarios b ON b.id = r.aliado_id "
            "WHERE r.organizacion_id = :o ORDER BY lower(b.nombre)"), {"o": organizacion_id})]
    return {"clientes": clientes, "aliados": aliados}


def buscar_beneficiarios(engine: Engine, cliente_id: int, termino: str, limite: int = 15) -> list[dict]:
    """Beneficiarios a los que les ha pagado el subcliente, para elegirlos en un requerimiento."""
    t = (_texto(termino) or "")
    if len(t) < 2:
        return []
    with engine.connect() as conn:
        return [dict(f._mapping) for f in conn.execute(text(
            "SELECT t.id_beneficiario, max(t.beneficiario) AS nombre, count(*) AS pagos, sum(t.monto) AS monto "
            "FROM tx_transacciones t JOIN tx_empresas e ON e.nombre_reporte = t.cliente "
            "WHERE e.cliente_id = :c AND t.exitosa AND t.tipo_transaccion ILIKE 'd_bito%' "
            "AND (t.beneficiario ILIKE :q OR t.id_beneficiario ILIKE :q) "
            "GROUP BY t.id_beneficiario ORDER BY sum(t.monto) DESC LIMIT :n"),
            {"c": cliente_id, "q": f"%{t}%", "n": limite})]
