"""
Requerimientos sugeridos por la plataforma (fase 2, cierre).

La plataforma PROPONE; el oficial decide con un clic (nunca se crean solos). Cada sugerencia
tiene una clave estable: si ya existe un requerimiento con esa clave abierto, o creado en los
últimos 90 días, no se vuelve a sugerir.

Qué se sugiere:
  - a un subcliente: completar documentación exigida (si su carpeta está enlazada);
    actualizar su perfil transaccional si opera >20 % por encima, o declararlo si no tiene;
  - a la organización: renovar contrato, póliza o licencia de un aliado vencido o por vencer;
    hacer la revisión periódica vencida de un aliado; completar los documentos de un aliado.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import Engine, text

from core.cumplimiento import aliados as ali
from core.cumplimiento import documentos as doc
from core.cumplimiento import requerimientos as rq
from core.cumplimiento import tablero as tb

PLAZO_DIAS = 15
VIGENCIA_DIAS = 90


def _ya_atendidas(conn, organizacion_id: int, hoy: date) -> set[str]:
    return set(conn.scalars(text(
        "SELECT clave_origen FROM requerimientos WHERE organizacion_id = :o AND clave_origen IS NOT NULL "
        "AND (estado = ANY(:a) OR creado_en >= :desde)"),
        {"o": organizacion_id, "a": list(rq.ABIERTOS), "desde": hoy - timedelta(days=VIGENCIA_DIAS)}))


def sugerir(engine: Engine, organizacion_id: int, hoy: date | None = None) -> list[dict]:
    hoy = hoy or date.today()
    s: list[dict] = []

    def poner(clave, dirigido_a, tipo, asunto, motivo, prioridad="media", cliente_id=None, cliente=None, descripcion=None):
        s.append({"clave": clave, "dirigido_a": dirigido_a, "cliente_id": cliente_id, "cliente": cliente, "tipo": tipo,
                  "asunto": asunto, "motivo": motivo, "prioridad": prioridad, "descripcion": descripcion or motivo,
                  "fecha_limite": (hoy + timedelta(days=PLAZO_DIAS)).isoformat()})

    with engine.connect() as conn:
        atendidas = _ya_atendidas(conn, organizacion_id, hoy)
        clientes = [dict(f) for f in conn.execute(text(
            "SELECT id, razon_social, carpeta_onedrive FROM clientes WHERE organizacion_id = :o ORDER BY razon_social"),
            {"o": organizacion_id}).mappings()]

    # ── Subclientes: documentación ──
    for c in clientes:
        if not c["carpeta_onedrive"]:
            continue
        e = doc.estado_propio(engine, c["id"])
        if e["faltan"]:
            poner(f"docs:{c['id']}", "cliente", "actualizacion_documental",
                  f"Documentación pendiente de {c['razon_social']}",
                  "Faltan en su carpeta: " + ", ".join(e["faltan"]) + ".", cliente_id=c["id"], cliente=c["razon_social"])

    # ── Subclientes: perfil transaccional (últimos 3 meses) ──
    desde = (hoy.replace(day=1) - timedelta(days=62)).replace(day=1)
    t = tb.tablero(engine, desde, hoy, organizacion_id, hoy)
    for o in t["organizaciones"]:
        for sc in o["subclientes"]:
            if not sc["cliente_id"] or sc["monto_pagado"] <= 0:
                continue
            dv = sc["desviacion_perfil"]
            if dv is not None and dv > tb.SOBRE_PERFIL:
                poner(f"perfil:{sc['cliente_id']}:{hoy:%Y-%m}", "cliente", "actualizacion_documental",
                      f"Actualizar el perfil transaccional de {sc['nombre']}",
                      f"Opera {dv:.0%} por encima de su perfil declarado (promedio mensual de los últimos 3 meses). "
                      "Pedir la actualización del perfil y el soporte del origen de los fondos.",
                      "alta" if dv > 0.5 else "media", sc["cliente_id"], sc["nombre"])
            elif sc["perfil_mensual"] is None:
                poner(f"sinperfil:{sc['cliente_id']}", "cliente", "actualizacion_documental",
                      f"Declarar el perfil transaccional de {sc['nombre']}",
                      "Opera sin perfil transaccional declarado (volumen y número de operaciones esperados al mes).",
                      cliente_id=sc["cliente_id"], cliente=sc["nombre"])

    # ── Aliados bancarios ──
    for a in ali.listar(engine, organizacion_id, hoy)["aliados"]:
        if a["estado"] == "terminado":
            continue
        for f in a["documentos"]["filas"]:
            if f["estado_vence"] in ("vencido", "por_vencer"):
                vencido = f["estado_vence"] == "vencido"
                poner(f"vence:{a['id']}:{f['codigo']}:{f['vence']}", "organizacion", "actualizacion_documental",
                      f"Renovar {f['nombre'].lower()} con {a['nombre']}",
                      f"{f['nombre']}: {'venció el' if vencido else 'vence el'} {f['vence'].isoformat()}.",
                      "alta" if vencido else "media")
        if a["estado"] in ("activo", "onboarding"):
            if a["proxima_revision"] and a["proxima_revision"] < hoy:
                poner(f"revision:{a['id']}:{a['proxima_revision']}", "organizacion", "otro",
                      f"Revisión periódica de {a['nombre']}",
                      f"La revisión del aliado venció el {a['proxima_revision'].isoformat()}: actualizar diligencia y riesgo.", "alta")
            faltan = [f["nombre"] for f in a["documentos"]["filas"] if f["exigido"] and not f["cargado"]]
            if a["documentos"]["carpeta"] and faltan:
                poner(f"docsaliado:{a['id']}", "organizacion", "actualizacion_documental",
                      f"Completar los documentos de {a['nombre']}", "Faltan: " + ", ".join(faltan) + ".")

    orden = {"alta": 0, "media": 1, "baja": 2}
    return sorted((x for x in s if x["clave"] not in atendidas), key=lambda x: (orden[x["prioridad"]], x["asunto"]))


def crear_desde_sugerencia(engine: Engine, organizacion_id: int, clave: str, usuario: str, hoy: date | None = None) -> dict:
    hoy = hoy or date.today()
    sug = next((x for x in sugerir(engine, organizacion_id, hoy) if x["clave"] == clave), None)
    if sug is None:
        raise LookupError("Esa sugerencia ya no aplica o ya se convirtió en requerimiento.")
    datos = {"dirigido_a": sug["dirigido_a"], "cliente_id": sug["cliente_id"], "origen": "oficial", "tipo": sug["tipo"],
             "asunto": sug["asunto"][:200], "descripcion": sug["descripcion"], "fecha_recibido": hoy,
             "fecha_limite": date.fromisoformat(sug["fecha_limite"]), "prioridad": sug["prioridad"],
             "comentario": "Creado desde una sugerencia de la plataforma."}
    return rq.crear(engine, organizacion_id, datos, usuario, clave_origen=clave)
