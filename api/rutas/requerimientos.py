"""
Requerimientos de compliance de cada organización y de sus clientes.

Solo equipo interno: super_admin y compliance gestionan; el director de cumplimiento solo
consulta. Los clientes no responden desde la app (decisión 2026-11-27). Todo va filtrado
por organización.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api import seguridad as seg
from api.rutas.aliados import _organizacion
from api.rutas.clientes import _cliente, _json
from core.cumplimiento import requerimientos as rq
from core.monitoreo_tx.config import ROLES_CARGA, ROLES_MONITOREO

router = APIRouter(tags=["requerimientos"])
interno = seg.requiere_roles(ROLES_MONITOREO)
gestion = seg.requiere_roles(ROLES_CARGA)


def _engine():
    from db.database import engine
    return engine


def _seguro(fn):
    try:
        return fn()
    except rq.ErrorRequerimiento as e:
        raise HTTPException(400, str(e))
    except LookupError as e:
        raise HTTPException(404, str(e))


class Datos(BaseModel):
    dirigido_a: str | None = None
    cliente_id: int | None = None
    origen: str | None = None
    relacion_aliado_id: int | None = None
    origen_detalle: str | None = Field(None, max_length=200)
    solicitante: str | None = Field(None, max_length=200)
    canal: str | None = None
    tipo: str | None = None
    asunto: str | None = Field(None, max_length=200)
    descripcion: str | None = Field(None, max_length=8000)
    referencias_tx: list[str] | None = Field(None, max_length=200)
    fecha_recibido: date | None = None
    fecha_limite: date | None = None
    prioridad: str | None = None
    responsable: str | None = Field(None, max_length=120)
    carpeta_evidencias: str | None = Field(None, max_length=1000)


class Nuevo(Datos):
    comentario: str | None = Field(None, max_length=2000)


class CambioEstado(BaseModel):
    estado: str
    comentario: str | None = Field(None, max_length=2000)
    fecha_envio: date | None = None
    resumen_respuesta: str | None = Field(None, max_length=4000)


class Nota(BaseModel):
    comentario: str = Field(max_length=4000)


@router.get("/api/requerimientos/catalogos")
def catalogos(u: seg.Usuario = Depends(interno)) -> dict:
    return rq.CATALOGOS


@router.get("/api/organizaciones/{organizacion_id}/requerimientos")
def listar(organizacion_id: int, u: seg.Usuario = Depends(interno)) -> dict:
    _organizacion(organizacion_id)
    return _json({**rq.listar(_engine(), organizacion_id), **rq.opciones(_engine(), organizacion_id)})


@router.get("/api/organizaciones/{organizacion_id}/requerimientos/{rid}")
def detalle(organizacion_id: int, rid: int, u: seg.Usuario = Depends(interno)) -> dict:
    _organizacion(organizacion_id)
    return _json(_seguro(lambda: rq.obtener(_engine(), organizacion_id, rid)))


@router.post("/api/organizaciones/{organizacion_id}/requerimientos", status_code=201)
def crear(organizacion_id: int, datos: Nuevo, request: Request, u: seg.Usuario = Depends(gestion)) -> dict:
    org = _organizacion(organizacion_id)
    d = datos.model_dump(exclude_unset=True)
    r = _seguro(lambda: rq.crear(_engine(), organizacion_id, d, u.username))
    seg.auditar(u, "CREATE", "requerimientos", f"Requerimiento {r['consecutivo']} de «{org}» registrado: {d.get('asunto')}",
                entidad_id=r["id"], ip=seg.ip_cliente(request), valores_nuevos=_json(d))
    return r


@router.patch("/api/organizaciones/{organizacion_id}/requerimientos/{rid}")
def editar(organizacion_id: int, rid: int, datos: Datos, request: Request, u: seg.Usuario = Depends(gestion)) -> dict:
    org = _organizacion(organizacion_id)
    d = datos.model_dump(exclude_unset=True)
    cambios = _seguro(lambda: rq.actualizar(_engine(), organizacion_id, rid, d, u.username))
    if cambios:
        q = rq.obtener(_engine(), organizacion_id, rid)
        seg.auditar(u, "UPDATE", "requerimientos", f"Requerimiento {q['consecutivo']} de «{org}» editado: {', '.join(cambios)}",
                    entidad_id=rid, ip=seg.ip_cliente(request), valores_nuevos=_json({k: d[k] for k in cambios if k in d}))
    return {"ok": True, "cambios": cambios}


@router.post("/api/organizaciones/{organizacion_id}/requerimientos/{rid}/estado")
def estado(organizacion_id: int, rid: int, datos: CambioEstado, request: Request, u: seg.Usuario = Depends(gestion)) -> dict:
    org = _organizacion(organizacion_id)
    _seguro(lambda: rq.cambiar_estado(_engine(), organizacion_id, rid, datos.estado, u.username, comentario=datos.comentario,
                                      fecha_envio=datos.fecha_envio, resumen_respuesta=datos.resumen_respuesta))
    q = rq.obtener(_engine(), organizacion_id, rid)
    seg.auditar(u, "UPDATE", "requerimientos", f"Requerimiento {q['consecutivo']} de «{org}» → {rq.ESTADOS[datos.estado]}",
                entidad_id=rid, ip=seg.ip_cliente(request), valores_nuevos=_json(datos.model_dump(exclude_unset=True)))
    return {"ok": True}


@router.post("/api/organizaciones/{organizacion_id}/requerimientos/{rid}/notas", status_code=201)
def nota(organizacion_id: int, rid: int, datos: Nota, request: Request, u: seg.Usuario = Depends(gestion)) -> dict:
    _organizacion(organizacion_id)
    _seguro(lambda: rq.agregar_nota(_engine(), organizacion_id, rid, datos.comentario, u.username))
    return {"ok": True}


@router.get("/api/clientes/{cliente_id}/requerimientos")
def de_cliente(cliente_id: int, u: seg.Usuario = Depends(interno)) -> dict:
    f = _cliente(cliente_id)
    filas = rq.por_cliente(_engine(), cliente_id)
    return _json({"requerimientos": filas, "resumen": rq.resumen(filas), "organizacion_id": f.get("organizacion_id")})


@router.get("/api/organizaciones/{organizacion_id}/aliados/{relacion_id}/requerimientos")
def de_aliado(organizacion_id: int, relacion_id: int, u: seg.Usuario = Depends(interno)) -> dict:
    _organizacion(organizacion_id)
    filas = rq.por_aliado(_engine(), organizacion_id, relacion_id)
    return _json({"requerimientos": filas, "resumen": rq.resumen(filas)})
