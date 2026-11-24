"""
Documentación del cliente y de sus beneficiarios, leída de la carpeta del cliente en OneDrive.

Estructura esperada dentro de la carpeta del cliente (decisión de Jorge, 2026-11-23):

    {Cliente}/
      Documentación corporativa/        documentos propios del cliente
      Beneficiarios/
        {documento} - {nombre}/         documentos básicos de cada beneficiario

Los nombres de los archivos son libres: cada uno se reconoce por palabras de su nombre
(«existencia», «accionaria», «contrato», «RUT», «cédula»…). Lo que no se reconoce se
asigna a mano. Basta con que el archivo exista para dar el documento por cargado.

La lectura es de solo lectura, con la misma conexión de OneDrive de la carga automática.
"""

from __future__ import annotations

import base64
import logging
import re
import threading
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlparse

from sqlalchemy import Engine, text

logger = logging.getLogger(__name__)

# ---------- Documentos ----------
DOCUMENTOS = {
    "certificado_existencia": "Certificado de existencia y representación legal",
    "composicion_accionaria": "Composición accionaria",
    "contrato": "Contrato",
    "rut": "RUT",
    "cedula_rl": "Cédula del representante legal",
    "documento_identidad": "Documento de identidad",
    "certificacion_bancaria": "Certificación bancaria",
}


@dataclass(frozen=True)
class Requisito:
    codigo: str
    nombre: str
    acepta: tuple[str, ...]          # documentos que lo cumplen


def _r(codigo: str, *acepta: str, nombre: str | None = None) -> Requisito:
    return Requisito(codigo, nombre or DOCUMENTOS[codigo], acepta or (codigo,))


PROPIOS = {
    "juridica": (_r("certificado_existencia"), _r("composicion_accionaria"), _r("contrato"), _r("rut"), _r("cedula_rl")),
    "natural": (_r("documento_identidad"), _r("rut"), _r("contrato")),
}
BENEFICIARIO = {
    "natural": (_r("documento_identidad"), _r("certificacion_bancaria")),
    "juridica": (_r("existencia_o_rut", "certificado_existencia", "rut",
                    nombre="Certificado de existencia o RUT"), _r("certificacion_bancaria")),
}


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def _palabras(nombre: str) -> set[str]:
    base = _norm(nombre).rsplit(".", 1)[0]
    return set(re.findall(r"[a-z]+|\d+", base))


def reconocer(nombre_archivo: str, de_beneficiario: bool = False) -> str | None:
    """Qué documento es un archivo, por las palabras de su nombre. None si no se reconoce."""
    p = _palabras(nombre_archivo)
    identidad = bool(p & {"cedula", "cc", "identidad", "pasaporte", "ce", "ti", "dni", "documento"})
    if not de_beneficiario and identidad and p & {"representante", "rl", "legal", "rep"}:
        return "cedula_rl"
    if p & {"existencia", "camara", "ccio", "cccomercio"} or "certificado de existencia" in _norm(nombre_archivo):
        return "certificado_existencia"
    if p & {"accionaria", "accionistas", "accionista", "socios", "composicion"} or "beneficiario final" in _norm(nombre_archivo):
        return "composicion_accionaria"
    if "contrato" in p:
        return "contrato"
    if "rut" in p:
        return "rut"
    if p & {"bancaria", "bancario", "banco", "cuenta"}:
        return "certificacion_bancaria"
    if identidad:
        return "documento_identidad"
    return None


def tipo_persona_beneficiario(tipo_identificacion: str | None, tipo_persona: str | None) -> str:
    ti, tp = _norm(tipo_identificacion or "").strip(), _norm(tipo_persona or "").strip()
    return "juridica" if ti in ("n", "nit") or tp.startswith("jur") else "natural"


def nombre_carpeta_beneficiario(id_beneficiario: str, nombre: str | None) -> str:
    limpio = re.sub(r'[\\/:*?"<>|]+', " ", (nombre or "").strip())
    return f"{id_beneficiario} - {re.sub(r'\s+', ' ', limpio).strip()}".strip(" -")


# ---------- Lectura de OneDrive ----------
class ErrorCarpeta(RuntimeError):
    pass


