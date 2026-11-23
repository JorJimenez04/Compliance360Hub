"""Organizaciones: los clientes de la plataforma (migración 038).

Cada organización es un sujeto obligado independiente. Solo el super_admin las crea
o modifica. El equipo interno las ve todas (para el selector); un usuario externo
solo ve la suya, y nunca sabe qué otras existen.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from api import seguridad as seg
from core.monitoreo_tx.config import ROLES_MONITOREO

router = APIRouter(prefix="/api/organizaciones", tags=["organizaciones"])

solo_super_admin = seg.requiere_roles(frozenset({"super_admin"}))
con_sesion = seg.usuario_actual


def _limpiar(valor: str | None) -> str | None:
    valor = (valor or "").strip()
    return valor or None


@router.get("")
def listar(u: seg.Usuario = Depends(con_sesion)) -> dict:
    from db.database import engine
    if u.externo:
        # Solo la propia, sin cifras internas
        with engine.connect() as conn:
            fila = conn.execute(text("SELECT id, nombre FROM organizaciones WHERE id = :id"),
                                {"id": u.organizacion_id}).mappings().first()
        return {"organizaciones": [dict(fila)] if fila else []}
    if u.rol not in ROLES_MONITOREO:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Su rol no tiene acceso a esta sección.")
    with engine.connect() as conn:
        filas = conn.execute(text(
            "SELECT o.id, o.nombre, o.nit, o.activa, o.notas, o.created_at, "
            "  (SELECT count(*) FROM tx_empresas e WHERE e.organizacion_id = o.id) AS empresas, "
            "  (SELECT count(*) FROM clientes c WHERE c.organizacion_id = o.id) AS clientes, "
            "  (SELECT count(*) FROM usuarios x WHERE x.organizacion_id = o.id AND x.activo = 1) AS usuarios "
            "FROM organizaciones o ORDER BY lower(o.nombre)")).mappings().all()
    return {"organizaciones": [{
        **{k: f[k] for k in ("id", "nombre", "nit", "notas", "empresas", "clientes", "usuarios")},
        "activa": bool(f["activa"]),
        "creada": f["created_at"].isoformat() if f["created_at"] else None,
    } for f in filas]}


class NuevaOrganizacion(BaseModel):
    nombre: str = Field(min_length=2, max_length=120)
    nit: str | None = Field(None, max_length=30)
    notas: str | None = Field(None, max_length=1000)


@router.post("", status_code=201)
def crear(datos: NuevaOrganizacion, request: Request, u: seg.Usuario = Depends(solo_super_admin)) -> dict:
    from db.database import engine
    nombre = datos.nombre.strip()
    if len(nombre) < 2:
        raise HTTPException(400, "El nombre es obligatorio.")
    try:
        with engine.begin() as conn:
            nuevo = conn.execute(text(
                "INSERT INTO organizaciones (nombre, nit, notas, creado_por) VALUES (:n, :nit, :no, :por) "
                "RETURNING id"), {"n": nombre, "nit": _limpiar(datos.nit), "no": _limpiar(datos.notas),
                                  "por": u.username}).scalar_one()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una organización con ese nombre o NIT.")
    seg.auditar(u, "CREATE", "organizaciones", f"Organización «{nombre}» creada por {u.username}",
                entidad_id=nuevo, ip=seg.ip_cliente(request), valores_nuevos={"nombre": nombre, "nit": datos.nit})
    return {"id": nuevo, "nombre": nombre}


class CambioOrganizacion(BaseModel):
    nombre: str | None = Field(None, min_length=2, max_length=120)
    nit: str | None = Field(None, max_length=30)
    notas: str | None = Field(None, max_length=1000)
    activa: bool | None = None


@router.patch("/{organizacion_id}")
def cambiar(organizacion_id: int, datos: CambioOrganizacion, request: Request,
            u: seg.Usuario = Depends(solo_super_admin)) -> dict:
    """Desactivar una organización saca de inmediato a sus usuarios externos (ver seguridad.sigue_activo)."""
    from db.database import engine
    cambios = datos.model_dump(exclude_unset=True)
    if not cambios:
        return {"ok": True}
    valores = {}
    if "nombre" in cambios:
        if not (cambios["nombre"] or "").strip():
            raise HTTPException(400, "El nombre es obligatorio.")
        valores["nombre"] = cambios["nombre"].strip()
    if "nit" in cambios:
        valores["nit"] = _limpiar(cambios["nit"])
    if "notas" in cambios:
        valores["notas"] = _limpiar(cambios["notas"])
    if "activa" in cambios and cambios["activa"] is not None:
        valores["activa"] = bool(cambios["activa"])
    if not valores:
        return {"ok": True}
    sets = ", ".join(f"{k} = :{k}" for k in valores)
    try:
        with engine.begin() as conn:
            hecho = conn.execute(text(f"UPDATE organizaciones SET {sets} WHERE id = :id"),
                                 {**valores, "id": organizacion_id}).rowcount
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una organización con ese nombre o NIT.")
    if not hecho:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La organización no existe.")
    seg.auditar(u, "UPDATE", "organizaciones", f"Organización {organizacion_id} modificada por {u.username}",
                entidad_id=organizacion_id, ip=seg.ip_cliente(request), valores_nuevos=valores)
    return {"ok": True}
