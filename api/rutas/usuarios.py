"""Administración de usuarios clientes: solo el super_admin.

El cliente no puede cambiar su propia clave: si la pierde o sospecha que se filtró, el
super_admin le genera una nueva. La clave nueva se muestra UNA vez (en la base solo queda
su hash) y todo queda en log_auditoria.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text

from api import seguridad as seg
from api.claves import clave_temporal, hash_clave

router = APIRouter(prefix="/api/usuarios", tags=["usuarios"])

ROL_CLIENTE = "cliente"
ROLES_ADMIN_USUARIOS = frozenset({"super_admin"})
solo_super_admin = seg.requiere_roles(ROLES_ADMIN_USUARIOS)


@router.get("/clientes")
def listar_clientes(u: seg.Usuario = Depends(solo_super_admin)) -> dict:
    from db.database import engine
    with engine.connect() as conn:
        filas = conn.execute(text(
            "SELECT u.id, u.username, u.nombre_completo, u.email, u.activo, u.ultimo_acceso, "
            "COALESCE(string_agg(e.nombre_reporte, ', ' ORDER BY e.nombre_reporte), '') AS empresas "
            "FROM usuarios u "
            "LEFT JOIN usuario_empresas ue ON ue.usuario_id = u.id "
            "LEFT JOIN tx_empresas e ON e.id = ue.empresa_id "
            "WHERE u.rol = :r GROUP BY u.id ORDER BY u.nombre_completo"), {"r": ROL_CLIENTE}).mappings().all()
    return {"clientes": [{
        "id": f["id"], "username": f["username"], "nombre": f["nombre_completo"] or f["username"],
        "email": f["email"], "activo": bool(f["activo"]),
        "ultimo_acceso": f["ultimo_acceso"].isoformat() if f["ultimo_acceso"] else None,
        "empresas": f["empresas"],
    } for f in filas]}


@router.post("/clientes/{usuario_id}/restablecer-clave")
def restablecer_clave(usuario_id: int, request: Request, u: seg.Usuario = Depends(solo_super_admin)) -> dict:
    from db.database import engine
    nueva = clave_temporal()
    with engine.begin() as conn:
        # Solo clientes: un usuario interno no se puede tocar desde aquí
        fila = conn.execute(text("SELECT id, username FROM usuarios WHERE id = :id AND rol = :r"),
                            {"id": usuario_id, "r": ROL_CLIENTE}).mappings().first()
        if not fila:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "El cliente no existe.")
        conn.execute(text("UPDATE usuarios SET password_hash = :h, activo = 1, updated_at = CURRENT_TIMESTAMP "
                          "WHERE id = :id"), {"h": hash_clave(nueva), "id": usuario_id})
    seg.auditar(u, "UPDATE", "usuarios",
                f"Clave del cliente «{fila['username']}» restablecida por {u.username}",
                entidad_id=usuario_id, ip=seg.ip_cliente(request))
    return {"username": fila["username"], "clave_temporal": nueva}