def validar_enlace(url: str | None) -> str | None:
    if not url or not url.strip():
        return None
    u = urlparse(url.strip())
    if u.scheme != "https" or not (u.hostname or "").endswith(("sharepoint.com", "1drv.ms", "onedrive.live.com")):
        raise ErrorCarpeta("Pegue el enlace de la carpeta del cliente en OneDrive o SharePoint (https://…sharepoint.com/…).")
    return url.strip()


class LectorGraph:
    """Lee carpetas con la conexión de OneDrive de la carga automática (Microsoft Graph, solo lectura)."""
    GRAPH = "https://graph.microsoft.com/v1.0"

    def __init__(self, fuente):
        self.f = fuente

    def _get(self, url: str) -> dict:
        r = self.f.http.get(url, headers=self.f._cabeceras(), timeout=self.f.timeout)
        if r.status_code == 404:
            raise ErrorCarpeta("No se encontró la carpeta: revise el enlace o que siga existiendo.")
        if r.status_code in (401, 403):
            raise ErrorCarpeta("La cuenta conectada a OneDrive no tiene acceso a esa carpeta.")
        if r.status_code != 200:
            raise ErrorCarpeta(f"Error de Microsoft Graph ({r.status_code}).")
        return r.json()

    def resolver(self, enlace: str) -> dict:
        token = "u!" + base64.urlsafe_b64encode(enlace.encode()).decode().rstrip("=")
        d = self._get(f"{self.GRAPH}/shares/{token}/driveItem?$select=id,name,folder,webUrl,parentReference")
        if "folder" not in d:
            raise ErrorCarpeta("El enlace no es de una carpeta.")
        return {"drive_id": d["parentReference"]["driveId"], "item_id": d["id"], "nombre": d.get("name")}

    def hijos(self, drive_id: str, item_id: str) -> list[dict]:
        url = (f"{self.GRAPH}/drives/{drive_id}/items/{item_id}/children"
               "?$select=id,name,folder,file,size,webUrl,lastModifiedDateTime&$top=200")
        elementos = []
        while url:
            d = self._get(url)
            elementos += d.get("value", [])
            url = d.get("@odata.nextLink")
        return elementos


def lector_configurado(engine: Engine):
    from core.monitoreo_tx.nube.fuentes import ErrorFuente, fuente_configurada
    try:
        fuente = fuente_configurada(engine)
    except ErrorFuente as e:
        raise ErrorCarpeta(str(e)) from e
    if fuente is None:
        raise ErrorCarpeta("OneDrive no está conectado. Conéctelo en Monitoreo → Cargas.")
    return LectorGraph(fuente)


def _es_carpeta(i: dict) -> bool:
    return "folder" in i


def _archivos(lector, drive: str, carpeta: dict, ruta: str, profundidad: int = 2) -> list[dict]:
    """Archivos de una carpeta y sus subcarpetas (hasta `profundidad` niveles)."""
    salida = []
    for i in lector.hijos(drive, carpeta["id"]):
        if _es_carpeta(i):
            if profundidad > 0:
                salida += _archivos(lector, drive, i, f"{ruta}/{i['name']}", profundidad - 1)
        else:
            salida.append({**i, "_ruta": f"{ruta}/{i['name']}"})
    return salida


def _fecha_graph(v):
    from core.monitoreo_tx.nube.fuentes import _fecha
    return _fecha(v)


