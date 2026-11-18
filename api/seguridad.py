"""
Sesión, inicio de sesión y permisos de la API.

- Mismas cuentas que la app Streamlit: tabla `usuarios` (bcrypt) y el
  administrador de emergencia de las variables ADMIN_USERNAME / ADMIN_PASSWORD.
- Sesión en una cookie HttpOnly firmada con HMAC-SHA256 (SECRET_KEY). El
  navegador no puede leerla ni modificarla; el frontend nunca ve un token.
- En cada petición se vuelve a comprobar que el usuario siga activo: desactivar
  a alguien lo saca de inmediato.
- Protección CSRF: toda petición que modifica datos debe traer la cabecera
  X-C360 (un sitio ajeno no puede enviarla con la cookie del usuario).
- Límite de intentos: 5 fallos seguidos por usuario+IP bloquean 60 s.
- Cada ingreso, fallido o no, queda en log_auditoria.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import threading
import time
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status

from config.settings import APP_ENV, Roles

logger = logging.getLogger(__name__)

COOKIE = "c360_sesion"
CABECERA_CSRF = "X-C360"
DURACION_SESION_S = int(os.getenv("SESSION_TIMEOUT_MINUTES", "480")) * 60
# Los usuarios externos (rol «cliente») tienen una sesión más corta
DURACION_SESION_CLIENTE_S = int(os.getenv("SESSION_TIMEOUT_MINUTES_CLIENTE", "60")) * 60


def duracion_sesion(rol: str) -> int:
    return min(DURACION_SESION_S, DURACION_SESION_CLIENTE_S) if rol == "cliente" else DURACION_SESION_S
MAX_FALLOS = 5
BLOQUEO_S = 60


@dataclass(frozen=True)
class Usuario:
    id: int
    username: str
    nombre: str
    rol: str
    email: str = ""

    def como_dict(self) -> dict:
        """Formato que esperan los servicios existentes (igual a st.session_state['user'])."""
        return {"id": self.id, "username": self.username, "nombre_completo": self.nombre,
                "rol": self.rol, "email": self.email}


# =========================
# Token de sesión
# =========================
def _clave() -> bytes:
    clave = os.getenv("SECRET_KEY", "")
    if not clave:
        if APP_ENV == "production":
            raise RuntimeError("SECRET_KEY no está definida")
        clave = "dev-api-no-usar-en-produccion"
    return hashlib.sha256(("c360-api-sesion:" + clave).encode()).digest()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def crear_token(u: Usuario) -> str:
    datos = {"uid": u.id, "usr": u.username, "nom": u.nombre, "rol": u.rol, "eml": u.email,
             "exp": int(time.time()) + duracion_sesion(u.rol)}
    cuerpo = _b64(json.dumps(datos, separators=(",", ":")).encode())
    firma = _b64(hmac.new(_clave(), cuerpo.encode(), hashlib.sha256).digest())
    return f"{cuerpo}.{firma}"


def leer_token(token: str) -> Usuario | None:
    try:
        cuerpo, firma = token.split(".", 1)
        esperada = _b64(hmac.new(_clave(), cuerpo.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(firma, esperada):
            return None
        datos = json.loads(_unb64(cuerpo))
        if int(datos["exp"]) < time.time():
            return None
        return Usuario(id=int(datos["uid"]), username=datos["usr"], nombre=datos.get("nom", ""),
                       rol=datos["rol"], email=datos.get("eml", ""))
    except Exception:
        return None


def opciones_cookie(rol: str = "") -> dict:
    return {"key": COOKIE, "httponly": True, "samesite": "lax", "path": "/",
            "secure": APP_ENV == "production", "max_age": duracion_sesion(rol)}


# =========================
# Límite de intentos
# =========================
_fallos: dict[str, tuple[int, float]] = {}
_candado = threading.Lock()


def bloqueado(clave: str) -> int:
    """Segundos restantes de bloqueo (0 si no está bloqueado)."""
    with _candado:
        n, desde = _fallos.get(clave, (0, 0.0))
        if n >= MAX_FALLOS:
            restante = int(BLOQUEO_S - (time.time() - desde))
            if restante > 0:
                return restante
            _fallos.pop(clave, None)
    return 0


def registrar_fallo(clave: str) -> None:
    with _candado:
        n, _ = _fallos.get(clave, (0, 0.0))
        _fallos[clave] = (n + 1, time.time())


def limpiar_fallos(clave: str) -> None:
    with _candado:
        _fallos.pop(clave, None)


# =========================
# Autenticación
# =========================
_HASH_FICTICIO: bytes | None = None


def _hash_ficticio() -> bytes:
    global _HASH_FICTICIO
    if _HASH_FICTICIO is None:
        import bcrypt
        _HASH_FICTICIO = bcrypt.hashpw(b"no-es-una-clave", bcrypt.gensalt(12))
    return _HASH_FICTICIO


def autenticar(username: str, password: str) -> Usuario | None:
    """Mismas reglas que app/auth/login.py, sin el atajo PLACEHOLDER_HASH."""
    import bcrypt
    from sqlalchemy import text
    from db.database import engine

    env_user = os.getenv("ADMIN_USERNAME", "admin")
    env_pass = os.getenv("ADMIN_PASSWORD", "")
    if env_pass and hmac.compare_digest(username, env_user) and hmac.compare_digest(password, env_pass):
        return Usuario(id=0, username=env_user, nombre="Administrador del Sistema", rol="admin",
                       email=os.getenv("ADMIN_EMAIL", ""))

    with engine.connect() as conn:
        fila = conn.execute(
            text("SELECT id, username, nombre_completo, email, rol, password_hash "
                 "FROM usuarios WHERE username = :u AND activo = 1"), {"u": username},
        ).mappings().first()
    if not fila or fila["password_hash"] in ("", "PLACEHOLDER_HASH"):
        # Se compara igual contra un hash ficticio: misma demora exista o no el usuario
        bcrypt.checkpw(b"x", _hash_ficticio())
        return None
    try:
        valido = bcrypt.checkpw(password.encode(), fila["password_hash"].encode())
    except ValueError:
        valido = False
    if not valido:
        return None
    with engine.begin() as conn:
        conn.execute(text("UPDATE usuarios SET ultimo_acceso = CURRENT_TIMESTAMP WHERE id = :id"),
                     {"id": fila["id"]})
    return Usuario(id=fila["id"], username=fila["username"], nombre=fila["nombre_completo"] or "",
                   rol=fila["rol"], email=fila["email"] or "")


def sigue_activo(u: Usuario) -> bool:
    if u.id == 0:
        return bool(os.getenv("ADMIN_PASSWORD"))
    from sqlalchemy import text
    from db.database import engine
    with engine.connect() as conn:
        fila = conn.execute(text("SELECT rol FROM usuarios WHERE id = :id AND activo = 1"),
                            {"id": u.id}).first()
    # Si le cambiaron el rol, la sesión anterior deja de valer: debe ingresar de nuevo
    return fila is not None and fila[0] == u.rol


def auditar(u: Usuario | None, accion: str, entidad: str, descripcion: str, *,
            username: str | None = None, entidad_id: int | None = None, ip: str | None = None,
            resultado: str = "exitoso", valores_nuevos: dict | None = None) -> None:
    try:
        from db.database import get_session
        from db.repositories.audit_repo import AuditRepository
        with next(get_session()) as s:
            AuditRepository(s).registrar(
                username=(u.username if u else username) or "desconocido",
                usuario_id=u.id if u else None, accion=accion, entidad=entidad,
                entidad_id=entidad_id, descripcion=descripcion, ip_address=ip,
                resultado=resultado, rol_usuario=u.rol if u else None, valores_nuevos=valores_nuevos,
            )
    except Exception:
        logger.exception("No se pudo registrar en log_auditoria: %s", descripcion)


def ip_cliente(request: Request) -> str:
    reenviada = request.headers.get("x-forwarded-for", "")
    return reenviada.split(",")[0].strip() or (request.client.host if request.client else "")


# =========================
# Dependencias de FastAPI
# =========================
def usuario_actual(request: Request) -> Usuario:
    token = request.cookies.get(COOKIE)
    u = leer_token(token) if token else None
    if u is None or not sigue_activo(u):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión no válida o vencida.")
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get(CABECERA_CSRF) != "1":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Petición rechazada (falta la cabecera de seguridad).")
    return u


def requiere_roles(roles: frozenset[str] | set[str]):
    def _dep(u: Usuario = Depends(usuario_actual)) -> Usuario:
        if u.rol not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Su rol no tiene acceso a esta sección.")
        return u
    return _dep


# Módulos que el frontend puede mostrar según el rol (menú lateral)
def modulos_visibles(rol: str) -> list[str]:
    from core.monitoreo_tx.config import ROLES_CONSULTA
    mods = []
    if rol in ROLES_CONSULTA:
        mods.append("monitoreo")
    if rol in Roles.CAN_VIEW_AUDIT:
        mods.append("auditoria")
    if rol == "super_admin":
        mods.append("usuarios")
    return mods
