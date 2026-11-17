"""
Revisión de la carpeta en la nube: descarga y carga los archivos nuevos.

- Un archivo ya procesado en la misma versión no se vuelve a descargar.
- Cada archivo se carga con la sincronización normal (etl/sync.py): mismo
  control de duplicados, rechazos, verificación de completitud y bitácora.
- El error de un archivo no detiene los demás; queda registrado.
- Dos revisiones no corren a la vez (bloqueo en PostgreSQL): si el proceso
  programado y el botón «Sincronizar ahora» coinciden, la segunda no hace nada.
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine, select, text, update

from core.monitoreo_tx.etl.sync import sincronizar
from core.monitoreo_tx.nube.fuentes import ArchivoNube
from core.monitoreo_tx.tablas import tx_archivos_nube, tx_revisiones_nube

logger = logging.getLogger(__name__)

A = tx_archivos_nube.c
R = tx_revisiones_nube.c
LLAVE_BLOQUEO = 360_0035   # pg_advisory_lock: identificador fijo de esta tarea


@dataclass
class ResultadoArchivo:
    empresa: str
    nombre: str
    resultado: str          # OK | OMITIDA | ERROR
    mensaje: str = ""
    insertadas: int = 0
    actualizadas: int = 0
    rechazadas: int = 0
    completitud: str = ""


@dataclass
class ResumenRevision:
    resultado: str = "OK"   # OK | CON_ERRORES | ERROR | EN_CURSO
    origen: str = ""
    descripcion: str = ""
    archivos_vistos: int = 0
    archivos_nuevos: int = 0
    cargados: int = 0
    errores: int = 0
    archivos: list[ResultadoArchivo] = field(default_factory=list)
    sueltos: list[str] = field(default_factory=list)
    ignorados: list[str] = field(default_factory=list)
    mensaje: str = ""
    duracion_s: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def _ya_procesado(engine: Engine, origen: str, a: ArchivoNube) -> bool:
    with engine.connect() as conn:
        return conn.execute(
            select(A.id).where(A.origen == origen, A.item_id == a.item_id, A.version == a.version,
                               A.resultado.in_(("OK", "OMITIDA")))
        ).first() is not None


def _registrar_archivo(engine: Engine, origen: str, a: ArchivoNube, res: ResultadoArchivo,
                       revision_id: int | None) -> None:
    # Un ERROR previo de la misma versión se reemplaza por el nuevo intento
    with engine.begin() as conn:
        conn.execute(tx_archivos_nube.delete().where(
            A.origen == origen, A.item_id == a.item_id, A.version == a.version))
        conn.execute(tx_archivos_nube.insert().values(
            origen=origen, item_id=a.item_id, version=a.version, empresa=a.empresa, nombre=a.nombre,
            tamano=a.tamano, modificado_en=a.modificado_en, procesado_en=datetime.now(),
            resultado=res.resultado, revision_id=revision_id, mensaje=res.mensaje[:2000],
        ))


def revisar(fuente, engine: Engine | None = None, usuario: str = "programada") -> ResumenRevision:
    """Revisa la fuente y carga los archivos nuevos o modificados."""
    if engine is None:
        from db.database import engine as engine_bd
        engine = engine_bd

    inicio = datetime.now()
    resumen = ResumenRevision(origen=fuente.origen, descripcion=fuente.descripcion())

    with engine.connect() as bloqueo:
        if not bloqueo.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LLAVE_BLOQUEO}).scalar():
            resumen.resultado = "EN_CURSO"
            resumen.mensaje = "Ya hay una revisión en curso; se omite esta."
            return resumen
        try:
            with engine.begin() as conn:
                revision_id = conn.execute(tx_revisiones_nube.insert().values(
                    origen=fuente.origen, iniciado_en=inicio, resultado="EN_CURSO", usuario=usuario,
                ).returning(R.id)).scalar_one()
            try:
                _procesar(fuente, engine, usuario, resumen, revision_id)
            except BaseException as e:
                resumen.resultado = "ERROR"
                resumen.mensaje = f"{type(e).__name__}: {e}" if str(e) else f"Revisión interrumpida ({type(e).__name__})"
                logger.exception("Revisión de %s fallida", fuente.descripcion())
                raise
            finally:
                resumen.duracion_s = round((datetime.now() - inicio).total_seconds(), 1)
                with engine.begin() as conn:
                    conn.execute(update(tx_revisiones_nube).where(R.id == revision_id).values(
                        finalizado_en=datetime.now(), resultado=resumen.resultado,
                        archivos_vistos=resumen.archivos_vistos, archivos_nuevos=resumen.archivos_nuevos,
                        cargados=resumen.cargados, errores=resumen.errores, mensaje=resumen.mensaje[:4000],
                    ))
        finally:
            bloqueo.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LLAVE_BLOQUEO})
            bloqueo.commit()
    return resumen


def _procesar(fuente, engine: Engine, usuario: str, resumen: ResumenRevision, revision_id: int) -> None:
    listado = fuente.listar()
    resumen.sueltos, resumen.ignorados = listado.sueltos, listado.ignorados
    resumen.archivos_vistos = len(listado.archivos)
    # Por empresa y nombre: con el nombre AAAA-MM-DD_… se cargan del más antiguo al más reciente
    pendientes = [a for a in sorted(listado.archivos, key=lambda a: (a.empresa.casefold(), a.nombre))
                  if not _ya_procesado(engine, fuente.origen, a)]
    resumen.archivos_nuevos = len(pendientes)

    with tempfile.TemporaryDirectory() as tmp:
        for a in pendientes:
            res = ResultadoArchivo(empresa=a.empresa, nombre=a.nombre, resultado="ERROR")
            try:
                ruta = fuente.descargar(a, Path(tmp) / f"archivo{Path(a.nombre).suffix.lower()}")
                r = sincronizar(ruta, engine=engine, cliente=a.empresa,
                                usuario=f"{usuario} ({fuente.origen})", nombre_archivo=f"{a.empresa}/{a.nombre}")
                res.resultado, res.mensaje = r.resultado, r.mensaje
                res.insertadas, res.actualizadas, res.rechazadas = r.insertadas, r.actualizadas, r.rechazadas
                v = r.verificacion.get(a.empresa)
                if v:
                    res.completitud = ("completa" if v["completa"] else
                                       f"{v['faltantes']} faltante(s), {v['descuadres_saldo']} saldo(s) descuadrado(s)")
                if r.resultado == "OK":
                    resumen.cargados += 1
            except Exception as e:   # un archivo dañado no detiene los demás
                res.mensaje = f"{type(e).__name__}: {e}"
                resumen.errores += 1
                logger.exception("No se pudo cargar %s/%s", a.empresa, a.nombre)
            _registrar_archivo(engine, fuente.origen, a, res, revision_id)
            resumen.archivos.append(res)

    resumen.resultado = "CON_ERRORES" if resumen.errores else "OK"
    partes = [f"{resumen.archivos_vistos} archivo(s) en la carpeta, {resumen.archivos_nuevos} nuevo(s), "
              f"{resumen.cargados} cargado(s)"]
    if resumen.errores:
        partes.append(f"{resumen.errores} con error")
    if resumen.sueltos:
        partes.append(f"{len(resumen.sueltos)} suelto(s) en la raíz sin empresa: {', '.join(resumen.sueltos[:5])}")
    if resumen.ignorados:
        partes.append(f"{len(resumen.ignorados)} ignorado(s) por formato")
    resumen.mensaje = "; ".join(partes)


def ultimas_revisiones(engine: Engine, limite: int = 10) -> list[dict]:
    with engine.connect() as conn:
        return [dict(f) for f in conn.execute(
            select(tx_revisiones_nube).order_by(R.id.desc()).limit(limite)).mappings()]


def ultimos_archivos(engine: Engine, limite: int = 30) -> list[dict]:
    with engine.connect() as conn:
        return [dict(f) for f in conn.execute(
            select(tx_archivos_nube).order_by(A.procesado_en.desc(), A.id.desc()).limit(limite)).mappings()]