def revisar(engine: Engine, cliente_id: int, lector=None, usuario: str = "sistema") -> dict:
    """Lee la carpeta del cliente y actualiza su registro de documentos y de beneficiarios con carpeta."""
    with engine.connect() as conn:
        c = conn.execute(text("SELECT carpeta_onedrive, carpeta_drive_id, carpeta_item_id FROM clientes WHERE id = :c"),
                         {"c": cliente_id}).mappings().first()
    if c is None:
        raise LookupError("El cliente no existe.")
    if not c["carpeta_onedrive"]:
        raise ErrorCarpeta("Primero registre el enlace de la carpeta del cliente en OneDrive.")
    try:
        lector = lector or lector_configurado(engine)
        drive, raiz_id, nombre = c["carpeta_drive_id"], c["carpeta_item_id"], None
        if not (drive and raiz_id):
            res = lector.resolver(c["carpeta_onedrive"])
            drive, raiz_id, nombre = res["drive_id"], res["item_id"], res["nombre"]
        hijos = lector.hijos(drive, raiz_id)
        propios, benef_carpetas = [], {}
        for i in hijos:
            n = _norm(i.get("name", ""))
            if _es_carpeta(i) and n.startswith("beneficiario"):
                for b in lector.hijos(drive, i["id"]):
                    if not _es_carpeta(b):
                        continue
                    m = re.match(r"\s*([\d.\-]+?)\s*(?:-|–|$)", b["name"])
                    idb = re.sub(r"[.\-\s]", "", m.group(1)) if m else None
                    if idb:
                        benef_carpetas[idb] = (b, _archivos(lector, drive, b, f"{i['name']}/{b['name']}", 1))
            elif _es_carpeta(i):
                propios += _archivos(lector, drive, i, i["name"])
            else:
                propios.append({**i, "_ruta": i["name"]})
    except ErrorCarpeta as e:
        with engine.begin() as conn:
            conn.execute(text("UPDATE clientes SET carpeta_error = :e, carpeta_revisada_en = CURRENT_TIMESTAMP "
                              "WHERE id = :c"), {"e": str(e), "c": cliente_id})
        raise

    encontrados = [(None, a) for a in propios] + [(idb, a) for idb, (_, archivos) in benef_carpetas.items() for a in archivos]
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE clientes SET carpeta_drive_id = :d, carpeta_item_id = :i, carpeta_nombre = COALESCE(:n, carpeta_nombre), "
            "carpeta_revisada_en = CURRENT_TIMESTAMP, carpeta_error = NULL WHERE id = :c"),
            {"d": drive, "i": raiz_id, "n": nombre, "c": cliente_id})
        for idb, a in encontrados:
            conn.execute(text(
                "INSERT INTO cmp_documentos (cliente_id, id_beneficiario, codigo, item_id, nombre_archivo, ruta, web_url, "
                "  tamano, modificado_en) VALUES (:c, :b, :cod, :item, :n, :r, :w, :t, :m) "
                "ON CONFLICT (cliente_id, item_id) DO UPDATE SET id_beneficiario = EXCLUDED.id_beneficiario, "
                "  nombre_archivo = EXCLUDED.nombre_archivo, ruta = EXCLUDED.ruta, web_url = EXCLUDED.web_url, "
                "  tamano = EXCLUDED.tamano, modificado_en = EXCLUDED.modificado_en, "
                "  codigo = CASE WHEN cmp_documentos.asignacion = 'manual' THEN cmp_documentos.codigo ELSE EXCLUDED.codigo END"),
                {"c": cliente_id, "b": idb, "cod": reconocer(a["name"], idb is not None), "item": a["id"], "n": a["name"],
                 "r": a["_ruta"], "w": a.get("webUrl"), "t": a.get("size"), "m": _fecha_graph(a.get("lastModifiedDateTime"))})
        vigentes = [a["id"] for _, a in encontrados]
        borrados = conn.execute(text("DELETE FROM cmp_documentos WHERE cliente_id = :c AND NOT (item_id = ANY(:v))"),
                                {"c": cliente_id, "v": vigentes}).rowcount
        # Una carpeta de beneficiario abre (o enlaza) su expediente
        for idb, (carpeta, _) in benef_carpetas.items():
            conn.execute(text(
                "INSERT INTO cmp_beneficiarios_expediente (cliente_id, id_beneficiario, origen, abierto_por, "
                "  carpeta_item_id, carpeta_nombre) VALUES (:c, :b, 'carpeta', :u, :i, :n) "
                "ON CONFLICT (cliente_id, id_beneficiario) DO UPDATE SET carpeta_item_id = EXCLUDED.carpeta_item_id, "
                "  carpeta_nombre = EXCLUDED.carpeta_nombre"),
                {"c": cliente_id, "b": idb, "u": usuario, "i": carpeta["id"], "n": carpeta["name"]})
        conn.execute(text(
            "UPDATE cmp_beneficiarios_expediente SET carpeta_item_id = NULL, carpeta_nombre = NULL "
            "WHERE cliente_id = :c AND NOT (id_beneficiario = ANY(:b))"), {"c": cliente_id, "b": list(benef_carpetas)})
    return {"archivos_propios": len(propios), "carpetas_beneficiarios": len(benef_carpetas),
            "archivos_beneficiarios": sum(len(a) for _, a in benef_carpetas.values()), "retirados": borrados}


