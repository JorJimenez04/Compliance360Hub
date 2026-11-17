"""
Sincronización del reporte de AdamoPay -> tablas tx_* de Compliance360 Hub.

Estrategia incremental por empresa (hoja del Excel o CSV de un cliente):
- Se lee el hash de contenido de las transacciones ya guardadas.
- Solo se escriben las filas nuevas o modificadas (upsert por clave natural).
- Opcionalmente se eliminan las que ya no vienen en el archivo.
- Todo ocurre en una única transacción: o se aplica completo o no se aplica.
- Si el archivo es idéntico (SHA-256) al de la última carga exitosa, no se
  procesa (salvo forzar=True).

Cada ejecución, exitosa o no, queda en tx_sincronizaciones.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import Connection, Engine, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.monitoreo_tx.config import SYNC_LOG_DIR
from core.monitoreo_tx.domain.continuidad import verificar_continuidad
from core.monitoreo_tx.etl.excel_loader import leer_archivo
from core.monitoreo_tx.repositorio import TransaccionesRepo, registrar_empresas_faltantes
from core.monitoreo_tx.tablas import tx_sincronizaciones, tx_transacciones

logger = logging.getLogger(__name__)

T = tx_transacciones.c
S = tx_sincronizaciones.c
TAMANO_LOTE = 5_000
COLUMNAS_TX = [c.name for c in tx_transacciones.columns if c.name != "id"]
COLUMNAS_ACTUALIZABLES = [c for c in COLUMNAS_TX if c not in ("cliente", "no_registro", "id_transaccion")]


@dataclass
class ResumenSincronizacion:
    resultado: str = "OK"
    archivo: str = ""
    clientes: int = 0
    filas_leidas: int = 0
    insertadas: int = 0
    actualizadas: int = 0
    sin_cambios: int = 0
    rechazadas: int = 0
    reparadas: int = 0
    eliminadas: int = 0
    empresas_nuevas: list[str] = field(default_factory=list)
    # Completitud de lo guardado por empresa tras la carga (ver domain/continuidad.py)
    verificacion: dict[str, dict] = field(default_factory=dict)
    faltantes: int = 0
    descuadres_saldo: int = 0
    duracion_s: float = 0.0
    archivo_rechazos: str | None = None
    rechazos: list[dict] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)
    mensaje: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def sha256_archivo(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _sentencia_upsert():
    stmt = pg_insert(tx_transacciones)
    return stmt.on_conflict_do_update(
        constraint="uq_tx_natural",
        set_={c: stmt.excluded[c] for c in COLUMNAS_ACTUALIZABLES},
    )


def _a_registros(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> lista de dicts con None en lugar de NaN/NaT."""
    df = df[COLUMNAS_TX].astype(object)
    df = df.where(df.notna(), None)
    return df.to_dict("records")


def _sincronizar_cliente(conn: Connection, upsert, hoja, ahora: datetime, eliminar_faltantes: bool) -> dict:
    df = hoja.df.copy()
    df["sincronizado_en"] = ahora

    existentes = {
        (no, id_tx): (pk, h)
        for pk, no, id_tx, h in conn.execute(
            select(T.id, T.no_registro, T.id_transaccion, T.row_hash).where(T.cliente == hoja.cliente)
        )
    }

    claves = list(zip(df["no_registro"], df["id_transaccion"]))
    hash_previo = pd.Series([existentes.get(k, (None, None))[1] for k in claves], index=df.index)
    nuevas = hash_previo.isna()
    cambiadas = ~nuevas & (hash_previo != df["row_hash"])
    por_escribir = df.loc[nuevas | cambiadas]

    registros = _a_registros(por_escribir)
    for i in range(0, len(registros), TAMANO_LOTE):
        conn.execute(upsert, registros[i:i + TAMANO_LOTE])

    eliminadas = 0
    if eliminar_faltantes:
        en_archivo = set(claves)
        faltantes = [pk for k, (pk, _) in existentes.items() if k not in en_archivo]
        for i in range(0, len(faltantes), TAMANO_LOTE):
            conn.execute(delete(tx_transacciones).where(T.id.in_(faltantes[i:i + TAMANO_LOTE])))
        eliminadas = len(faltantes)

    return {
        "insertadas": int(nuevas.sum()),
        "actualizadas": int(cambiadas.sum()),
        "sin_cambios": int(len(df) - nuevas.sum() - cambiadas.sum()),
        "eliminadas": eliminadas,
    }


def _exportar_rechazos(rechazos: list[dict], directorio: Path) -> str | None:
    if not rechazos:
        return None
    try:
        directorio.mkdir(parents=True, exist_ok=True)
        ruta = directorio / f"rechazos_{datetime.now():%Y%m%d_%H%M%S}.csv"
        pd.DataFrame(rechazos).to_csv(ruta, index=False, encoding="utf-8-sig")
        return str(ruta)
    except OSError:
        # En el contenedor el disco puede ser de solo lectura: los rechazos siguen en el resumen
        logger.warning("No se pudo guardar el CSV de rechazos en %s", directorio)
        return None


def _ultima_ok(engine: Engine) -> dict | None:
    with engine.connect() as conn:
        fila = conn.execute(
            select(S.id, S.archivo_sha256, S.finalizado_en)
            .where(S.resultado == "OK").order_by(S.id.desc()).limit(1)
        ).mappings().first()
    return dict(fila) if fila else None


