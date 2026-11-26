"""Consulta del log de auditoría (migrada de la app anterior).

Equipo interno (super_admin, compliance y director de cumplimiento): solo lectura.
El log es inmutable: aquí no hay rutas que escriban.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from api import seguridad as seg
from core.monitoreo_tx.config import ROLES_MONITOREO

router = APIRouter(prefix="/api/auditoria", tags=["auditoria"])
interno = seg.requiere_roles(ROLES_MONITOREO)


@router.get("")
def consultar(usuario: str | None = None, entidad: str | None = None, accion: str | None = None,
              resultado: str | None = None, texto: str | None = Query(None, max_length=100),
              desde: date | None = None, hasta: date | None = None,
              pagina: int = Query(1, ge=1), tamano: int = Query(50, ge=10, le=200),
              u: seg.Usuario = Depends(interno)) -> dict:
    from db.database import engine
    condiciones, p = [], {}
    for campo, valor in (("username", usuario), ("entidad", entidad), ("accion", accion), ("resultado", resultado)):
        if valor:
            condiciones.append(f"{campo} = :{campo}")
            p[campo] = valor
    if texto:
        condiciones.append("descripcion ILIKE :texto")
        p["texto"] = f"%{texto.strip()}%"
    if desde:
        condiciones.append("created_at >= :desde")
        p["desde"] = desde
    if hasta:
        condiciones.append("created_at < :hasta")
        p["hasta"] = hasta + timedelta(days=1)
    donde = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
    with engine.connect() as conn:
        total = conn.scalar(text(f"SELECT count(*) FROM log_auditoria {donde}"), p)
        filas = conn.execute(text(
            f"SELECT id, created_at, username, accion, entidad, entidad_id, descripcion, resultado, ip_address "
            f"FROM log_auditoria {donde} ORDER BY created_at DESC, id DESC LIMIT :lim OFFSET :off"),
            {**p, "lim": tamano, "off": (pagina - 1) * tamano}).mappings().all()
        opciones = {
            "usuarios": list(conn.scalars(text("SELECT DISTINCT username FROM log_auditoria ORDER BY 1"))),
            "entidades": list(conn.scalars(text("SELECT DISTINCT entidad FROM log_auditoria ORDER BY 1"))),
            "acciones": list(conn.scalars(text("SELECT DISTINCT accion FROM log_auditoria ORDER BY 1"))),
        }
    if pagina == 1:                     # quién consulta el log también queda registrado (una vez por búsqueda)
        seg.auditar(u, "READ", "log_auditoria", "Consulta del log de auditoría")
    return {"total": total, "pagina": pagina, "tamano": tamano, "opciones": opciones,
            "registros": [{**dict(f), "created_at": f["created_at"].isoformat()} for f in filas]}
