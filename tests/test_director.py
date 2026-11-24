"""Perfil «director_cumplimiento» (migración 043, decisión 2026-11-24).

Responsable del compliance de todo el grupo: interno, sin organización, ve todas las
organizaciones y TODO en solo lectura. Lo que no puede fallar:
  - entra a toda ruta de consulta interna y a ninguna que modifique datos;
  - solo el super_admin lo crea, y nunca con organización;
  - la app anterior (Streamlit) no lo deja entrar.
"""

from __future__ import annotations

import os

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

os.environ.setdefault("DATABASE_URL", "postgresql://smoke:smoke@localhost:5432/smoke")
os.environ.setdefault("APP_ENV", "development")

from api import seguridad as seg  # noqa: E402
from api.rutas import clientes, monitoreo, organizaciones, usuarios  # noqa: E402
from core.monitoreo_tx.config import ROLES_CARGA, ROLES_MONITOREO, ROL_DIRECTOR  # noqa: E402

DIRECTOR = seg.Usuario(7, "director", "Director", ROL_DIRECTOR)


def test_rol_de_solo_lectura():
    assert ROL_DIRECTOR in ROLES_MONITOREO and ROL_DIRECTOR not in ROLES_CARGA
    assert not DIRECTOR.externo


def _rutas():
    for modulo in (clientes, monitoreo, organizaciones, usuarios):
        for r in modulo.router.routes:
            if not isinstance(r, APIRoute):
                continue
            for d in r.dependant.dependencies:
                if getattr(d.call, "__name__", "") == "_dep":
                    yield r, d.call


# Consultas que solo existen para gestionar (la pestaña «Empresas» de Monitoreo, donde se enlazan
# empresas con clientes): el director no tiene esa pantalla.
SOLO_GESTION = {"/api/monitoreo/empresas"}


def test_lee_todo_y_no_modifica_nada():
    leidas = escritas = 0
    for r, dep in _rutas():
        escribe = bool(r.methods & {"POST", "PATCH", "PUT", "DELETE"}) or r.path in SOLO_GESTION
        if escribe:
            with pytest.raises(HTTPException) as e:
                dep(DIRECTOR)
            assert e.value.status_code == 403, r.path
            escritas += 1
        elif not r.path.startswith("/api/usuarios"):
            assert dep(DIRECTOR) is DIRECTOR, r.path
            leidas += 1
    assert leidas > 15 and escritas > 15


def test_menu_del_director():
    mods = seg.modulos_visibles(ROL_DIRECTOR)
    assert {"monitoreo", "organizaciones", "catalogo"} <= set(mods)
    assert "usuarios" not in mods and "junta" not in mods
    assert "organizaciones" in seg.modulos_visibles("compliance")
    assert "organizaciones" not in seg.modulos_visibles("cliente")


def test_reglas_de_alta():
    usuarios._reglas_de_perfil(ROL_DIRECTOR, None, None, [])
    with pytest.raises(HTTPException):
        usuarios._reglas_de_perfil(ROL_DIRECTOR, 1, None, [])          # no pertenece a una organización
    with pytest.raises(HTTPException):
        usuarios._reglas_de_perfil(ROL_DIRECTOR, None, "organizacion", [])


def test_la_app_anterior_no_lo_deja_entrar():
    fuente = open("app/auth/login.py", encoding="utf-8").read()
    assert fuente.count('"director_cumplimiento"') >= 2


def test_la_base_acepta_el_rol_y_lo_exige_sin_organizacion():
    url = os.getenv("TX_TEST_PG_URL")
    if not url:
        pytest.skip("Defina TX_TEST_PG_URL para probar contra PostgreSQL")
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import IntegrityError
    from tests._esquema import crear_esquema_minimo
    engine = create_engine(url)
    crear_esquema_minimo(engine)
    with engine.begin() as c:
        c.execute(text("INSERT INTO usuarios (username, nombre_completo, rol, password_hash, activo) "
                       "VALUES ('dir', 'Director', 'director_cumplimiento', 'x', 1)"))
    with pytest.raises(IntegrityError), engine.begin() as c:
        c.execute(text("INSERT INTO usuarios (username, nombre_completo, rol, password_hash, activo, organizacion_id) "
                       "SELECT 'dir2', 'Director', 'director_cumplimiento', 'x', 1, id FROM organizaciones LIMIT 1"))
    engine.dispose()