def revisar_todos(engine: Engine) -> None:
    """Revisa las carpetas de todos los clientes que tienen enlace. Nunca lanza excepción."""
    try:
        with engine.connect() as conn:
            ids = list(conn.scalars(text("SELECT id FROM clientes WHERE carpeta_onedrive IS NOT NULL")))
        if not ids:
            return
        lector = lector_configurado(engine)
        for cid in ids:
            try:
                revisar(engine, cid, lector)
            except Exception as e:               # una carpeta con problema no detiene a las demás
                logger.warning("No se pudo revisar la carpeta del cliente %s: %s", cid, e)
    except Exception as e:
        logger.warning("Revisión de carpetas de clientes omitida: %s", e)


def revisar_todos_en_segundo_plano(engine: Engine) -> None:
    threading.Thread(target=revisar_todos, args=(engine,), daemon=True, name="revision-carpetas").start()


# ---------- Estado ----------
def _archivos_bd(conn, cliente_id: int) -> list[dict]:
    return [dict(f) for f in conn.execute(text(
        "SELECT id, id_beneficiario, codigo, nombre_archivo, ruta, web_url, tamano, modificado_en, asignacion, "
        "asignado_por FROM cmp_documentos WHERE cliente_id = :c ORDER BY ruta"), {"c": cliente_id}).mappings()]


def _checklist(requisitos: tuple[Requisito, ...], archivos: list[dict]) -> tuple[list[dict], bool]:
    filas = []
    for r in requisitos:
        suyos = [a for a in archivos if a["codigo"] in r.acepta]
        filas.append({"codigo": r.codigo, "nombre": r.nombre, "cargado": bool(suyos), "archivos": suyos})
    return filas, all(f["cargado"] for f in filas)


def estado_propio(engine: Engine, cliente_id: int) -> dict:
    with engine.connect() as conn:
        c = conn.execute(text("SELECT tipo_persona, carpeta_onedrive, carpeta_nombre, carpeta_revisada_en, carpeta_error "
                              "FROM clientes WHERE id = :c"), {"c": cliente_id}).mappings().first()
        if c is None:
            raise LookupError("El cliente no existe.")
        archivos = [a for a in _archivos_bd(conn, cliente_id) if a["id_beneficiario"] is None]
    requisitos = PROPIOS.get(c["tipo_persona"], PROPIOS["juridica"])
    filas, completo = _checklist(requisitos, archivos)
    return {"carpeta": {"enlace": c["carpeta_onedrive"], "nombre": c["carpeta_nombre"],
                        "revisada_en": c["carpeta_revisada_en"], "error": c["carpeta_error"]},
            "requisitos": filas, "listo_para_banco": completo and bool(c["carpeta_onedrive"]),
            "faltan": [f["nombre"] for f in filas if not f["cargado"]],
            "otros_archivos": [a for a in archivos if a["codigo"] not in {x for r in requisitos for x in r.acepta}],
            "documentos": DOCUMENTOS}


def _abrir_top10(engine: Engine, cliente_id: int, lista: list[dict]) -> None:
    with engine.begin() as conn:
        for b in lista[:10]:
            conn.execute(text(
                "INSERT INTO cmp_beneficiarios_expediente (cliente_id, id_beneficiario, nombre, tipo_persona, origen) "
                "VALUES (:c, :b, :n, :t, 'top10') ON CONFLICT (cliente_id, id_beneficiario) DO NOTHING"),
                {"c": cliente_id, "b": b["id_beneficiario"], "n": b["nombre"],
                 "t": tipo_persona_beneficiario(b["tipo_identificacion"], b["tipo_persona"])})


