"""
Reportes UIAF cargados en PDF (migración 047).

El oficial carga los reportes que presenta por SIREL (ROS, AROS u otros) para que el
director de cumplimiento los vea en el tablero. El PDF se guarda en la base (queda en los
respaldos). Reserva legal del ROS: solo el equipo interno los consulta.
"""

from __future__ import annotations

import hashlib
from datetime import date

from sqlalchemy import Engine, text

TIPOS = {"ROS": "ROS — Reporte de operación sospechosa", "AROS": "AROS — Ausencia de reporte de operación sospechosa",
         "otro": "Otro reporte a la UIAF"}
MAX_BYTES = 15 * 1024 * 1024


class ErrorReporte(ValueError):
    pass


def _texto(v):
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


def guardar(engine: Engine, organizacion_id: int, datos: dict, nombre_archivo: str, contenido: bytes, usuario: str) -> int:
    tipo = datos.get("tipo")
    if tipo not in TIPOS:
        raise ErrorReporte("Tipo de reporte no válido.")
    if not contenido or not contenido.startswith(b"%PDF-"):
        raise ErrorReporte("El archivo debe ser un PDF.")
    if len(contenido) > MAX_BYTES:
        raise ErrorReporte("El PDF supera 15 MB.")
    presentado = datos.get("fecha_presentacion")
    if not presentado:
        raise ErrorReporte("Indique la fecha en que se presentó.")
    if presentado > date.today():
        raise ErrorReporte("La fecha de presentación no puede ser futura.")
    desde, hasta = datos.get("periodo_desde"), datos.get("periodo_hasta")
    if desde and hasta and hasta < desde:
        raise ErrorReporte("El periodo reportado está al revés.")
    if tipo == "AROS" and not (desde and hasta):
        raise ErrorReporte("Indique el periodo que cubre el AROS.")
    nombre = (_texto(nombre_archivo) or "reporte.pdf").replace("\\", "/").split("/")[-1][:200]
    sha = hashlib.sha256(contenido).hexdigest()
    with engine.begin() as conn:
        cliente = datos.get("cliente_id")
        if cliente and not conn.scalar(text("SELECT 1 FROM clientes WHERE id = :c AND organizacion_id = :o"),
                                       {"c": cliente, "o": organizacion_id}):
            raise ErrorReporte("El subcliente no pertenece a esta organización.")
        if conn.scalar(text("SELECT 1 FROM reportes_uiaf WHERE organizacion_id = :o AND archivo_sha256 = :s"),
                       {"o": organizacion_id, "s": sha}):
            raise ErrorReporte("Ese mismo PDF ya está cargado.")
        return conn.scalar(text(
            "INSERT INTO reportes_uiaf (organizacion_id, tipo, periodo_desde, periodo_hasta, fecha_presentacion, radicado, "
            "cliente_id, descripcion, archivo_nombre, archivo_bytes, archivo_sha256, archivo, creado_por) "
            "VALUES (:o, :t, :pd, :ph, :fp, :r, :c, :d, :n, :b, :s, :a, :u) RETURNING id"),
            {"o": organizacion_id, "t": tipo, "pd": desde, "ph": hasta, "fp": presentado,
             "r": _texto(datos.get("radicado")), "c": cliente, "d": _texto(datos.get("descripcion")),
             "n": nombre, "b": len(contenido), "s": sha, "a": contenido, "u": usuario})


def listar(engine: Engine, organizacion_id: int) -> list[dict]:
    with engine.connect() as conn:
        return [dict(f._mapping) for f in conn.execute(text(
            "SELECT r.id, r.tipo, r.periodo_desde, r.periodo_hasta, r.fecha_presentacion, r.radicado, r.cliente_id, "
            "c.razon_social AS subcliente, r.descripcion, r.archivo_nombre, r.archivo_bytes, r.creado_por, r.creado_en "
            "FROM reportes_uiaf r LEFT JOIN clientes c ON c.id = r.cliente_id "
            "WHERE r.organizacion_id = :o ORDER BY r.fecha_presentacion DESC, r.id DESC"), {"o": organizacion_id})]


def archivo(engine: Engine, reporte_id: int) -> dict:
    with engine.connect() as conn:
        f = conn.execute(text("SELECT r.organizacion_id, r.tipo, r.radicado, r.archivo_nombre, r.archivo "
                              "FROM reportes_uiaf r WHERE r.id = :i"), {"i": reporte_id}).mappings().first()
    if f is None:
        raise LookupError("El reporte no existe.")
    return {**dict(f), "archivo": bytes(f["archivo"])}


def eliminar(engine: Engine, organizacion_id: int, reporte_id: int) -> dict:
    with engine.begin() as conn:
        f = conn.execute(text("DELETE FROM reportes_uiaf WHERE id = :i AND organizacion_id = :o "
                              "RETURNING tipo, radicado, archivo_nombre, fecha_presentacion"),
                         {"i": reporte_id, "o": organizacion_id}).mappings().first()
    if f is None:
        raise LookupError("El reporte no existe en esta organización.")
    return dict(f)
