"""
Carpeta Compliance de cada organización (fase 2, cierre; migración 048).

Se pega UNA vez el enlace de la carpeta Compliance de la organización y la plataforma
encuentra por su nombre (sin importar mayúsculas, tildes ni números al inicio):

    Compliance/
      {Subcliente}/                       se enlaza al subcliente si no tiene carpeta propia
        Documentación corporativa/ · Beneficiarios/        (los lee documentos.revisar)
        Requerimientos/REQ-AAAA-NNN - Asunto/              requerimientos dirigidos a él
      Aliados bancarios/{Aliado}/          documentos del aliado
      Requerimientos/REQ-AAAA-NNN - Asunto/                requerimientos dirigidos a la organización
          1. Solicitud/ · 2. Soportes/ · 3. Respuesta/     evidencias

Solo lectura de OneDrive, con la misma conexión de la carga automática.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta

from sqlalchemy import Engine, text

from core.cumplimiento import documentos as doc

logger = logging.getLogger(__name__)

# ---------- Nombres ----------
_SUFIJOS = r"\b(s\s?a\s?s|s\s?a|ltda|limitada|inc|llc|ltd|corp|sociedad|grupo empresarial)\b"


def clave(nombre: str | None) -> str:
    """Nombre comparable: sin tildes, mayúsculas, signos, números de orden ni sufijos societarios."""
    n = doc._norm(nombre or "")
    n = re.sub(r"^\s*\d+\s*[.\-)_]*\s*", "", n)              # «1. Solicitud», «02 - Aliados»
    n = re.sub(r"[^a-z0-9]+", " ", n)
    n = re.sub(_SUFIJOS, " ", n)
    return re.sub(r"\s+", " ", n).strip()


def coincide(carpeta: str, *nombres: str | None) -> bool:
    k = clave(carpeta)
    if not k:
        return False
    for nombre in nombres:
        n = clave(nombre)
        if not n:
            continue
        if k == n:
            return True
        corto, largo = sorted((k, n), key=len)
        if len(corto) >= 4 and re.search(rf"\b{re.escape(corto)}\b", largo):
            return True
    return False


def es_carpeta_aliados(nombre: str) -> bool:
    k = clave(nombre)
    return k.startswith("aliado") or "banking partner" in k or k in ("bancos", "rieles", "aliados bancarios")


def es_carpeta_requerimientos(nombre: str) -> bool:
    return clave(nombre).startswith("requerimiento")


CONSECUTIVO = re.compile(r"REQ[-_ ]?(\d{4})[-_ ]?(\d{1,4})", re.IGNORECASE)


def consecutivo_de(nombre: str) -> str | None:
    m = CONSECUTIVO.search(nombre or "")
    return f"REQ-{m.group(1)}-{int(m.group(2)):03d}" if m else None


def parte_evidencia(nombre: str) -> str | None:
    k = clave(nombre)
    if k.startswith("solicitud") or k.startswith("requerimiento"):
        return "solicitud"
    if k.startswith("soporte") or k.startswith("anexo"):
        return "soportes"
    if k.startswith("respuesta") or k.startswith("enviado"):
        return "respuesta"
    return None


# ---------- Documentos de los aliados ----------
DOCUMENTOS_ALIADO = {
    "contrato": "Contrato",
    "poliza": "Póliza",
    "licencia": "Licencia o autorización del regulador",
    "certificado_existencia": "Certificado de existencia y representación legal",
    "rut": "RUT",
    "aml": "Cuestionario o certificación AML / SARLAFT",
    "estados_financieros": "Estados financieros",
}
VENCIMIENTOS = {"contrato": "vence_contrato", "poliza": "vence_poliza", "licencia": "vence_licencia"}
DIAS_POR_VENCER = 30


def reconocer_aliado(nombre_archivo: str) -> str | None:
    p = doc._palabras(nombre_archivo)
    n = doc._norm(nombre_archivo)
    if p & {"aml", "sarlaft", "sagrilaft", "kyc", "wolfsberg", "cuestionario", "questionnaire", "lavado", "laft", "ptee"}:
        return "aml"
    if p & {"poliza", "policy", "seguro"}:
        return "poliza"
    if p & {"licencia", "license", "licence", "autorizacion", "habilitacion", "resolucion"} or "registro ante" in n:
        return "licencia"
    if p & {"financieros", "financiero", "balance", "eeff", "dictamen"} or "estados financieros" in n:
        return "estados_financieros"
    if "contrato" in p or "agreement" in p or "convenio" in p:
        return "contrato"
    code = doc.reconocer(nombre_archivo)
    return code if code in ("certificado_existencia", "rut") else None


def requisitos_aliado(relacion: dict) -> list[dict]:
    """Qué documentos se exigen al aliado: contrato, AML y existencia siempre; RUT si es colombiano;
    licencia si es entidad regulada. Póliza y estados financieros se muestran pero no se exigen."""
    colombiano = clave(relacion.get("pais") or "colombia") in ("colombia", "co", "col")
    exigidos = {"contrato", "aml", "certificado_existencia"}
    if colombiano:
        exigidos.add("rut")
    if relacion.get("regulado"):
        exigidos.add("licencia")
    return [{"codigo": c, "nombre": n, "exigido": c in exigidos} for c, n in DOCUMENTOS_ALIADO.items()]


def estado_documentos_aliado(conn, relacion: dict, hoy: date | None = None) -> dict:
    hoy = hoy or date.today()
    archivos = [dict(f) for f in conn.execute(text(
        "SELECT id, codigo, nombre_archivo, ruta, web_url, modificado_en, asignacion FROM org_aliado_documentos "
        "WHERE relacion_id = :r ORDER BY ruta"), {"r": relacion["id"]}).mappings()]
    filas = []
    for req in requisitos_aliado(relacion):
        suyos = [a for a in archivos if a["codigo"] == req["codigo"]]
        vence = relacion.get(VENCIMIENTOS[req["codigo"]]) if req["codigo"] in VENCIMIENTOS else None
        estado_vence = None
        if vence:
            estado_vence = "vencido" if vence < hoy else "por_vencer" if vence <= hoy + timedelta(days=DIAS_POR_VENCER) else "vigente"
        filas.append({**req, "cargado": bool(suyos), "archivos": suyos, "vence": vence, "estado_vence": estado_vence})
    return {"filas": filas, "sin_reconocer": [a for a in archivos if a["codigo"] is None],
            "completo": all(f["cargado"] for f in filas if f["exigido"]),
            "carpeta": bool(relacion.get("carpeta_item_id"))}


def asignar_documento_aliado(engine: Engine, organizacion_id: int, documento_id: int, codigo: str | None, usuario: str) -> None:
    if codigo is not None and codigo not in DOCUMENTOS_ALIADO:
        raise ValueError("Documento no válido.")
    with engine.begin() as conn:
        n = conn.execute(text(
            "UPDATE org_aliado_documentos d SET codigo = :c, asignacion = 'manual', asignado_por = :u "
            "FROM org_aliados r WHERE d.id = :i AND r.id = d.relacion_id AND r.organizacion_id = :o"),
            {"c": codigo, "u": usuario, "i": documento_id, "o": organizacion_id}).rowcount
    if not n:
        raise LookupError("El archivo no existe en esta organización.")


# ---------- Enlace ----------
def guardar_enlace(engine: Engine, organizacion_id: int, enlace: str | None) -> None:
    url = doc.validar_enlace(enlace)
    with engine.begin() as conn:
        n = conn.execute(text(
            "UPDATE organizaciones SET carpeta_compliance = :u, carpeta_drive_id = NULL, carpeta_item_id = NULL, "
            "carpeta_nombre = NULL, carpeta_error = NULL, carpeta_resumen = NULL, carpeta_revisada_en = NULL "
            "WHERE id = :o"), {"u": url, "o": organizacion_id}).rowcount
        if not n:
            raise LookupError("La organización no existe.")
        if url is None:                  # se quitó el enlace: se sueltan los subclientes enlazados por esta vía
            conn.execute(text(
                "UPDATE clientes SET carpeta_onedrive = NULL, carpeta_drive_id = NULL, carpeta_item_id = NULL, "
                "carpeta_nombre = NULL, carpeta_origen = 'manual' WHERE organizacion_id = :o AND carpeta_origen = 'compliance'"),
                {"o": organizacion_id})


def estado(engine: Engine, organizacion_id: int) -> dict:
    with engine.connect() as conn:
        f = conn.execute(text("SELECT carpeta_compliance, carpeta_nombre, carpeta_revisada_en, carpeta_error, carpeta_resumen "
                              "FROM organizaciones WHERE id = :o"), {"o": organizacion_id}).mappings().first()
    if f is None:
        raise LookupError("La organización no existe.")
    r = dict(f)
    if isinstance(r["carpeta_resumen"], str):
        r["carpeta_resumen"] = json.loads(r["carpeta_resumen"])
    return r


# ---------- Revisión ----------
def _contar(lector, drive: str, carpeta: dict, profundidad: int = 1) -> int:
    return len(doc._archivos(lector, drive, carpeta, "", profundidad))


def _evidencias(lector, drive: str, carpeta_req: dict) -> dict:
    ev = {"solicitud": 0, "soportes": 0, "respuesta": 0}
    for h in lector.hijos(drive, carpeta_req["id"]):
        if doc._es_carpeta(h):
            parte = parte_evidencia(h["name"])
            if parte:
                ev[parte] += _contar(lector, drive, h, 1)
        else:
            ev["soportes"] += 1                    # archivos sueltos en la carpeta del requerimiento
    return ev


def _carpetas_requerimientos(lector, drive: str, carpeta: dict) -> list[tuple[str, dict]]:
    salida = []
    for h in lector.hijos(drive, carpeta["id"]):
        if doc._es_carpeta(h):
            c = consecutivo_de(h["name"])
            salida.append((c, h))
    return salida


def revisar_organizacion(engine: Engine, organizacion_id: int, lector=None, usuario: str = "sistema") -> dict:
    with engine.connect() as conn:
        o = conn.execute(text("SELECT carpeta_compliance, carpeta_drive_id, carpeta_item_id FROM organizaciones WHERE id = :o"),
                         {"o": organizacion_id}).mappings().first()
        if o is None:
            raise LookupError("La organización no existe.")
        clientes = [dict(f) for f in conn.execute(text(
            "SELECT id, razon_social, carpeta_onedrive, carpeta_origen, carpeta_item_id FROM clientes WHERE organizacion_id = :o"),
            {"o": organizacion_id}).mappings()]
        empresas = {}
        for f in conn.execute(text("SELECT cliente_id, nombre_reporte FROM tx_empresas WHERE organizacion_id = :o AND cliente_id IS NOT NULL"),
                              {"o": organizacion_id}):
            empresas.setdefault(f[0], []).append(f[1])
        aliados = [dict(f) for f in conn.execute(text(
            "SELECT r.id, b.nombre, b.razon_social FROM org_aliados r JOIN aliados_bancarios b ON b.id = r.aliado_id "
            "WHERE r.organizacion_id = :o"), {"o": organizacion_id}).mappings()]
        reqs = {f[1]: f[0] for f in conn.execute(text(
            "SELECT id, consecutivo FROM requerimientos WHERE organizacion_id = :o"), {"o": organizacion_id})}
    if not o["carpeta_compliance"]:
        raise doc.ErrorCarpeta("Primero registre el enlace de la carpeta Compliance de la organización.")

    resumen = {"subclientes": [], "carpetas_sin_subcliente": [], "aliados": [], "aliados_sin_carpeta": [],
               "carpetas_sin_aliado": [], "requerimientos": 0, "carpetas_req_sin_coincidir": []}
    try:
        lector = lector or doc.lector_configurado(engine)
        drive, raiz, nombre = o["carpeta_drive_id"], o["carpeta_item_id"], None
        if not (drive and raiz):
            res = lector.resolver(o["carpeta_compliance"])
            drive, raiz, nombre = res["drive_id"], res["item_id"], res["nombre"]
        hijos = [h for h in lector.hijos(drive, raiz) if doc._es_carpeta(h)]

        enlaces_cli: dict[int, dict] = {}
        docs_aliados: dict[int, tuple[dict, list[dict]]] = {}
        req_encontrados: dict[int, tuple[dict, dict]] = {}

        def leer_requerimientos(carpeta: dict):
            for c, h in _carpetas_requerimientos(lector, drive, carpeta):
                if c and c in reqs:
                    req_encontrados[reqs[c]] = (h, _evidencias(lector, drive, h))
                else:
                    resumen["carpetas_req_sin_coincidir"].append(h["name"])

        for h in hijos:
            if es_carpeta_aliados(h["name"]):
                for a in (x for x in lector.hijos(drive, h["id"]) if doc._es_carpeta(x)):
                    rel = next((r for r in aliados if coincide(a["name"], r["nombre"], r["razon_social"])), None)
                    if rel is None:
                        resumen["carpetas_sin_aliado"].append(a["name"])
                        continue
                    docs_aliados[rel["id"]] = (a, doc._archivos(lector, drive, a, a["name"], 2))
            elif es_carpeta_requerimientos(h["name"]):
                leer_requerimientos(h)
            else:
                cli = next((c for c in clientes if coincide(h["name"], c["razon_social"], *empresas.get(c["id"], []))), None)
                if cli is None:
                    resumen["carpetas_sin_subcliente"].append(h["name"])
                    continue
                enlaces_cli[cli["id"]] = h
                for sub in (x for x in lector.hijos(drive, h["id"]) if doc._es_carpeta(x) and es_carpeta_requerimientos(x["name"])):
                    leer_requerimientos(sub)
    except doc.ErrorCarpeta as e:
        with engine.begin() as conn:
            conn.execute(text("UPDATE organizaciones SET carpeta_error = :e, carpeta_revisada_en = CURRENT_TIMESTAMP WHERE id = :o"),
                         {"e": str(e), "o": organizacion_id})
        raise

    por_revisar: list[int] = []
    with engine.begin() as conn:
        # Subclientes: se enlazan los que no tienen carpeta pegada a mano
        for c in clientes:
            h = enlaces_cli.get(c["id"])
            if h is not None:
                manual = c["carpeta_origen"] == "manual" and c["carpeta_onedrive"]
                if not manual:
                    conn.execute(text(
                        "UPDATE clientes SET carpeta_onedrive = :u, carpeta_drive_id = :d, carpeta_item_id = :i, carpeta_nombre = :n, "
                        "carpeta_origen = 'compliance', carpeta_error = NULL WHERE id = :c"),
                        {"u": h.get("webUrl") or o["carpeta_compliance"], "d": drive, "i": h["id"], "n": h["name"], "c": c["id"]})
                por_revisar.append(c["id"])
                resumen["subclientes"].append({"cliente_id": c["id"], "subcliente": c["razon_social"], "carpeta": h["name"],
                                               "enlace": "manual" if manual else "compliance"})
            elif c["carpeta_origen"] == "compliance":
                conn.execute(text("UPDATE clientes SET carpeta_onedrive = NULL, carpeta_drive_id = NULL, carpeta_item_id = NULL, "
                                  "carpeta_nombre = NULL, carpeta_origen = 'manual' WHERE id = :c"), {"c": c["id"]})
        # Aliados: documentos de su carpeta
        for r in aliados:
            hallado = docs_aliados.get(r["id"])
            if hallado is None:
                conn.execute(text("UPDATE org_aliados SET carpeta_item_id = NULL, carpeta_web_url = NULL, carpeta_nombre = NULL, "
                                  "carpeta_revisada_en = CURRENT_TIMESTAMP WHERE id = :r"), {"r": r["id"]})
                conn.execute(text("DELETE FROM org_aliado_documentos WHERE relacion_id = :r"), {"r": r["id"]})
                resumen["aliados_sin_carpeta"].append(r["nombre"])
                continue
            carpeta, archivos = hallado
            conn.execute(text("UPDATE org_aliados SET carpeta_item_id = :i, carpeta_web_url = :u, carpeta_nombre = :n, "
                              "carpeta_revisada_en = CURRENT_TIMESTAMP WHERE id = :r"),
                         {"i": carpeta["id"], "u": carpeta.get("webUrl"), "n": carpeta["name"], "r": r["id"]})
            for a in archivos:
                conn.execute(text(
                    "INSERT INTO org_aliado_documentos (relacion_id, codigo, item_id, nombre_archivo, ruta, web_url, tamano, modificado_en) "
                    "VALUES (:r, :c, :i, :n, :ru, :w, :t, :m) ON CONFLICT (relacion_id, item_id) DO UPDATE SET "
                    "nombre_archivo = EXCLUDED.nombre_archivo, ruta = EXCLUDED.ruta, web_url = EXCLUDED.web_url, "
                    "tamano = EXCLUDED.tamano, modificado_en = EXCLUDED.modificado_en, "
                    "codigo = CASE WHEN org_aliado_documentos.asignacion = 'manual' THEN org_aliado_documentos.codigo ELSE EXCLUDED.codigo END"),
                    {"r": r["id"], "c": reconocer_aliado(a["name"]), "i": a["id"], "n": a["name"], "ru": a["_ruta"],
                     "w": a.get("webUrl"), "t": a.get("size"), "m": doc._fecha_graph(a.get("lastModifiedDateTime"))})
            conn.execute(text("DELETE FROM org_aliado_documentos WHERE relacion_id = :r AND NOT (item_id = ANY(:v))"),
                         {"r": r["id"], "v": [a["id"] for a in archivos]})
            resumen["aliados"].append({"relacion_id": r["id"], "aliado": r["nombre"], "carpeta": carpeta["name"], "archivos": len(archivos)})
        # Requerimientos: evidencias
        for rid in reqs.values():
            hallado = req_encontrados.get(rid)
            if hallado is None:
                conn.execute(text("UPDATE requerimientos SET carpeta_item_id = NULL, carpeta_web_url = NULL, ev_solicitud = NULL, "
                                  "ev_soportes = NULL, ev_respuesta = NULL, carpeta_revisada_en = CURRENT_TIMESTAMP WHERE id = :r"), {"r": rid})
                continue
            h, ev = hallado
            conn.execute(text("UPDATE requerimientos SET carpeta_item_id = :i, carpeta_web_url = :u, ev_solicitud = :s, "
                              "ev_soportes = :so, ev_respuesta = :re, carpeta_revisada_en = CURRENT_TIMESTAMP WHERE id = :r"),
                         {"i": h["id"], "u": h.get("webUrl"), "s": ev["solicitud"], "so": ev["soportes"], "re": ev["respuesta"], "r": rid})
        resumen["requerimientos"] = len(req_encontrados)
        conn.execute(text(
            "UPDATE organizaciones SET carpeta_drive_id = :d, carpeta_item_id = :i, carpeta_nombre = COALESCE(:n, carpeta_nombre), "
            "carpeta_revisada_en = CURRENT_TIMESTAMP, carpeta_error = NULL, carpeta_resumen = CAST(:r AS JSONB) WHERE id = :o"),
            {"d": drive, "i": raiz, "n": nombre, "r": json.dumps(resumen, ensure_ascii=False), "o": organizacion_id})

    # Documentos de cada subcliente enlazado (una carpeta con problema no detiene a las demás)
    for cid in por_revisar:
        try:
            doc.revisar(engine, cid, lector, usuario)
        except Exception as e:
            logger.warning("No se pudo revisar la carpeta del subcliente %s: %s", cid, e)
    return resumen


def revisar_todas(engine: Engine, lector=None) -> None:
    """Revisa la carpeta Compliance de todas las organizaciones que la tienen. Nunca lanza excepción."""
    try:
        with engine.connect() as conn:
            ids = list(conn.scalars(text("SELECT id FROM organizaciones WHERE activa AND carpeta_compliance IS NOT NULL")))
        if not ids:
            return
        lector = lector or doc.lector_configurado(engine)
        for oid in ids:
            try:
                revisar_organizacion(engine, oid, lector)
            except Exception as e:
                logger.warning("No se pudo revisar la carpeta Compliance de la organización %s: %s", oid, e)
    except Exception as e:
        logger.warning("Revisión de carpetas Compliance omitida: %s", e)
