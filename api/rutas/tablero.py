"""
Tablero general de cumplimiento y reportes UIAF (decisiones 2026-11-28).

Solo equipo interno. El director de cumplimiento lo consulta (es su pantalla de inicio);
super_admin y compliance además cargan los reportes UIAF en PDF. Los reportes tienen
reserva legal: nunca los ve el cliente ni la junta, y cada descarga queda en la auditoría.
"""

from __future__ import annotations

from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from api import seguridad as seg
from api.rutas.aliados import _organizacion
from api.rutas.clientes import _cliente, _json
from core.cumplimiento import reportes_uiaf as ru
from core.cumplimiento import requerimientos as rq
from core.cumplimiento import tablero as tb
from core.monitoreo_tx.config import ROLES_CARGA, ROLES_MONITOREO

router = APIRouter(tags=["tablero"])
interno = seg.requiere_roles(ROLES_MONITOREO)
gestion = seg.requiere_roles(ROLES_CARGA)
solo_super = seg.requiere_roles(frozenset({"super_admin"}))


def _engine():
    from db.database import engine
    return engine


@router.get("/api/tablero")
def tablero(desde: date | None = Query(None), hasta: date | None = Query(None),
            organizacion_id: int | None = Query(None), u: seg.Usuario = Depends(interno)) -> dict:
    if (desde is None) != (hasta is None):
        raise HTTPException(400, "Indique el periodo completo (desde y hasta) o ninguno.")
    if desde and hasta and hasta < desde:
        raise HTTPException(400, "El periodo está al revés.")
    if organizacion_id:
        _organizacion(organizacion_id)
    return _json(tb.tablero(_engine(), desde, hasta, organizacion_id))


# ---------- Reportes UIAF ----------
@router.get("/api/organizaciones/{organizacion_id}/reportes-uiaf")
def reportes(organizacion_id: int, u: seg.Usuario = Depends(interno)) -> dict:
    _organizacion(organizacion_id)
    return _json({"reportes": ru.listar(_engine(), organizacion_id), "tipos": ru.TIPOS})


@router.post("/api/organizaciones/{organizacion_id}/reportes-uiaf", status_code=201)
async def cargar_reporte(
    organizacion_id: int, request: Request,
    archivo: UploadFile = File(...),
    tipo: str = Form(...),
    fecha_presentacion: date = Form(...),
    periodo_desde: date | None = Form(None),
    periodo_hasta: date | None = Form(None),
    radicado: str | None = Form(None),
    cliente_id: int | None = Form(None),
    descripcion: str | None = Form(None),
    u: seg.Usuario = Depends(gestion),
) -> dict:
    org = _organizacion(organizacion_id)
    contenido = await archivo.read(ru.MAX_BYTES + 1)
    datos = {"tipo": tipo, "fecha_presentacion": fecha_presentacion, "periodo_desde": periodo_desde,
             "periodo_hasta": periodo_hasta, "radicado": radicado, "cliente_id": cliente_id, "descripcion": descripcion}
    try:
        rid = ru.guardar(_engine(), organizacion_id, datos, archivo.filename or "reporte.pdf", contenido, u.username)
    except ru.ErrorReporte as e:
        raise HTTPException(400, str(e))
    seg.auditar(u, "CREATE", "reportes_uiaf", f"Reporte UIAF {tipo} de «{org}» cargado"
                f"{f' (radicado {radicado})' if radicado else ''}", entidad_id=rid, ip=seg.ip_cliente(request),
                valores_nuevos=_json({k: v for k, v in datos.items() if k != "descripcion"}))
    return {"id": rid}


@router.get("/api/reportes-uiaf/{reporte_id}/archivo")
def descargar_reporte(reporte_id: int, request: Request, u: seg.Usuario = Depends(interno)) -> Response:
    try:
        r = ru.archivo(_engine(), reporte_id)
    except LookupError as e:
        raise HTTPException(404, str(e))
    seg.auditar(u, "READ", "reportes_uiaf", f"Descarga del reporte UIAF {r['tipo']} «{r['archivo_nombre']}»",
                entidad_id=reporte_id, ip=seg.ip_cliente(request))
    return Response(r["archivo"], media_type="application/pdf", headers={
        "Content-Disposition": f"inline; filename*=UTF-8''{quote(r['archivo_nombre'])}",
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


class Eliminacion(BaseModel):
    motivo: str = Field(min_length=10, max_length=1000)


@router.post("/api/organizaciones/{organizacion_id}/reportes-uiaf/{reporte_id}/eliminar")
def eliminar_reporte(organizacion_id: int, reporte_id: int, datos: Eliminacion, request: Request,
                     u: seg.Usuario = Depends(solo_super)) -> dict:
    org = _organizacion(organizacion_id)
    try:
        r = ru.eliminar(_engine(), organizacion_id, reporte_id)
    except LookupError as e:
        raise HTTPException(404, str(e))
    seg.auditar(u, "DELETE", "reportes_uiaf", f"Reporte UIAF {r['tipo']} «{r['archivo_nombre']}» de «{org}» eliminado. "
                f"Motivo: {datos.motivo}", entidad_id=reporte_id, ip=seg.ip_cliente(request), valores_nuevos=_json(r))
    return {"ok": True}


# ---------- Beneficiarios para los requerimientos ----------
@router.get("/api/clientes/{cliente_id}/beneficiarios/buscar")
def buscar_beneficiarios(cliente_id: int, q: str = Query(..., max_length=100), u: seg.Usuario = Depends(interno)) -> dict:
    _cliente(cliente_id)
    return _json({"beneficiarios": rq.buscar_beneficiarios(_engine(), cliente_id, q)})
