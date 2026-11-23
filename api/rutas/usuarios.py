"""Administración de usuarios: solo el super_admin crea, modifica y restablece claves.

Perfiles que se gestionan aquí:
  - cliente     equipo de una organización, solo lectura. Alcance 'organizacion' (todas sus
                empresas) o 'empresas' (solo las asignadas).
  - junta       junta directiva de una organización: tablero ejecutivo, sin datos personales.
  - compliance  equipo interno de la plataforma (sin organización).

Nadie puede cambiar su propia clave: el super_admin genera una nueva. La clave se
muestra UNA vez (en la base solo queda su hash) y todo queda en log_auditoria.
No se cambia el rol ni la organización de un usuario existente: se crea otro. Así un
acceso nunca «migra» en silencio de una organización a otra.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from api import seguridad as seg
from api.claves import clave_temporal, hash_clave
from core.monitoreo_tx.config import ALCANCE_EMPRESAS, ALCANCE_ORGANIZACION

router = APIRouter(prefix="/api/usuarios", tags=["usuarios"])

ROL_CLIENTE = "cliente"
ROLES_GESTIONADOS = ("cliente", "junta", "compliance")
ROLES_ADMIN_USUARIOS = frozenset({"super_admin"})
solo_super_admin = seg.requiere_roles(ROLES_ADMIN_USUARIOS)

_USERNAME = re.compile(r"^[A-Za-z0-9._-]{3,60}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _iso(v):
    return v.isoformat() if v else None


@router.get("")
def listar(u: seg.Usuario = Depends(solo_super_admin)) -> dict:
    from db.database import engine
    with engine.connect() as conn:
        filas = conn.execute(text(
            "SELECT u.id, u.username, u.nombre_completo, u.email, u.rol, u.activo, u.ultimo_acceso, "
            "u.organizacion_id, o.nombre AS organizacion, u.alcance, "
            "COALESCE(array_agg(e.id ORDER BY e.nombre_reporte) FILTER (WHERE e.id IS NOT NULL), '{}') AS empresas_ids, "
            "COALESCE(string_agg(e.nombre_reporte, ', ' ORDER BY e.nombre_reporte), '') AS empresas "
            "FROM usuarios u "
            "LEFT JOIN organizaciones o ON o.id = u.organizacion_id "
            "LEFT JOIN usuario_empresas ue ON ue.usuario_id = u.id "
            "LEFT JOIN tx_empresas e ON e.id = ue.empresa_id "
            "WHERE u.rol = ANY(:roles) GROUP BY u.id, o.nombre "
            "ORDER BY o.nombre NULLS FIRST, u.nombre_completo"), {"roles": list(ROLES_GESTIONADOS)}).mappings().all()
    return {"usuarios": [{
        "id": f["id"], "username": f["username"], "nombre": f["nombre_completo"] or f["username"],
        "email": f["email"], "rol": f["rol"], "activo": bool(f["activo"]),
        "ultimo_acceso": _iso(f["ultimo_acceso"]),
        "organizacion_id": f["organizacion_id"], "organizacion": f["organizacion"],
        "alcance": f["alcance"], "empresas_ids": list(f["empresas_ids"]), "empresas": f["empresas"],
    } for f in filas]}


# Compatibilidad con la versión anterior de la pantalla: solo clientes
@router.get("/clientes")
def listar_clientes(u: seg.Usuario = Depends(solo_super_admin)) -> dict:
    return {"clientes": [x for x in listar(u)["usuarios"] if x["rol"] == ROL_CLIENTE]}


class NuevoUsuario(BaseModel):
    username: str = Field(min_length=3, max_length=60)
    nombre: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=160)
    rol: str
    organizacion_id: int | None = None
    alcance: str | None = None
    empresas: list[int] = Field(default_factory=list, max_length=200)


def _validar_empresas(conn, organizacion_id: int, empresas: list[int]) -> None:
    """Todas las empresas deben existir y ser de la organización del usuario."""
    if not empresas:
        return
    propias = set(conn.scalars(text("SELECT id FROM tx_empresas WHERE organizacion_id = :o AND id = ANY(:ids)"),
                               {"o": organizacion_id, "ids": list(set(empresas))}))
    if propias != set(empresas):
        raise HTTPException(400, "Alguna de las empresas no existe o es de otra organización.")


def _reglas_de_perfil(rol: str, organizacion_id: int | None, alcance: str | None, empresas: list[int]) -> None:
    if rol not in ROLES_GESTIONADOS:
        raise HTTPException(400, "Perfil no válido. Use cliente, junta o compliance.")
    if rol in ("cliente", "junta"):
        if organizacion_id is None:
            raise HTTPException(400, "Indique la organización del usuario.")
    elif organizacion_id is not None:
        raise HTTPException(400, "El equipo interno (compliance) no pertenece a una organización.")
    if rol == "cliente":
        # Decisión 2026-11-23: los clientes de los clientes no tienen acceso. Un usuario «cliente» es
        # siempre del equipo de la organización y ve toda su operación (nunca el compliance interno).
        if alcance == ALCANCE_EMPRESAS:
            raise HTTPException(400, "Los clientes de sus clientes no tienen acceso a la plataforma: "
                                     "el perfil Cliente es para el equipo de la organización.")
        if alcance != ALCANCE_ORGANIZACION:
            raise HTTPException(400, "Indique el alcance del usuario.")
        if empresas:
            raise HTTPException(400, "El perfil Cliente ve toda su organización: no se asignan empresas.")
    elif alcance is not None or empresas:
        raise HTTPException(400, "El alcance y las empresas solo aplican al perfil cliente.")


@router.post("", status_code=201)
def crear(datos: NuevoUsuario, request: Request, u: seg.Usuario = Depends(solo_super_admin)) -> dict:
    from db.database import engine
    username, email, nombre = datos.username.strip(), datos.email.strip().lower(), datos.nombre.strip()
    if not _USERNAME.match(username):
        raise HTTPException(400, "Usuario no válido: de 3 a 60 caracteres (letras, números, punto, guion).")
    if not _EMAIL.match(email):
        raise HTTPException(400, "Correo no válido.")
    _reglas_de_perfil(datos.rol, datos.organizacion_id, datos.alcance, datos.empresas)
    clave = clave_temporal()
    try:
        with engine.begin() as conn:
            if datos.organizacion_id is not None:
                activa = conn.scalar(text("SELECT activa FROM organizaciones WHERE id = :id"),
                                     {"id": datos.organizacion_id})
                if activa is None:
                    raise HTTPException(404, "La organización no existe.")
                if not activa:
                    raise HTTPException(400, "La organización está inactiva.")
                _validar_empresas(conn, datos.organizacion_id, datos.empresas)
            nuevo = conn.execute(text(
                "INSERT INTO usuarios (username, nombre_completo, email, password_hash, rol, activo, "
                "organizacion_id, alcance) VALUES (:u, :n, :e, :h, :r, 1, :o, :a) RETURNING id"),
                {"u": username, "n": nombre, "e": email, "h": hash_clave(clave), "r": datos.rol,
                 "o": datos.organizacion_id, "a": datos.alcance}).scalar_one()
            for empresa_id in sorted(set(datos.empresas)):
                conn.execute(text("INSERT INTO usuario_empresas (usuario_id, empresa_id) VALUES (:u, :e)"),
                             {"u": nuevo, "e": empresa_id})
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un usuario con ese nombre de usuario o correo.")
    seg.auditar(u, "CREATE", "usuarios",
                f"Usuario «{username}» ({datos.rol}) creado por {u.username}", entidad_id=nuevo,
                ip=seg.ip_cliente(request),
                valores_nuevos={"rol": datos.rol, "organizacion_id": datos.organizacion_id,
                                "alcance": datos.alcance, "empresas": sorted(set(datos.empresas))})
    return {"id": nuevo, "username": username, "clave_temporal": clave}


class CambioUsuario(BaseModel):
    nombre: str | None = Field(None, min_length=2, max_length=120)
    email: str | None = Field(None, min_length=5, max_length=160)
    activo: bool | None = None
    alcance: str | None = None
    empresas: list[int] | None = Field(None, max_length=200)


def _gestionado(conn, usuario_id: int):
    fila = conn.execute(text("SELECT id, username, rol, organizacion_id, alcance FROM usuarios "
                             "WHERE id = :id AND rol = ANY(:roles)"),
                        {"id": usuario_id, "roles": list(ROLES_GESTIONADOS)}).mappings().first()
    if not fila:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El usuario no existe.")
    return fila


@router.patch("/{usuario_id}")
def cambiar(usuario_id: int, datos: CambioUsuario, request: Request,
            u: seg.Usuario = Depends(solo_super_admin)) -> dict:
    """Cambiar el alcance invalida la sesión abierta del usuario (seguridad.sigue_activo)."""
    from db.database import engine
    cambios = datos.model_dump(exclude_unset=True)
    try:
        with engine.begin() as conn:
            fila = _gestionado(conn, usuario_id)
            valores: dict = {}
            if cambios.get("nombre") is not None:
                valores["nombre_completo"] = cambios["nombre"].strip()
            if cambios.get("email") is not None:
                email = cambios["email"].strip().lower()
                if not _EMAIL.match(email):
                    raise HTTPException(400, "Correo no válido.")
                valores["email"] = email
            if cambios.get("activo") is not None:
                if cambios["activo"] and fila["rol"] == ROL_CLIENTE and fila["alcance"] == ALCANCE_EMPRESAS \
                        and cambios.get("alcance") != ALCANCE_ORGANIZACION:
                    raise HTTPException(400, "Este usuario era de un cliente de su cliente: esos perfiles ya no tienen acceso.")
                valores["activo"] = 1 if cambios["activo"] else 0
            toca_alcance = "alcance" in cambios or "empresas" in cambios
            if toca_alcance:
                if fila["rol"] != ROL_CLIENTE:
                    raise HTTPException(400, "El alcance y las empresas solo aplican al perfil cliente.")
                alcance = cambios.get("alcance") or fila["alcance"]
                if "empresas" in cambios and cambios["empresas"] is not None:
                    empresas = cambios["empresas"]
                elif alcance == ALCANCE_EMPRESAS:
                    empresas = list(conn.scalars(text("SELECT empresa_id FROM usuario_empresas WHERE usuario_id = :u"),
                                                 {"u": usuario_id}))
                else:
                    empresas = []
                _reglas_de_perfil(ROL_CLIENTE, fila["organizacion_id"], alcance, empresas)
                _validar_empresas(conn, fila["organizacion_id"], empresas)
                valores["alcance"] = alcance
                conn.execute(text("DELETE FROM usuario_empresas WHERE usuario_id = :u"), {"u": usuario_id})
                for empresa_id in sorted(set(empresas)):
                    conn.execute(text("INSERT INTO usuario_empresas (usuario_id, empresa_id) VALUES (:u, :e)"),
                                 {"u": usuario_id, "e": empresa_id})
            if valores:
                sets = ", ".join(f"{k} = :{k}" for k in valores)
                conn.execute(text(f"UPDATE usuarios SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE id = :id"),
                             {**valores, "id": usuario_id})
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un usuario con ese correo.")
    seg.auditar(u, "UPDATE", "usuarios", f"Usuario «{fila['username']}» modificado por {u.username}",
                entidad_id=usuario_id, ip=seg.ip_cliente(request),
                valores_nuevos={k: v for k, v in cambios.items()})
    return {"ok": True}


@router.post("/{usuario_id}/restablecer-clave")
def restablecer(usuario_id: int, request: Request, u: seg.Usuario = Depends(solo_super_admin)) -> dict:
    from db.database import engine
    nueva = clave_temporal()
    with engine.begin() as conn:
        # Solo perfiles gestionados aquí: un super_admin u otro rol interno no se toca desde esta pantalla
        fila = _gestionado(conn, usuario_id)
        conn.execute(text("UPDATE usuarios SET password_hash = :h, activo = 1, updated_at = CURRENT_TIMESTAMP "
                          "WHERE id = :id"), {"h": hash_clave(nueva), "id": usuario_id})
    seg.auditar(u, "UPDATE", "usuarios",
                f"Clave de «{fila['username']}» ({fila['rol']}) restablecida por {u.username}",
                entidad_id=usuario_id, ip=seg.ip_cliente(request))
    return {"username": fila["username"], "clave_temporal": nueva}


# Ruta anterior (pantalla vieja): misma regla, solo clientes
@router.post("/clientes/{usuario_id}/restablecer-clave")
def restablecer_clave(usuario_id: int, request: Request, u: seg.Usuario = Depends(solo_super_admin)) -> dict:
    from db.database import engine
    with engine.connect() as conn:
        rol = conn.scalar(text("SELECT rol FROM usuarios WHERE id = :id"), {"id": usuario_id})
    if rol != ROL_CLIENTE:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El cliente no existe.")
    return restablecer(usuario_id, request, u)
