"""
Fuentes de archivos para la carga automática.

Las dos ofrecen lo mismo: listar los CSV de cada subcarpeta-empresa (con una
«versión» que cambia si cambia el contenido) y descargarlos.

- FuenteOneDrive: OneDrive empresarial / SharePoint vía Microsoft Graph, de solo
  lectura, en uno de dos modos:
    · aplicación (client credentials): requiere un administrador que conceda
      Files.Read.All; no depende de ningún usuario.
    · delegado (inicio de sesión con código): sin administrador; la app actúa
      en nombre de un usuario que se conecta una vez y solo lee SUS archivos.
      El acceso se renueva solo con el refresh token guardado cifrado.
- FuenteCarpeta: una carpeta del disco; sirve para pruebas y para cargar desde
  la carpeta sincronizada de OneDrive en un equipo.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

EXTENSIONES = (".csv",)


@dataclass(frozen=True)
class ArchivoNube:
    item_id: str           # identificador estable del archivo en la fuente
    empresa: str           # nombre de la subcarpeta = empresa en el sistema
    nombre: str
    version: str           # cambia si cambia el contenido (cTag en OneDrive)
    tamano: int | None = None
    modificado_en: datetime | None = None


@dataclass
class Listado:
    archivos: list[ArchivoNube] = field(default_factory=list)
    sueltos: list[str] = field(default_factory=list)          # archivos en la raíz: no se sabe la empresa
    ignorados: list[str] = field(default_factory=list)        # otros formatos dentro de las empresas


class ErrorFuente(RuntimeError):
    """La fuente no está disponible o la configuración es incorrecta."""


# =========================
# Carpeta local
# =========================
class FuenteCarpeta:
    origen = "carpeta"

    def __init__(self, ruta: Path | str):
        self.ruta = Path(ruta)

    def descripcion(self) -> str:
        return str(self.ruta)

    def listar(self) -> Listado:
        if not self.ruta.is_dir():
            raise ErrorFuente(f"No existe la carpeta {self.ruta}")
        r = Listado()
        for p in sorted(self.ruta.iterdir()):
            if p.is_file():
                r.sueltos.append(p.name)
            elif p.is_dir() and not p.name.startswith(("_", ".")):
                for f in sorted(p.iterdir()):
                    if not f.is_file():
                        continue
                    if f.suffix.lower() not in EXTENSIONES:
                        r.ignorados.append(f"{p.name}/{f.name}")
                        continue
                    st = f.stat()
                    r.archivos.append(ArchivoNube(
                        item_id=f"{p.name}/{f.name}", empresa=p.name.strip(), nombre=f.name,
                        version=f"{st.st_size}-{int(st.st_mtime)}", tamano=st.st_size,
                        modificado_en=datetime.fromtimestamp(st.st_mtime),
                    ))
        return r

    def descargar(self, archivo: ArchivoNube, destino: Path) -> Path:
        origen = self.ruta / archivo.empresa / archivo.nombre
        destino.write_bytes(origen.read_bytes())
        return destino


# =========================
# OneDrive empresarial / SharePoint (Microsoft Graph)
# =========================
GRAPH = "https://graph.microsoft.com/v1.0"
LOGIN = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"


SCOPES_DELEGADOS = "Files.Read User.Read offline_access"


@dataclass(frozen=True)
class ConfigOneDrive:
    tenant_id: str
    client_id: str
    client_secret: str | None = None    # con secreto: modo aplicación; sin secreto: modo delegado
    carpeta: str = "AdamoPay_Datos"     # ruta de la carpeta raíz dentro del drive
    usuario: str | None = None          # modo aplicación: dueño del OneDrive (correo)
    drive_id: str | None = None         # modo aplicación: Sites.Selected o un sitio de SharePoint

    @property
    def delegado(self) -> bool:
        return not self.client_secret

    @classmethod
    def desde_entorno(cls) -> "ConfigOneDrive | None":
        """None si la carga automática no está configurada (faltan variables)."""
        v = {k: (os.getenv(k) or "").strip() for k in (
            "TX_ONEDRIVE_TENANT_ID", "TX_ONEDRIVE_CLIENT_ID", "TX_ONEDRIVE_CLIENT_SECRET",
            "TX_ONEDRIVE_USUARIO", "TX_ONEDRIVE_DRIVE_ID", "TX_ONEDRIVE_CARPETA")}
        if not (v["TX_ONEDRIVE_TENANT_ID"] and v["TX_ONEDRIVE_CLIENT_ID"]):
            return None
        # Modo aplicación: necesita saber de quién es el OneDrive
        if v["TX_ONEDRIVE_CLIENT_SECRET"] and not (v["TX_ONEDRIVE_USUARIO"] or v["TX_ONEDRIVE_DRIVE_ID"]):
            return None
        return cls(
            tenant_id=v["TX_ONEDRIVE_TENANT_ID"], client_id=v["TX_ONEDRIVE_CLIENT_ID"],
            client_secret=v["TX_ONEDRIVE_CLIENT_SECRET"] or None,
            carpeta=v["TX_ONEDRIVE_CARPETA"] or "AdamoPay_Datos",
            usuario=v["TX_ONEDRIVE_USUARIO"] or None, drive_id=v["TX_ONEDRIVE_DRIVE_ID"] or None,
        )


# =========================
# Inicio de sesión con código (modo delegado)
# =========================
class ErrorConexion(ErrorFuente):
    """La conexión delegada venció o fue revocada: hay que volver a conectar."""


def iniciar_conexion(cfg: ConfigOneDrive, sesion: requests.Session | None = None) -> dict:
    """
    Pide a Microsoft un código de inicio de sesión. Devuelve user_code,
    verification_uri, device_code, interval y expires_in. El usuario abre la
    dirección, escribe el código e inicia sesión con su cuenta.
    """
    http = sesion or requests.Session()
    r = http.post(f"https://login.microsoftonline.com/{cfg.tenant_id}/oauth2/v2.0/devicecode",
                  data={"client_id": cfg.client_id, "scope": SCOPES_DELEGADOS}, timeout=30)
    if r.status_code != 200:
        raise ErrorFuente(f"Microsoft no entregó el código de inicio de sesión ({r.status_code}): {_error_graph(r)}")
    return r.json()


def completar_conexion(cfg: ConfigOneDrive, device_code: str,
                       sesion: requests.Session | None = None) -> dict | None:
    """
    Una consulta (sin esperar): None si el usuario aún no termina de iniciar
    sesión; si terminó, {"refresh_token", "access_token", "expires_in", "cuenta"}.
    """
    http = sesion or requests.Session()
    r = http.post(LOGIN.format(tenant=cfg.tenant_id), data={
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "client_id": cfg.client_id, "device_code": device_code}, timeout=30)
    try:
        datos = r.json() or {}
    except ValueError:
        datos = {}
    if r.status_code == 200:
        yo = http.get(f"{GRAPH}/me?$select=userPrincipalName,mail",
                      headers={"Authorization": f"Bearer {datos['access_token']}"}, timeout=30)
        cuenta = None
        if yo.status_code == 200:
            info = yo.json()
            cuenta = info.get("userPrincipalName") or info.get("mail")
        return {"refresh_token": datos.get("refresh_token"), "access_token": datos["access_token"],
                "expires_in": int(datos.get("expires_in", 3600)), "cuenta": cuenta}
    error = datos.get("error")
    if error in ("authorization_pending", "slow_down"):
        return None
    if error == "expired_token":
        raise ErrorFuente("El código venció sin que se completara el inicio de sesión. Pida uno nuevo.")
    if error == "authorization_declined":
        raise ErrorFuente("Se rechazó el inicio de sesión.")
    raise ErrorFuente(f"No se pudo completar la conexión: {_error_graph(r)}")


class FuenteOneDrive:
    origen = "onedrive"

    def __init__(self, config: ConfigOneDrive, sesion: requests.Session | None = None, timeout: int = 60,
                 refresh_token: str | None = None, cuenta: str | None = None,
                 al_renovar=None):
        """
        Modo delegado: `refresh_token` del usuario conectado; `al_renovar(nuevo)`
        se llama cada vez que Microsoft entrega uno nuevo (rotan), para guardarlo.
        """
        self.cfg = config
        self.http = sesion or requests.Session()
        self.timeout = timeout
        self._token: str | None = None
        self._token_vence = 0.0
        self._refresh = refresh_token
        self.cuenta = cuenta
        self._al_renovar = al_renovar
        if config.delegado and not refresh_token:
            raise ErrorConexion("OneDrive no está conectado: falta iniciar sesión.")

    def descripcion(self) -> str:
        dueño = self.cuenta or self.cfg.usuario or f"drive {self.cfg.drive_id}"
        return f"OneDrive de {dueño} · /{self.cfg.carpeta.strip('/')}"

    # ---------- autenticación ----------
    def _cabeceras(self) -> dict:
        if not self._token or time.time() > self._token_vence - 60:
            if self.cfg.delegado:
                datos = {"client_id": self.cfg.client_id, "grant_type": "refresh_token",
                         "refresh_token": self._refresh, "scope": SCOPES_DELEGADOS}
            else:
                datos = {"client_id": self.cfg.client_id, "client_secret": self.cfg.client_secret,
                         "scope": "https://graph.microsoft.com/.default", "grant_type": "client_credentials"}
            r = self.http.post(LOGIN.format(tenant=self.cfg.tenant_id), data=datos, timeout=self.timeout)
            if r.status_code != 200:
                if self.cfg.delegado:
                    raise ErrorConexion("La conexión con OneDrive venció o fue revocada; vuelva a conectar. "
                                        f"({_error_graph(r)})")
                raise ErrorFuente(f"Microsoft rechazó las credenciales ({r.status_code}): {_error_graph(r)}")
            respuesta = r.json()
            self._token = respuesta["access_token"]
            self._token_vence = time.time() + int(respuesta.get("expires_in", 3600))
            nuevo = respuesta.get("refresh_token")
            if self.cfg.delegado and nuevo and nuevo != self._refresh:
                self._refresh = nuevo
                if self._al_renovar:
                    self._al_renovar(nuevo)
        return {"Authorization": f"Bearer {self._token}"}

    def _drive(self) -> str:
        if self.cfg.delegado:
            return f"{GRAPH}/me/drive"
        if self.cfg.drive_id:
            return f"{GRAPH}/drives/{quote(self.cfg.drive_id, safe='!')}"
        return f"{GRAPH}/users/{quote(self.cfg.usuario or '', safe='@.')}/drive"

    def _get_todos(self, url: str) -> list[dict]:
        """GET con paginación de Graph (@odata.nextLink)."""
        elementos = []
        while url:
            r = self.http.get(url, headers=self._cabeceras(), timeout=self.timeout)
            if r.status_code == 404:
                raise ErrorFuente(f"No se encontró la carpeta «{self.cfg.carpeta}» en el OneDrive configurado.")
            if r.status_code in (401, 403):
                raise ErrorFuente(f"Sin permiso para leer el OneDrive ({r.status_code}): {_error_graph(r)}")
            if r.status_code != 200:
                raise ErrorFuente(f"Error de Microsoft Graph ({r.status_code}): {_error_graph(r)}")
            datos = r.json()
            elementos += datos.get("value", [])
            url = datos.get("@odata.nextLink")
        return elementos

    # ---------- operaciones ----------
    def listar(self) -> Listado:
        campos = "$select=id,name,folder,file,size,lastModifiedDateTime,cTag,eTag&$top=200"
        ruta = quote(self.cfg.carpeta.strip("/"))
        raiz = self._get_todos(f"{self._drive()}/root:/{ruta}:/children?{campos}")
        r = Listado()
        for item in sorted(raiz, key=lambda i: i.get("name", "").casefold()):
            nombre = item.get("name", "")
            if "folder" not in item:
                r.sueltos.append(nombre)
                continue
            if nombre.startswith(("_", ".")):
                continue   # _descartados y similares
            hijos = self._get_todos(f"{self._drive()}/items/{item['id']}/children?{campos}")
            for h in sorted(hijos, key=lambda i: i.get("name", "").casefold()):
                if "file" not in h:
                    continue
                if not h["name"].lower().endswith(EXTENSIONES):
                    r.ignorados.append(f"{nombre}/{h['name']}")
                    continue
                r.archivos.append(ArchivoNube(
                    item_id=h["id"], empresa=nombre.strip(), nombre=h["name"],
                    version=h.get("cTag") or h.get("eTag") or h.get("lastModifiedDateTime", ""),
                    tamano=h.get("size"), modificado_en=_fecha(h.get("lastModifiedDateTime")),
                ))
        return r

    def descargar(self, archivo: ArchivoNube, destino: Path) -> Path:
        # Graph responde con una redirección a una URL de descarga ya firmada
        r = self.http.get(f"{self._drive()}/items/{archivo.item_id}/content",
                          headers=self._cabeceras(), timeout=self.timeout * 5, allow_redirects=True)
        if r.status_code != 200:
            raise ErrorFuente(f"No se pudo descargar {archivo.empresa}/{archivo.nombre} ({r.status_code})")
        destino.write_bytes(r.content)
        return destino


def _fecha(valor: str | None) -> datetime | None:
    """Fecha de Graph (UTC, ISO 8601) en hora local sin zona, como el resto de la base."""
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
    except ValueError:
        return None


def _error_graph(r: requests.Response) -> str:
    try:
        d = r.json()
        e = d.get("error")
        if isinstance(e, dict):
            return e.get("message") or e.get("code") or str(e)
        return d.get("error_description") or str(e or d)[:200]
    except ValueError:
        return r.text[:200]


def fuente_configurada(engine=None) -> FuenteOneDrive | None:
    """
    La fuente OneDrive lista para usar, o None si falta configuración.
    Modo delegado: además debe haber un usuario conectado (credencial guardada).
    """
    cfg = ConfigOneDrive.desde_entorno()
    if cfg is None:
        return None
    if not cfg.delegado:
        return FuenteOneDrive(cfg)
    from app.monitoreo_tx.nube import credenciales
    if engine is None:
        from db.database import engine as engine_bd
        engine = engine_bd
    guardada = credenciales.leer(engine)
    if guardada is None:
        return None
    return FuenteOneDrive(cfg, refresh_token=guardada["refresh_token"], cuenta=guardada["cuenta"],
                          al_renovar=lambda nuevo: credenciales.renovar(engine, nuevo))


__all__ = ["ArchivoNube", "ConfigOneDrive", "ErrorConexion", "ErrorFuente", "FuenteCarpeta",
           "FuenteOneDrive", "Listado", "completar_conexion", "fuente_configurada", "iniciar_conexion"]