def sincronizar(
    ruta: Path | str,
    engine: Engine | None = None,
    forzar: bool = False,
    eliminar_faltantes: bool = False,
    cliente: str | None = None,
    usuario: str | None = None,
    nombre_archivo: str | None = None,
    directorio_logs: Path | None = None,
) -> ResumenSincronizacion:
    """
    Carga el Excel maestro (una hoja por empresa) o el CSV «Historial de pagos»
    de una empresa (`cliente` = nombre con el que se registra). Lanza la
    excepción original si falla, después de registrar el error en la bitácora.
    """
    if engine is None:
        from db.database import engine as engine_bd
        engine = engine_bd

    inicio = time.perf_counter()
    iniciado_en = datetime.now()
    ruta = Path(ruta)
    resumen = ResumenSincronizacion(archivo=nombre_archivo or ruta.name)
    huella = None

    try:
        huella = sha256_archivo(ruta)
        ultima = _ultima_ok(engine)
        if not forzar and ultima and ultima["archivo_sha256"] == huella:
            resumen.resultado = "OMITIDA"
            resumen.mensaje = (
                f"El archivo no cambió desde la carga #{ultima['id']} "
                f"({ultima['finalizado_en']:%Y-%m-%d %H:%M}). Para cargarlo de nuevo, marque «Reprocesar» "
                "en la app o use --forzar en el script."
            )
            logger.info(resumen.mensaje)
        else:
            hojas = leer_archivo(ruta, cliente)
            upsert = _sentencia_upsert()
            rechazos: list[dict] = []

            with engine.begin() as conn:
                for hoja in hojas:
                    conteo = _sincronizar_cliente(conn, upsert, hoja, iniciado_en, eliminar_faltantes)
                    for k, v in conteo.items():
                        setattr(resumen, k, getattr(resumen, k) + v)
                    resumen.filas_leidas += hoja.filas_leidas
                    resumen.reparadas += hoja.reparadas
                    resumen.advertencias += [f"{hoja.cliente}: {a}" for a in hoja.advertencias]
                    rechazos += hoja.rechazos
                    logger.info("  %-35s %s", hoja.cliente, conteo)

                    # Se verifica todo lo guardado de la empresa, no solo este archivo:
                    # así se detectan huecos entre un exporte y el siguiente.
                    cont = verificar_continuidad(TransaccionesRepo(engine).datos_continuidad(hoja.cliente, conn))
                    resumen.verificacion[hoja.cliente] = cont.to_dict()
                    resumen.faltantes += cont.faltantes
                    resumen.descuadres_saldo += cont.descuadres_saldo
                    if not cont.completa:
                        resumen.advertencias.append(f"{hoja.cliente}: {cont.resumen()}")
                    logger.info("  %-35s %s", "", cont.resumen())

                if eliminar_faltantes and cliente is None:
                    # Empresas cuya hoja ya no viene en el Excel maestro
                    borrado = conn.execute(
                        delete(tx_transacciones).where(T.cliente.not_in([h.cliente for h in hojas]))
                    )
                    resumen.eliminadas += borrado.rowcount or 0

                # Cada hoja nueva obtiene una ficha para enlazarla con su cliente
                resumen.empresas_nuevas = registrar_empresas_faltantes(conn, [h.cliente for h in hojas])

            resumen.clientes = len(hojas)
            resumen.rechazadas = len(rechazos)
            resumen.rechazos = rechazos
            resumen.archivo_rechazos = _exportar_rechazos(rechazos, directorio_logs or SYNC_LOG_DIR)
            resumen.mensaje = "Carga completada"
    except BaseException as e:
        # BaseException y no Exception: una interrupción (Ctrl+C, cierre del proceso) también
        # deshace la transacción y no debe quedar registrada como carga exitosa.
        resumen.resultado = "ERROR"
        resumen.mensaje = f"{type(e).__name__}: {e}" if str(e) else f"Carga interrumpida ({type(e).__name__})"
        resumen.insertadas = resumen.actualizadas = resumen.sin_cambios = resumen.eliminadas = 0
        resumen.verificacion, resumen.faltantes, resumen.descuadres_saldo = {}, 0, 0
        logger.exception("Error sincronizando %s", ruta)
        raise
    finally:
        resumen.duracion_s = round(time.perf_counter() - inicio, 2)
        _registrar(engine, resumen, iniciado_en, huella, usuario)

    return resumen


def _registrar(engine: Engine, resumen: ResumenSincronizacion, iniciado_en: datetime,
               huella: str | None, usuario: str | None) -> None:
    detalle = {"advertencias": resumen.advertencias, "archivo_rechazos": resumen.archivo_rechazos,
               "empresas_nuevas": resumen.empresas_nuevas}
    try:
        with engine.begin() as conn:
            conn.execute(tx_sincronizaciones.insert().values(
                iniciado_en=iniciado_en,
                finalizado_en=datetime.now(),
                archivo=resumen.archivo,
                archivo_sha256=huella,
                resultado=resumen.resultado,
                usuario=usuario,
                clientes=resumen.clientes,
                filas_leidas=resumen.filas_leidas,
                insertadas=resumen.insertadas,
                actualizadas=resumen.actualizadas,
                sin_cambios=resumen.sin_cambios,
                rechazadas=resumen.rechazadas,
                reparadas=resumen.reparadas,
                eliminadas=resumen.eliminadas,
                mensaje=f"{resumen.mensaje}\n{json.dumps(detalle, ensure_ascii=False)}",
                faltantes=resumen.faltantes,
                descuadres_saldo=resumen.descuadres_saldo,
                verificacion=json.dumps(resumen.verificacion, ensure_ascii=False) if resumen.verificacion else None,
            ))
    except Exception:
        logger.exception("No se pudo registrar la carga en tx_sincronizaciones")
