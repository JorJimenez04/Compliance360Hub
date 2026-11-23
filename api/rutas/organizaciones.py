"""Organizaciones: los clientes de la plataforma (migración 038).

Cada organización es un sujeto obligado independiente. Solo el super_admin las crea
o modifica. El equipo interno las ve todas (para el selector); un usuario externo
solo ve la suya, y nunca sabe qué otras existen.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from api import seguridad as seg
from core.cumplimiento import catalogo as cat
from core.monitoreo_tx.config import ROLES_MONITOREO

router = APIRouter(prefix="/api/organizaciones", tags=["organizaciones"])
router_catalogo = APIRouter(prefix="/api/catalogo", tags=["catálogo de cumplimiento"])

solo_super_admin = seg.requiere_roles(frozenset({"super_admin"}))
interno = seg.requiere_roles(ROLES_MONITOREO)
con_sesion = seg.usuario_actual

# Quién puede ser oficial principal: equipo interno de la plataforma
ROLES_OFICIAL = ("super_admin", "admin", "compliance")


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
    # Ficha (migración 039). Los códigos se validan contra core/cumplimiento/catalogo.py
    tipo_persona: str | None = None
    servicios: list[str] | None = Field(None, max_length=30)
    modelos_negocio: list[str] | None = Field(None, max_length=30)
    regimen: str | None = None
    nivel_riesgo: str | None = None
    fecha_calificacion: date | None = None
    proxima_revision: date | None = None
    oficial_principal_id: int | None = None
    oficial_suplente: str | None = Field(None, max_length=200)
    fecha_designacion: date | None = None
    acta_designacion: str | None = Field(None, max_length=200)


def _validar_ficha(cambios: dict) -> dict:
    """Traduce los campos de la ficha a columnas, rechazando códigos fuera del catálogo."""
    v: dict = {}
    if "tipo_persona" in cambios:
        if cambios["tipo_persona"] not in (cat.PJ, cat.PN):
            raise HTTPException(400, "Tipo de persona no válido.")
        v["tipo_persona"] = cambios["tipo_persona"]
    if "servicios" in cambios:
        malos = [c for c in cambios["servicios"] or [] if cat.servicio(c) is None]
        if malos:
            raise HTTPException(400, f"Servicios no válidos: {', '.join(malos)}")
        v["servicios"] = sorted(set(cambios["servicios"] or []))
    if "modelos_negocio" in cambios:
        malos = [c for c in cambios["modelos_negocio"] or [] if cat.modelo(c) is None]
        if malos:
            raise HTTPException(400, f"Modelos de negocio no válidos: {', '.join(malos)}")
        v["modelos_negocio"] = list(dict.fromkeys(cambios["modelos_negocio"] or []))
    if "regimen" in cambios:
        if cambios["regimen"] is not None and cat.regimen(cambios["regimen"]) is None:
            raise HTTPException(400, "Régimen no válido.")
        v["regimen"] = cambios["regimen"]
    if "nivel_riesgo" in cambios:
        if cambios["nivel_riesgo"] not in (*cat.NIVELES, "Sin calificar"):
            raise HTTPException(400, "Nivel de riesgo no válido: use Alto, Medio o Bajo.")
        v["nivel_riesgo"] = cambios["nivel_riesgo"]
    for campo in ("fecha_calificacion", "proxima_revision", "fecha_designacion", "oficial_principal_id"):
        if campo in cambios:
            v[campo] = cambios[campo]
    for campo in ("oficial_suplente", "acta_designacion"):
        if campo in cambios:
            v[campo] = _limpiar(cambios[campo])
    return v


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
    valores |= _validar_ficha(cambios)
    if not valores:
        return {"ok": True}
    sets = ", ".join(f"{k} = :{k}" for k in valores)
    try:
        with engine.begin() as conn:
            if valores.get("oficial_principal_id") is not None:
                rol = conn.scalar(text("SELECT rol FROM usuarios WHERE id = :id AND activo = 1 AND organizacion_id IS NULL"),
                                  {"id": valores["oficial_principal_id"]})
                if rol not in ROLES_OFICIAL:
                    raise HTTPException(400, "El oficial principal debe ser un usuario activo del equipo interno.")
            hecho = conn.execute(text(f"UPDATE organizaciones SET {sets} WHERE id = :id"),
                                 {**valores, "id": organizacion_id}).rowcount
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una organización con ese nombre o NIT.")
    if not hecho:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La organización no existe.")
    seg.auditar(u, "UPDATE", "organizaciones", f"Organización {organizacion_id} modificada por {u.username}",
                entidad_id=organizacion_id, ip=seg.ip_cliente(request), valores_nuevos=valores)
    return {"ok": True}


# =========================
# Ficha y paquete de vinculación
# =========================
_COLUMNAS_FICHA = ("tipo_persona", "servicios", "modelos_negocio", "regimen", "nivel_riesgo", "fecha_calificacion",
                   "proxima_revision", "oficial_principal_id", "oficial_suplente", "fecha_designacion",
                   "acta_designacion")


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


@router.get("/{organizacion_id}")
def ficha(organizacion_id: int, u: seg.Usuario = Depends(interno)) -> dict:
    from db.database import engine
    with engine.connect() as conn:
        f = conn.execute(text(
            "SELECT o.*, x.nombre_completo AS oficial_principal FROM organizaciones o "
            "LEFT JOIN usuarios x ON x.id = o.oficial_principal_id WHERE o.id = :id"),
            {"id": organizacion_id}).mappings().first()
        oficiales = conn.execute(text(
            "SELECT id, nombre_completo FROM usuarios WHERE activo = 1 AND organizacion_id IS NULL "
            "AND rol = ANY(:r) ORDER BY nombre_completo"), {"r": list(ROLES_OFICIAL)}).mappings().all()
    if not f:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La organización no existe.")
    modelos = list(f["modelos_negocio"] or [])
    return {
        "id": f["id"], "nombre": f["nombre"], "nit": f["nit"], "activa": bool(f["activa"]), "notas": f["notas"],
        **{k: _iso(f[k]) for k in _COLUMNAS_FICHA},
        "servicios": list(f["servicios"] or []), "modelos_negocio": modelos,
        "oficial_principal": f["oficial_principal"],
        "riesgo_sugerido": cat.riesgo_sugerido(modelos),
        "monitoreo_sugerido": list(cat.monitoreo_sugerido(modelos)),
        "oficiales_disponibles": [{"id": o["id"], "nombre": o["nombre_completo"]} for o in oficiales],
    }


def _paquete(modelos: list[str], nivel: str, tipo_persona: str, regimen: str | None = None) -> dict:
    try:
        reqs = cat.requisitos(modelos, nivel, tipo_persona)
    except ValueError as e:
        raise HTTPException(400, str(e))
    reg = cat.regimen(regimen) if regimen else None
    return {
        "nivel": nivel, "tipo_persona": tipo_persona, "modelos": modelos,
        "riesgo_sugerido": cat.riesgo_sugerido(modelos),
        "monitoreo_sugerido": list(cat.monitoreo_sugerido(modelos)),
        "regimen": ({"codigo": reg.codigo, "nombre": reg.nombre, "supervisor": reg.supervisor,
                     "sistema": reg.sistema, "reportes_uiaf": list(reg.reportes_uiaf), "nota": reg.nota}
                    if reg else None),
        "senales_alerta": sorted({s for m in modelos for s in cat.modelo(m).senales_alerta}),
        "documentos": [{"codigo": r.documento.codigo, "nombre": r.documento.nombre, "carpeta": r.documento.carpeta,
                        "aporta": r.documento.aporta, "vigencia_meses": r.vigencia_meses, "nota": r.documento.nota,
                        "origen": list(r.origen)} for r in reqs],
    }


@router.get("/{organizacion_id}/paquete")
def paquete_organizacion(organizacion_id: int, u: seg.Usuario = Depends(interno)) -> dict:
    """Documentación e información estandarizada que se le exige a la organización, según su ficha.
    Sin nivel calificado se usa el sugerido por sus modelos (y si no hay modelos, Alto: conservador)."""
    f = ficha(organizacion_id, u)
    nivel = f["nivel_riesgo"] if f["nivel_riesgo"] in cat.NIVELES else (f["riesgo_sugerido"] or "Alto")
    return {**_paquete(f["modelos_negocio"], nivel, f["tipo_persona"], f["regimen"]),
            "nivel_es_provisional": f["nivel_riesgo"] not in cat.NIVELES}


@router_catalogo.get("")
def catalogo(u: seg.Usuario = Depends(interno)) -> dict:
    return cat.como_dict()


@router_catalogo.get("/paquete")
def paquete_prospecto(modelos: list[str] = Query(default=[]), nivel: str | None = None,
                      tipo_persona: str = cat.PJ, regimen: str | None = None,
                      u: seg.Usuario = Depends(interno)) -> dict:
    """Para un cliente potencial, antes de crearlo: qué se le va a pedir."""
    if tipo_persona not in (cat.PJ, cat.PN):
        raise HTTPException(400, "Tipo de persona no válido.")
    nivel = nivel or cat.riesgo_sugerido(modelos) or "Alto"
    return _paquete(modelos, nivel, tipo_persona, regimen)
