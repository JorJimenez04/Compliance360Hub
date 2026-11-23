"""Organizaciones (migración 038): solo el super_admin las crea o cambia; un usuario
externo solo ve la suya y nunca sabe qué otras existen.

Las pruebas con base usan PostgreSQL real (TX_TEST_PG_URL, se vacía); el resto corre sin base.
"""

from __future__ import annotations

import os

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

os.environ.setdefault("DATABASE_URL", "postgresql://smoke:smoke@localhost:5432/smoke")
os.environ.setdefault("APP_ENV", "development")

from api import seguridad as seg  # noqa: E402
from api.rutas import organizaciones as ro  # noqa: E402

JEFE = seg.Usuario(1, "jefe", "Jefe", "super_admin")
ANA = seg.Usuario(2, "ana", "Ana", "compliance")


def _dep(ruta: str, metodo: str):
    for r in ro.router.routes:
        if isinstance(r, APIRoute) and r.path == ruta and metodo in r.methods:
            return r.dependant.dependencies[-1].call
    raise AssertionError(f"Falta la ruta {metodo} {ruta}")


@pytest.mark.parametrize("ruta, metodo", [("/api/organizaciones", "POST"),
                                          ("/api/organizaciones/{organizacion_id}", "PATCH")])
@pytest.mark.parametrize("rol", ["admin", "compliance", "cliente", "junta"])
def test_crear_y_cambiar_es_solo_del_super_admin(ruta, metodo, rol):
    with pytest.raises(HTTPException) as e:
        _dep(ruta, metodo)(seg.Usuario(5, "x", "X", rol, organizacion_id=1 if rol in ("cliente", "junta") else None,
                                       alcance="organizacion" if rol == "cliente" else None))
    assert e.value.status_code == 403
    assert _dep(ruta, metodo)(JEFE) is JEFE


def test_el_menu_de_organizaciones_es_del_super_admin():
    assert "organizaciones" in seg.modulos_visibles("super_admin")


def test_un_rol_sin_monitoreo_no_lista_organizaciones():
    with pytest.raises(HTTPException) as e:
        ro.listar(seg.Usuario(5, "x", "X", "comercial"))
    assert e.value.status_code == 403


# ---------- Contra PostgreSQL ----------
class _Peticion:
    headers: dict = {}
    client = None


@pytest.fixture
def pg(monkeypatch):
    url = os.getenv("TX_TEST_PG_URL")
    if not url:
        pytest.skip("Defina TX_TEST_PG_URL para probar contra PostgreSQL")
    from sqlalchemy import create_engine
    import db.database as bd
    from tests._esquema import crear_esquema_minimo
    engine = create_engine(url)
    crear_esquema_minimo(engine)
    monkeypatch.setattr(bd, "engine", engine)
    registros = []
    monkeypatch.setattr(seg, "auditar", lambda *a, **k: registros.append((a, k)))
    yield engine, registros
    engine.dispose()


def test_crear_listar_y_cambiar(pg):
    engine, registros = pg
    nueva = ro.crear(ro.NuevaOrganizacion(nombre="  CM Grupo Tecno ", nit="901000"), _Peticion(), JEFE)
    assert nueva["nombre"] == "CM Grupo Tecno"
    lista = {o["nombre"]: o for o in ro.listar(ANA)["organizaciones"]}
    assert set(lista) == {"Adamo", "CM Grupo Tecno"} and lista["CM Grupo Tecno"]["activa"] is True
    ro.cambiar(nueva["id"], ro.CambioOrganizacion(activa=False, notas="Pausa"), _Peticion(), JEFE)
    lista = {o["nombre"]: o for o in ro.listar(ANA)["organizaciones"]}
    assert lista["CM Grupo Tecno"]["activa"] is False and lista["CM Grupo Tecno"]["notas"] == "Pausa"
    assert [r[0][1] for r in registros] == ["CREATE", "UPDATE"]


@pytest.mark.parametrize("repetida", [{"nombre": "ADAMO"}, {"nombre": "Nueva", "nit": "901000"}])
def test_nombre_o_nit_repetido_responde_409(pg, repetida):
    ro.crear(ro.NuevaOrganizacion(nombre="Con NIT", nit="901000"), _Peticion(), JEFE)
    with pytest.raises(HTTPException) as e:
        ro.crear(ro.NuevaOrganizacion(**repetida), _Peticion(), JEFE)
    assert e.value.status_code == 409


def test_cambiar_una_inexistente_responde_404(pg):
    with pytest.raises(HTTPException) as e:
        ro.cambiar(999999, ro.CambioOrganizacion(activa=False), _Peticion(), JEFE)
    assert e.value.status_code == 404


def test_el_externo_solo_ve_la_suya(pg):
    otra = ro.crear(ro.NuevaOrganizacion(nombre="Otra"), _Peticion(), JEFE)["id"]
    externo = seg.Usuario(9, "ceo", "CEO", "junta", organizacion_id=otra)
    assert ro.listar(externo)["organizaciones"] == [{"id": otra, "nombre": "Otra"}]
