"""
Monitoreo Transaccional: endpoints para el nuevo frontend.

Toda la lógica vive en app/monitoreo_tx/servicio.py (la misma que usa la
interfaz Streamlit): aquí solo se traducen peticiones y respuestas, y los
permisos se vuelven a validar en el servicio.
"""

from __future__ import annotations

import json
import logging
import tempfile
import threading
import time
from datetime import date
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel

from api import seguridad as seg
from app.monitoreo_tx.config import ROLES_CARGA, ROLES_MONITOREO
from app.monitoreo_tx.domain import metricas
from app.monitoreo_tx.domain.entidades import FiltrosTransacciones
from app.monitoreo_tx.domain.errores import ErrorDominio, NoEncontrado, PermisoDenegado
from app.monitoreo_tx.servicio import registrar_auditoria, servicio
from app.monitoreo_tx.ui.formato import enmascarar

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/monitoreo", tags=["monitoreo transaccional"])

ver = seg.requiere_roles(ROLES_MONITOREO)
cargar = seg.requiere_roles(ROLES_CARGA)
TAMANO_MAX_CARGA = 25 * 1024 * 1024   # 25 MB por archivo en la carga manual


# =========================
# Utilidades
# =========================
def _registros(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> lista JSON (fechas ISO, NaN -> null, tipos numpy -> Python)."""
    if df is None or df.empty:
        return []
    return json.loads(df.to_json(orient="records", date_format="iso", force_ascii=False))


def _kpis(k: metricas.KPIs | None) -> dict | None:
    if k is None:
        return None
    return {**k.__dict__, "tasa_devolucion": k.tasa_devolucion}


def _error(e: Exception):
    if isinstance(e, PermisoDenegado):
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    if isinstance(e, NoEncontrado):
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    if isinstance(e, ErrorDominio):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    raise e


def _filtros(desde: date | None, hasta: date | None, estados: list[str] | None, texto: str) -> FiltrosTransacciones:
    return FiltrosTransacciones(desde=desde, hasta=hasta,
                                estados=tuple(estados) if estados is not None else None,
                                texto=(texto or "").strip()[:120])


def _empresa_json(e, conteo: dict[str, int] | None = None) -> dict:
    return {"id": e.id, "nombre_reporte": e.nombre_reporte, "nombre": e.nombre_visible, "activa": e.activa,
            "enlazada": e.enlazada, "cliente_id": e.cliente_id, "razon_social": e.razon_social,
            "nit": e.nit, "nivel_riesgo": e.nivel_riesgo,
            "transacciones": (conteo or {}).get(e.nombre_reporte)}


# =========================
# Empresas y estado general
# =========================
@router.get("/resumen")
def resumen(u: seg.Usuario = Depends(ver)) -> dict:
    srv, user = servicio(), u.como_dict()
    try:
        empresas = srv.empresas(user, solo_activas=True)
        conteo = srv.conteo_por_empresa(user)
    except Exception as e:
        _error(e)
    ultima = srv.ultima_carga()
    return {
        "ultima_carga": ultima["finalizado_en"].isoformat() if ultima and ultima.get("finalizado_en") else None,
        "empresas": [_empresa_json(e, conteo) for e in empresas],
        "puede_cargar": u.rol in ROLES_CARGA,
    }


@router.get("/empresas/{empresa_id}/opciones")
def opciones(empresa_id: int, u: seg.Usuario = Depends(ver)) -> dict:
    srv, user = servicio(), u.como_dict()
    try:
        o = srv.opciones_filtro(user, empresa_id)
        cont = srv.continuidad(user, empresa_id) if o.tiene_datos else None
    except Exception as e:
        _error(e)
    return {
        "fecha_min": o.fecha_min.isoformat() if o.fecha_min else None,
        "fecha_max": o.fecha_max.isoformat() if o.fecha_max else None,
        "estados": list(o.estados),
        "continuidad": ({**cont.to_dict(), "resumen": cont.resumen()} if cont else None),
    }


@router.get("/empresas/{empresa_id}/tablero")
def tablero(
    empresa_id: int,
    desde: date | None = None,
    hasta: date | None = None,
    estados: list[str] | None = Query(None),
    texto: str = "",
    granularidad: str | None = Query(None, pattern="^(Diaria|Semanal|Mensual)$"),
    u: seg.Usuario = Depends(ver),
) -> dict:
    """Todo lo que necesita el tablero en una sola respuesta (indicadores y gráficos)."""
    srv, user = servicio(), u.como_dict()
    f = _filtros(desde, hasta, estados, texto)
    try:
        df = srv.transacciones_filtradas(user, empresa_id, f)
        anterior = srv.kpis_periodo_anterior(user, empresa_id, f)
    except Exception as e:
        _error(e)
    if df.empty:
        return {"vacio": True}
    k = metricas.calcular_kpis(df)
    gran = granularidad or (metricas.granularidad_sugerida(desde, hasta) if desde and hasta else "Mensual")
    exitosos = metricas.pagos_exitosos(df)
    beneficiarios = int(exitosos["id_beneficiario"].nunique())
    actividad = metricas.actividad_semana_hora(df)
    pico = metricas.dia_pico(df)
    devol = metricas.devoluciones(df).head(20)
    return {
        "vacio": False,
        "kpis": _kpis(k),
        "kpis_anterior": _kpis(anterior),
        "beneficiarios": beneficiarios,
        "dia_pico": {"fecha": pico[0].isoformat(), "monto": pico[1]} if pico else None,
        "granularidad": gran,
        "serie": _registros(metricas.serie_pagos(df, gran)),
        "composicion": _registros(metricas.composicion_movimientos(df)),
        "rangos": _registros(metricas.distribucion_montos(df)),
        "bancos": _registros(metricas.top_bancos(df)),
        "ranking_monto": _registros(metricas.top_beneficiarios(df, n=50, por="monto").assign(
            id_beneficiario=lambda d: d["id_beneficiario"].map(enmascarar))),
        "ranking_pagos": _registros(metricas.top_beneficiarios(df, n=50, por="pagos").assign(
            id_beneficiario=lambda d: d["id_beneficiario"].map(enmascarar))),
        "actividad": {"dias": [str(i) for i in actividad.index], "horas": [int(c) for c in actividad.columns],
                      "valores": actividad.astype(int).values.tolist()},
        "motivos_devolucion": _registros(metricas.motivos_devolucion(df)),
        "devoluciones_recientes": _registros(devol.assign(
            motivo=devol["descripcion"].map(metricas.motivo_devolucion),
            id_beneficiario=devol["id_beneficiario"].map(enmascarar),
            numero_cuenta=devol["numero_cuenta"].map(enmascarar),
        )[["fecha_hora", "beneficiario", "id_beneficiario", "banco", "numero_cuenta", "monto", "motivo"]]),
    }


@router.get("/empresas/{empresa_id}/transacciones")
def transacciones(
    empresa_id: int,
    desde: date | None = None,
    hasta: date | None = None,
    estados: list[str] | None = Query(None),
    texto: str = "",
    pagina: int = Query(1, ge=1),
    tamano: int = Query(50, ge=10, le=200),
    u: seg.Usuario = Depends(ver),
) -> dict:
    """Detalle paginado. Cuentas y documentos van enmascarados; completos solo en el CSV (auditado)."""
    srv, user = servicio(), u.como_dict()
    try:
        df = srv.transacciones_filtradas(user, empresa_id, _filtros(desde, hasta, estados, texto))
    except Exception as e:
        _error(e)
    total = len(df)
    tramo = df.iloc[(pagina - 1) * tamano: pagina * tamano].copy()
    if not tramo.empty:
        tramo["movimiento"] = metricas.movimientos(tramo["tipo_transaccion"])
        tramo["motivo_devolucion"] = [
            metricas.motivo_devolucion(d) if m == metricas.DEVOLUCION else None
            for d, m in zip(tramo["descripcion"], tramo["movimiento"])]
        tramo["id_beneficiario"] = tramo["id_beneficiario"].map(enmascarar)
        tramo["numero_cuenta"] = tramo["numero_cuenta"].map(enmascarar)
    columnas = ["fecha_hora", "id_transaccion", "referencia_externa", "tipo_transaccion", "movimiento",
                "beneficiario", "tipo_identificacion", "id_beneficiario", "banco", "tipo_cuenta",
                "numero_cuenta", "monto", "comision", "saldo", "estado", "exitosa", "descripcion",
                "motivo_devolucion"]
    return {"total": total, "pagina": pagina, "tamano": tamano,
            "filas": _registros(tramo[[c for c in columnas if c in tramo.columns]])}


@router.get("/empresas/{empresa_id}/transacciones.csv")
def transacciones_csv(
    empresa_id: int,
    desde: date | None = None,
    hasta: date | None = None,
    estados: list[str] | None = Query(None),
    texto: str = "",
    u: seg.Usuario = Depends(ver),
) -> Response:
    srv, user = servicio(), u.como_dict()
    f = _filtros(desde, hasta, estados, texto)
    try:
        empresa = srv.empresas_repo.obtener(empresa_id)
        contenido = srv.csv_transacciones(user, empresa_id, f)
    except Exception as e:
        _error(e)
    nombre = f"monitoreo_tx_{empresa_id}_{desde or 'inicio'}_{hasta or 'fin'}.csv"
    registrar_auditoria(user, "EXPORT", f"Monitoreo TX: CSV de {empresa.nombre_reporte if empresa else empresa_id} "
                                        f"· {desde or 'inicio'} a {hasta or 'fin'} (nueva interfaz)")
    return Response(contenido, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/empresas/{empresa_id}/riesgo")
def riesgo(
    empresa_id: int,
    desde: date | None = None,
    hasta: date | None = None,
    estados: list[str] | None = Query(None),
    texto: str = "",
    u: seg.Usuario = Depends(ver),
) -> dict:
    try:
        analisis = servicio().evaluar_riesgo(u.como_dict(), empresa_id, _filtros(desde, hasta, estados, texto))
    except ErrorDominio as e:
        _error(e)
    except Exception:
        logger.exception("Error en el análisis de riesgo de la empresa %s", empresa_id)
        raise HTTPException(500, "No se pudo calcular el análisis de riesgo.")
    return json.loads(json.dumps(analisis, default=str))


# =========================
# Empresas (administración del enlace con clientes)
# =========================
@router.get("/empresas")
def empresas(u: seg.Usuario = Depends(cargar)) -> dict:
    srv, user = servicio(), u.como_dict()
    conteo = srv.conteo_por_empresa(user)
    return {"empresas": [_empresa_json(e, conteo) for e in srv.empresas(user, solo_activas=False)],
            "clientes": [{"id": c["id"], "razon_social": c["razon_social"], "nit": c["nit"],
                          "nivel_riesgo": c["nivel_riesgo"]} for c in srv.clientes_disponibles(user)]}


class CambioEmpresa(BaseModel):
    cliente_id: int | None = None
    quitar_enlace: bool = False
    activa: bool | None = None


@router.patch("/empresas/{empresa_id}")
def cambiar_empresa(empresa_id: int, datos: CambioEmpresa, u: seg.Usuario = Depends(cargar)) -> dict:
    srv, user = servicio(), u.como_dict()
    try:
        if datos.quitar_enlace:
            srv.enlazar_cliente(user, empresa_id, None)
        elif datos.cliente_id is not None:
            srv.enlazar_cliente(user, empresa_id, datos.cliente_id)
        if datos.activa is not None:
            srv.cambiar_estado(user, empresa_id, datos.activa)
    except Exception as e:
        _error(e)
    return {"ok": True}


# =========================
# Cargas
# =========================
def _fila_bitacora(f: dict) -> dict:
    return {"id": f["id"], "fecha": (f["finalizado_en"] or f["iniciado_en"]).isoformat(),
            "archivo": f["archivo"], "resultado": f["resultado"], "usuario": f.get("usuario"),
            "empresas": f["clientes"], "leidas": f["filas_leidas"], "nuevas": f["insertadas"],
            "actualizadas": f["actualizadas"], "rechazadas": f["rechazadas"],
            "faltantes": f.get("faltantes") or 0, "descuadres_saldo": f.get("descuadres_saldo") or 0,
            "mensaje": (f["mensaje"] or "").split("\n", 1)[0]}


@router.get("/cargas")
def bitacora(u: seg.Usuario = Depends(ver)) -> dict:
    return {"cargas": [_fila_bitacora(f) for f in servicio().bitacora(u.como_dict(), 50)]}


@router.post("/cargas")
async def carga_manual(
    archivo: UploadFile = File(...),
    empresa: str | None = Form(None),
    forzar: bool = Form(False),
    eliminar_faltantes: bool = Form(False),
    u: seg.Usuario = Depends(cargar),
) -> dict:
    nombre = Path(archivo.filename or "archivo").name
    sufijo = Path(nombre).suffix.lower()
    if sufijo not in (".csv", ".xlsx"):
        raise HTTPException(400, "Formato no admitido. Use el CSV «Historial de pagos» o el Excel de AdamoPay.")
    if sufijo == ".csv" and not (empresa or "").strip():
        raise HTTPException(400, "Indique a qué empresa corresponde el CSV.")
    contenido = await archivo.read(TAMANO_MAX_CARGA + 1)
    if len(contenido) > TAMANO_MAX_CARGA:
        raise HTTPException(413, "El archivo supera 25 MB. Use la carga automática o el script de carga.")
    with tempfile.TemporaryDirectory() as tmp:
        ruta = Path(tmp) / f"carga{sufijo}"
        ruta.write_bytes(contenido)
        try:
            r = servicio().cargar_archivo(u.como_dict(), ruta, nombre,
                                          cliente=(empresa or "").strip() or None,
                                          forzar=forzar, eliminar_faltantes=eliminar_faltantes)
        except ErrorDominio as e:
            _error(e)
        except Exception as e:
            logger.exception("Carga manual fallida: %s", nombre)
            raise HTTPException(400, f"No se pudo cargar el archivo: {e}")
    d = r.to_dict()
    d["rechazos"] = d["rechazos"][:500]
    return d


# =========================
# OneDrive
# =========================
@router.get("/nube")
def nube(u: seg.Usuario = Depends(ver)) -> dict:
    e = servicio().estado_nube(u.como_dict())
    conexion = e["conexion"]
    return {
        "configurada": e["configurada"], "delegado": e["delegado"], "lista": e["lista"],
        "descripcion": e["descripcion"],
        "conexion": ({k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in conexion.items()}
                     if conexion else None),
        "revisiones": [{"id": r["id"], "fecha": (r["finalizado_en"] or r["iniciado_en"]).isoformat(),
                        "resultado": r["resultado"], "usuario": r["usuario"], "mensaje": r["mensaje"],
                        "nuevos": r["archivos_nuevos"], "cargados": r["cargados"], "errores": r["errores"]}
                       for r in e["revisiones"]],
        "archivos": [{"fecha": a["procesado_en"].isoformat(), "empresa": a["empresa"], "nombre": a["nombre"],
                      "resultado": a["resultado"], "mensaje": (a["mensaje"] or "").split("\n", 1)[0]}
                     for a in e["archivos"]],
    }


@router.post("/nube/sincronizar")
def sincronizar(u: seg.Usuario = Depends(cargar)) -> dict:
    from app.monitoreo_tx.nube.fuentes import ErrorFuente
    try:
        r = servicio().sincronizar_nube_ahora(u.como_dict())
    except ErrorDominio as e:
        _error(e)
    except ErrorFuente as e:
        raise HTTPException(400, str(e))
    return r.to_dict()


# Flujos de conexión pendientes: el device_code no sale del servidor
_flujos: dict[int, tuple[str, float]] = {}
_candado_flujos = threading.Lock()


@router.post("/nube/conectar")
def conectar(u: seg.Usuario = Depends(cargar)) -> dict:
    try:
        flujo = servicio().iniciar_conexion_onedrive(u.como_dict())
    except ErrorDominio as e:
        _error(e)
    except Exception as e:
        raise HTTPException(400, f"No se pudo iniciar la conexión: {e}")
    with _candado_flujos:
        _flujos[u.id] = (flujo["device_code"], time.time() + int(flujo.get("expires_in", 900)))
    return {"codigo": flujo["user_code"], "url": flujo["verification_uri"],
            "vence_en_s": int(flujo.get("expires_in", 900))}


@router.post("/nube/completar")
def completar(u: seg.Usuario = Depends(cargar)) -> dict:
    with _candado_flujos:
        flujo = _flujos.get(u.id)
    if not flujo or flujo[1] < time.time():
        raise HTTPException(400, "No hay una conexión en curso o el código venció. Pida uno nuevo.")
    try:
        hecho = servicio().completar_conexion_onedrive(u.como_dict(), flujo[0])
    except ErrorDominio as e:
        _error(e)
    except Exception as e:
        with _candado_flujos:
            _flujos.pop(u.id, None)
        raise HTTPException(400, str(e))
    if hecho is None:
        return {"listo": False}
    with _candado_flujos:
        _flujos.pop(u.id, None)
    return {"listo": True, "cuenta": hecho["cuenta"]}


@router.post("/nube/desconectar")
def desconectar(u: seg.Usuario = Depends(cargar)) -> dict:
    servicio().desconectar_onedrive(u.como_dict())
    return {"ok": True}
