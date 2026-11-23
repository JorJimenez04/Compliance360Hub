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


# ---------- Ficha y paquete de vinculación (migración 039) ----------
def test_ficha_valida_contra_el_catalogo(pg):
    from api.rutas import organizaciones as ro2
    org = ro.crear(ro.NuevaOrganizacion(nombre="Cliente Nuevo"), _Peticion(), JEFE)["id"]
    malos = [{"servicios": ["inventado"]}, {"modelos_negocio": ["nada"]}, {"regimen": "x"},
             {"nivel_riesgo": "Muy Alto"}, {"tipo_persona": "mixta"}]
    for cambio in malos:
        with pytest.raises(HTTPException) as e:
            ro.cambiar(org, ro.CambioOrganizacion(**cambio), _Peticion(), JEFE)
        assert e.value.status_code == 400
    assert ro2.ficha(org, ANA)["nivel_riesgo"] == "Sin calificar"


def test_ficha_completa_y_paquete(pg):
    from sqlalchemy import text
    engine, _ = pg
    with engine.begin() as c:
        jefe_id = c.execute(text("INSERT INTO usuarios (username, nombre_completo, rol) "
                                 "VALUES ('jorge', 'Jorge Jiménez', 'super_admin') RETURNING id")).scalar_one()
    org = ro.crear(ro.NuevaOrganizacion(nombre="Exchange SAS"), _Peticion(), JEFE)["id"]
    ro.cambiar(org, ro.CambioOrganizacion(
        servicios=["kyc_kyb", "monitoreo_cripto", "oficial_cumplimiento"], modelos_negocio=["exchange_cripto"],
        regimen="psav", oficial_principal_id=jefe_id, oficial_suplente="Ana Pérez · CC 123",
        fecha_designacion="2026-11-01", acta_designacion="Acta 15 de junta"), _Peticion(), JEFE)
    f = ro.ficha(org, ANA)
    assert f["servicios"] == ["kyc_kyb", "monitoreo_cripto", "oficial_cumplimiento"]
    assert f["oficial_principal"] == "Jorge Jiménez" and f["fecha_designacion"] == "2026-11-01"
    assert f["riesgo_sugerido"] == "Alto" and f["monitoreo_sugerido"] == ["fiat", "cripto"]
    p = ro.paquete_organizacion(org, ANA)
    assert p["nivel_es_provisional"] is True and p["nivel"] == "Alto"       # sin calificar: usa el sugerido
    assert "Transacciones con activos virtuales (mensual)" in p["regimen"]["reportes_uiaf"]
    assert {"wallets_declaradas", "reporte_kyt"} <= {d["codigo"] for d in p["documentos"]}
    ro.cambiar(org, ro.CambioOrganizacion(nivel_riesgo="Medio"), _Peticion(), JEFE)
    assert ro.paquete_organizacion(org, ANA)["nivel_es_provisional"] is False


def test_el_oficial_debe_ser_del_equipo_interno(pg):
    from sqlalchemy import text
    engine, _ = pg
    with engine.begin() as c:
        ext = c.execute(text("INSERT INTO usuarios (username, rol, organizacion_id) "
                             "SELECT 'ceo', 'junta', id FROM organizaciones WHERE nombre = 'Adamo' RETURNING id")).scalar_one()
    adamo = next(o["id"] for o in ro.listar(ANA)["organizaciones"] if o["nombre"] == "Adamo")
    for candidato in (ext, 999999):
        with pytest.raises(HTTPException) as e:
            ro.cambiar(adamo, ro.CambioOrganizacion(oficial_principal_id=candidato), _Peticion(), JEFE)
        assert e.value.status_code == 400


def test_paquete_de_prospecto():
    p = ro.paquete_prospecto(modelos=["comercio_general"], nivel=None, tipo_persona="juridica", regimen=None, u=ANA)
    assert p["nivel"] == "Bajo" and p["documentos"]
    with pytest.raises(HTTPException):
        ro.paquete_prospecto(modelos=["no_existe"], nivel=None, tipo_persona="juridica", regimen=None, u=ANA)


def test_la_ficha_y_el_catalogo_son_internos():
    for ruta in ("/api/organizaciones/{organizacion_id}", "/api/organizaciones/{organizacion_id}/paquete"):
        dep = _dep(ruta, "GET")
        with pytest.raises(HTTPException):
            dep(seg.Usuario(9, "c", "C", "cliente", organizacion_id=1, alcance="organizacion"))
    for r in ro.router_catalogo.routes:
        dep = r.dependant.dependencies[-1].call
        with pytest.raises(HTTPException):
            dep(seg.Usuario(9, "j", "J", "junta", organizacion_id=1))
