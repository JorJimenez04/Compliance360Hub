"""Inicio y cierre de sesión."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from api import seguridad as seg

router = APIRouter(prefix="/api/auth", tags=["sesión"])


class Credenciales(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=256)


def _perfil(u: seg.Usuario) -> dict:
    return {"id": u.id, "username": u.username, "nombre": u.nombre or u.username, "rol": u.rol,
            "email": u.email, "modulos": seg.modulos_visibles(u.rol)}


@router.post("/login")
def login(datos: Credenciales, request: Request, response: Response) -> dict:
    ip = seg.ip_cliente(request)
    clave = f"{datos.username.strip().lower()}|{ip}"
    if (espera := seg.bloqueado(clave)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"Demasiados intentos. Intente de nuevo en {espera} segundos.")
    u = seg.autenticar(datos.username.strip(), datos.password)
    if u is None:
        seg.registrar_fallo(clave)
        seg.auditar(None, "LOGIN_FAIL", "usuarios", f"Inicio de sesión fallido (nueva interfaz) · IP: {ip}",
                    username=datos.username.strip(), ip=ip, resultado="fallido")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario o contraseña incorrectos.")
    seg.limpiar_fallos(clave)
    seg.auditar(u, "LOGIN", "usuarios", f"Inicio de sesión exitoso (nueva interfaz) · IP: {ip}",
                entidad_id=u.id or None, ip=ip)
    response.set_cookie(value=seg.crear_token(u), **seg.opciones_cookie())
    return _perfil(u)


@router.post("/logout")
def logout(response: Response, u: seg.Usuario = Depends(seg.usuario_actual)) -> dict:
    response.delete_cookie(seg.COOKIE, path="/")
    return {"ok": True}


@router.get("/yo")
def yo(u: seg.Usuario = Depends(seg.usuario_actual)) -> dict:
    return _perfil(u)
