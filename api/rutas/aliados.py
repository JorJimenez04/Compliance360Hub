"""
Aliados bancarios de cada organización (bancos, PSP, VASP… con los que opera).

Solo equipo interno: super_admin y compliance gestionan; el director de cumplimiento
solo consulta (decisión 2026-11-27). Cada consulta va filtrada por organización, para que
el día que se habilite al cliente vea solo lo suyo.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from api import seguridad as seg
from api.rutas.clientes import _json
from core.cumplimiento import aliados as ali
from core.monitoreo_tx.config import ROLES_CARGA, ROLES_MONITOREO

router = APIRouter(tags=["aliados bancarios"])
interno = seg.requiere_roles(ROLES_MONITOREO)
gestion = seg.requiere_roles(ROLES_CARGA)


def _engine():
    from db.database import engine
    return engine


def _organizacion(organizacion_id: int) -> str:
    with _engine().connect() as conn:
        nombre = conn.scalar(text("SELECT nombre FROM organizaciones WHERE id = :id"), {"id": organizacion_id})
    if nombre is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La organización no existe.")
    return nombre


def _seguro(fn):
    try:
        return fn()
    except ali.ErrorAliado as e:
        raise HTTPException(400, str(e))
    except LookupError as e:
        raise HTTPException(404, str(e))


class Entidad(BaseModel):
    nombre: str | None = Field(None, max_length=120)
    razon_social: str | None = Field(None, max_length=200)
    identificacion: str | None = Field(None, max_length=40)
    pais: str | None = Field(None, max_length=60)
    tipo_entidad: str | None = None
    regulado: bool | None = None
    regulador: str | None = Field(None, max_length=120)
    licencia: str | None = Field(None, max_length=120)
    sitio_web: str | None = Field(None, max_length=200)


class Relacion(BaseModel):
    fecha_inicio: date | None = None
    vence_contrato: date | None = None
    vence_poliza: date | None = None
    vence_licencia: date | None = None
    servicios: list[str] | None = Field(None, max_length=10)
    monedas: list[str] | None = Field(None, max_length=10)
    exigencias: list[str] | None = Field(None, max_length=30)
    contacto_cumplimiento: str | None = Field(None, max_length=120)
    correo_cumplimiento: str | None = Field(None, max_length=120)
    telefono_cumplimiento: str | None = Field(None, max_length=40)
    contacto_comercial: str | None = Field(None, max_length=120)
    correo_comercial: str | None = Field(None, max_length=120)
    notas: str | None = Field(None, max_length=4000)


class NuevoAliado(Entidad, Relacion):
    aliado_id: int | None = None               # reutilizar una entidad ya registrada
    estado: str | None = None
    nivel_riesgo: str | None = None
    motivo: str | None = Field(None, max_length=1000)


class CambioAliado(Entidad, Relacion):
    notas_entidad: str | None = Field(None, max_length=4000)


class Movimiento(BaseModel):
    estado: str | None = None
    nivel_riesgo: str | None = None
    proxima_revision: date | None = None
    dd_estado: str | None = None
    dd_fecha: date | None = None
    dd_nivel: str | None = None
    motivo: str = Field(max_length=1000)


@router.get("/api/aliados/catalogos")
def catalogos(u: seg.Usuario = Depends(interno)) -> dict:
    return ali.CATALOGOS


@router.get("/api/aliados/buscar")
def buscar(q: str, u: seg.Usuario = Depends(interno)) -> dict:
    return {"aliados": ali.buscar_catalogo(_engine(), q)}


@router.get("/api/organizaciones/{organizacion_id}/aliados")
def listar(organizacion_id: int, u: seg.Usuario = Depends(interno)) -> dict:
    _organizacion(organizacion_id)
    return _json(ali.listar(_engine(), organizacion_id))


@router.get("/api/organizaciones/{organizacion_id}/aliados/{relacion_id}")
def detalle(organizacion_id: int, relacion_id: int, u: seg.Usuario = Depends(interno)) -> dict:
    _organizacion(organizacion_id)
    return _json(_seguro(lambda: ali.obtener(_engine(), organizacion_id, relacion_id)))


@router.post("/api/organizaciones/{organizacion_id}/aliados", status_code=201)
def crear(organizacion_id: int, datos: NuevoAliado, request: Request, u: seg.Usuario = Depends(gestion)) -> dict:
    org = _organizacion(organizacion_id)
    d = datos.model_dump(exclude_unset=True)
    rid = _seguro(lambda: ali.crear(_engine(), organizacion_id, d, u.username))
    nombre = _seguro(lambda: ali.obtener(_engine(), organizacion_id, rid))["nombre"]
    seg.auditar(u, "CREATE", "aliados_bancarios", f"Aliado bancario «{nombre}» registrado para «{org}»",
                entidad_id=rid, ip=seg.ip_cliente(request), valores_nuevos=_json(d))
    return {"id": rid}


@router.patch("/api/organizaciones/{organizacion_id}/aliados/{relacion_id}")
def cambiar_datos(organizacion_id: int, relacion_id: int, datos: CambioAliado, request: Request,
                  u: seg.Usuario = Depends(gestion)) -> dict:
    org = _organizacion(organizacion_id)
    d = datos.model_dump(exclude_unset=True)
    entidad = {k: v for k, v in d.items() if k in ali.CAMPOS_ENTIDAD and k != "notas"}
    if "notas_entidad" in d:
        entidad["notas"] = d["notas_entidad"]
    relacion = {k: v for k, v in d.items() if k in ali.CAMPOS_RELACION}
    r = _seguro(lambda: ali.actualizar(_engine(), organizacion_id, relacion_id, entidad, relacion))
    nombre = ali.obtener(_engine(), organizacion_id, relacion_id)["nombre"]
    seg.auditar(u, "UPDATE", "aliados_bancarios", f"Aliado bancario «{nombre}» de «{org}» actualizado",
                entidad_id=relacion_id, ip=seg.ip_cliente(request), valores_nuevos=_json(d))
    return {"ok": True, **r}


@router.post("/api/organizaciones/{organizacion_id}/aliados/{relacion_id}/movimientos")
def mover(organizacion_id: int, relacion_id: int, datos: Movimiento, request: Request,
          u: seg.Usuario = Depends(gestion)) -> dict:
    org = _organizacion(organizacion_id)
    d = datos.model_dump(exclude_unset=True)
    hechos = _seguro(lambda: ali.cambiar(_engine(), organizacion_id, relacion_id, d, u.username))
    nombre = ali.obtener(_engine(), organizacion_id, relacion_id)["nombre"]
    seg.auditar(u, "UPDATE", "aliados_bancarios", f"Aliado «{nombre}» de «{org}»: {', '.join(hechos)}. Motivo: {d['motivo']}",
                entidad_id=relacion_id, ip=seg.ip_cliente(request), valores_nuevos=_json(d))
    return {"ok": True, "cambios": hechos}


class Asignacion(BaseModel):
    codigo: str | None = None


@router.post("/api/organizaciones/{organizacion_id}/aliados/documentos/{documento_id}/asignar")
def asignar_documento(organizacion_id: int, documento_id: int, datos: Asignacion, request: Request,
                      u: seg.Usuario = Depends(gestion)) -> dict:
    """Corrige qué documento es un archivo de la carpeta del aliado (cuando el nombre no lo dice)."""
    from core.cumplimiento import carpeta_compliance as cc
    _organizacion(organizacion_id)
    try:
        cc.asignar_documento_aliado(_engine(), organizacion_id, documento_id, datos.codigo, u.username)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except LookupError as e:
        raise HTTPException(404, str(e))
    seg.auditar(u, "UPDATE", "aliados_bancarios", f"Documento de aliado {documento_id} asignado como «{datos.codigo or 'sin asignar'}»",
                entidad_id=documento_id, ip=seg.ip_cliente(request))
    return {"ok": True}