def expedientes_beneficiarios(engine: Engine, cliente_id: int) -> dict:
    """Beneficiarios con expediente (top 10 por monto, manuales y con carpeta) y su documentación."""
    from core.cumplimiento import beneficiarios as bf
    lista = bf.listar(engine, cliente_id)["beneficiarios"]
    _abrir_top10(engine, cliente_id, lista)
    por_id = {b["id_beneficiario"]: (i + 1, b) for i, b in enumerate(lista)}
    with engine.connect() as conn:
        exp = conn.execute(text(
            "SELECT id_beneficiario, nombre, tipo_persona, origen, abierto_por, abierto_en, carpeta_nombre "
            "FROM cmp_beneficiarios_expediente WHERE cliente_id = :c AND activo ORDER BY abierto_en, id"),
            {"c": cliente_id}).mappings().all()
        archivos = [a for a in _archivos_bd(conn, cliente_id) if a["id_beneficiario"]]
        carpeta = conn.scalar(text("SELECT carpeta_onedrive IS NOT NULL FROM clientes WHERE id = :c"), {"c": cliente_id})
    filas = []
    for e in exp:
        pos, b = por_id.get(e["id_beneficiario"], (None, None))
        nombre = e["nombre"] or (b or {}).get("nombre")
        tipo = tipo_persona_beneficiario(b["tipo_identificacion"], b["tipo_persona"]) if b else e["tipo_persona"]
        suyos = [a for a in archivos if a["id_beneficiario"] == e["id_beneficiario"]]
        reqs, completo = _checklist(BENEFICIARIO[tipo], suyos)
        conocidos = {x for r in BENEFICIARIO[tipo] for x in r.acepta}
        filas.append({**dict(e), "nombre": nombre, "tipo_persona": tipo, "posicion": pos,
                      "monto": b["monto"] if b else 0.0, "participacion": b["participacion"] if b else 0.0,
                      "senales": b["senales"] if b else [],
                      "carpeta_sugerida": nombre_carpeta_beneficiario(e["id_beneficiario"], nombre),
                      "requisitos": reqs, "completo": completo,
                      "otros_archivos": [a for a in suyos if a["codigo"] not in conocidos]})
    filas.sort(key=lambda f: (f["posicion"] is None, f["posicion"] or 0))
    return {"con_carpeta_cliente": bool(carpeta), "expedientes": filas,
            "completos": sum(1 for f in filas if f["completo"]), "documentos": DOCUMENTOS}


def abrir_expediente(engine: Engine, cliente_id: int, id_beneficiario: str, usuario: str) -> None:
    from core.cumplimiento import beneficiarios as bf
    b = next((x for x in bf.listar(engine, cliente_id)["beneficiarios"] if x["id_beneficiario"] == id_beneficiario), None)
    if b is None:
        raise ErrorCarpeta("Ese beneficiario no aparece en las transacciones del cliente.")
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO cmp_beneficiarios_expediente (cliente_id, id_beneficiario, nombre, tipo_persona, origen, abierto_por) "
            "VALUES (:c, :b, :n, :t, 'manual', :u) "
            "ON CONFLICT (cliente_id, id_beneficiario) DO UPDATE SET activo = TRUE"),
            {"c": cliente_id, "b": id_beneficiario, "n": b["nombre"], "u": usuario,
             "t": tipo_persona_beneficiario(b["tipo_identificacion"], b["tipo_persona"])})


def cerrar_expediente(engine: Engine, cliente_id: int, id_beneficiario: str) -> bool:
    with engine.begin() as conn:
        return bool(conn.execute(text(
            "UPDATE cmp_beneficiarios_expediente SET activo = FALSE WHERE cliente_id = :c AND id_beneficiario = :b"),
            {"c": cliente_id, "b": id_beneficiario}).rowcount)


def asignar(engine: Engine, documento_id: int, codigo: str | None, usuario: str) -> dict:
    if codigo is not None and codigo not in DOCUMENTOS:
        raise ErrorCarpeta("Tipo de documento no válido.")
    with engine.begin() as conn:
        f = conn.execute(text(
            "UPDATE cmp_documentos SET codigo = :cod, asignacion = 'manual', asignado_por = :u WHERE id = :id "
            "RETURNING cliente_id, nombre_archivo"), {"cod": codigo, "u": usuario, "id": documento_id}).mappings().first()
    if f is None:
        raise LookupError("El documento no existe.")
    return dict(f)
