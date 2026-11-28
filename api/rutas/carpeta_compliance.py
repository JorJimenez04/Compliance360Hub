"""
Carpeta Compliance de cada organización: un solo enlace para subclientes, aliados y
requerimientos (fase 2, cierre). Consulta: equipo interno; enlazar y revisar: gestión.
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from api import seguridad as seg
from api.rutas.aliados import _organizacion
from api.rutas.clientes import _cliente, _json
from core.cumplimiento import carpeta_compliance as cc
from core.cumplimiento import documentos as doc
from core.monitoreo_tx.config import ROLES_CARGA, ROLES_MONITOREO

router = APIRouter(tags=["carpeta compliance"])
interno = seg.requiere_roles(ROLES_MONITOREO)
gestion = seg.requiere_roles(ROLES_CARGA)


def _engine():
    from db.database import engine
    return engine


class Enlace(BaseModel):
    enlace: str | None = Field(None, max_length=2000)


@router.get("/api/organizaciones/{organizacion_id}/carpeta-compliance")
def estado(organizacion_id: int, u: seg.Usuario = Depends(interno)) -> dict:
    _organizacion(organizacion_id)
    return _json(cc.estado(_engine(), organizacion_id))


@router.put("/api/organizaciones/{organizacion_id}/carpeta-compliance")
def enlazar(organizacion_id: int, datos: Enlace, request: Request, u: seg.Usuario = Depends(gestion)) -> dict:
    org = _organizacion(organizacion_id)
    try:
        cc.guardar_enlace(_engine(), organizacion_id, datos.enlace)
    except doc.ErrorCarpeta as e:
        raise HTTPException(400, str(e))
    seg.auditar(u, "UPDATE", "organizaciones", f"Carpeta Compliance de «{org}» {'enlazada' if datos.enlace else 'desenlazada'}",
                entidad_id=organizacion_id, ip=seg.ip_cliente(request))
    if not datos.enlace:
        return {"ok": True, "resumen": None}
    return revisar(organizacion_id, request, u)


@router.post("/api/organizaciones/{organizacion_id}/carpeta-compliance/revisar")
def revisar(organizacion_id: int, request: Request, u: seg.Usuario = Depends(gestion)) -> dict:
    org = _organizacion(organizacion_id)
    try:
        resumen = cc.revisar_organizacion(_engine(), organizacion_id, usuario=u.username)
    except doc.ErrorCarpeta as e:
        raise HTTPException(400, str(e))
    seg.auditar(u, "READ", "organizaciones", f"Carpeta Compliance de «{org}» revisada: {len(resumen['subclientes'])} subclientes, "
                f"{len(resumen['aliados'])} aliados, {resumen['requerimientos']} requerimientos", entidad_id=organizacion_id,
                ip=seg.ip_cliente(request))
    return _json({"ok": True, "resumen": resumen})


@router.get("/api/clientes/{cliente_id}/paquete-banco")
def paquete_banco(cliente_id: int, request: Request, u: seg.Usuario = Depends(interno)) -> Response:
    """ZIP con el resumen KYC en PDF y los documentos propios del subcliente (desde OneDrive)."""
    from core.cumplimiento import paquete_banco as pb
    _cliente(cliente_id)
    try:
        nombre, contenido, info = pb.generar(_engine(), cliente_id)
    except doc.ErrorCarpeta as e:
        raise HTTPException(400, str(e))
    except LookupError as e:
        raise HTTPException(404, str(e))
    seg.auditar(u, "READ", "clientes", f"Paquete para el banco descargado: {nombre} ({info['documentos']} documentos)",
                entidad_id=cliente_id, ip=seg.ip_cliente(request))
    return Response(contenido, media_type="application/zip", headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(nombre)}", "Cache-Control": "no-store"})
