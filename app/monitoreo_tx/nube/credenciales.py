"""
Credencial de la conexión delegada con OneDrive.

Se guarda el refresh token del usuario que se conectó, cifrado (Fernet) con
una clave derivada de SECRET_KEY (o TX_ONEDRIVE_CLAVE si se define). Quien
lea la base sin la clave no obtiene un token utilizable. Si la clave cambia,
el token deja de poder leerse y hay que volver a conectar.

Microsoft entrega un refresh token nuevo en cada renovación: se reemplaza el
guardado, así la conexión se mantiene viva mientras la revisión programada
se ejecute (los refresh tokens vencen tras 90 días sin uso).
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from datetime import datetime

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Engine, delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.monitoreo_tx.tablas import tx_credenciales_nube

logger = logging.getLogger(__name__)

C = tx_credenciales_nube.c
ORIGEN = "onedrive"


class SinClave(RuntimeError):
    pass


def _fernet() -> Fernet:
    clave = (os.getenv("TX_ONEDRIVE_CLAVE") or os.getenv("SECRET_KEY") or "").strip()
    if len(clave) < 16:
        raise SinClave("Falta SECRET_KEY (o TX_ONEDRIVE_CLAVE) en el servidor para cifrar la conexión.")
    derivada = hashlib.sha256(("compliance360-onedrive:" + clave).encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(derivada))


def guardar(engine: Engine, refresh_token: str, cuenta: str | None, conectado_por: str) -> None:
    ahora = datetime.now()
    cifrado = _fernet().encrypt(refresh_token.encode("utf-8")).decode("ascii")
    stmt = pg_insert(tx_credenciales_nube).values(
        origen=ORIGEN, cuenta=cuenta, token_cifrado=cifrado, conectado_por=conectado_por,
        conectado_en=ahora, renovado_en=ahora)
    stmt = stmt.on_conflict_do_update(index_elements=["origen"], set_={
        "cuenta": stmt.excluded.cuenta, "token_cifrado": stmt.excluded.token_cifrado,
        "conectado_por": stmt.excluded.conectado_por, "conectado_en": stmt.excluded.conectado_en,
        "renovado_en": stmt.excluded.renovado_en})
    with engine.begin() as conn:
        conn.execute(stmt)


def leer(engine: Engine) -> dict | None:
    """{"refresh_token", "cuenta", "conectado_por", "conectado_en", "renovado_en"} o None."""
    with engine.connect() as conn:
        fila = conn.execute(select(tx_credenciales_nube).where(C.origen == ORIGEN)).mappings().first()
    if fila is None:
        return None
    try:
        token = _fernet().decrypt(fila["token_cifrado"].encode("ascii")).decode("utf-8")
    except (InvalidToken, SinClave):
        logger.warning("La credencial de OneDrive no se puede descifrar (¿cambió SECRET_KEY?); reconecte.")
        return None
    return {"refresh_token": token, "cuenta": fila["cuenta"], "conectado_por": fila["conectado_por"],
            "conectado_en": fila["conectado_en"], "renovado_en": fila["renovado_en"]}


def info(engine: Engine) -> dict | None:
    """Datos de la conexión para mostrar, sin el token (y sin necesitar la clave)."""
    with engine.connect() as conn:
        fila = conn.execute(select(C.cuenta, C.conectado_por, C.conectado_en, C.renovado_en)
                            .where(C.origen == ORIGEN)).mappings().first()
    return dict(fila) if fila else None


def renovar(engine: Engine, refresh_token: str) -> None:
    cifrado = _fernet().encrypt(refresh_token.encode("utf-8")).decode("ascii")
    with engine.begin() as conn:
        conn.execute(update(tx_credenciales_nube).where(C.origen == ORIGEN)
                     .values(token_cifrado=cifrado, renovado_en=datetime.now()))


def eliminar(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(delete(tx_credenciales_nube).where(C.origen == ORIGEN))
