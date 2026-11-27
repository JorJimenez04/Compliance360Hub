"""Aliados bancarios de cada organización (migración 045).

Lo que no puede fallar:
  - la entidad se registra una vez y cada organización tiene su propia relación con ella;
  - una organización nunca ve ni toca los aliados de otra;
  - estado, riesgo y diligencia exigen motivo y quedan en el historial;
  - solo tres niveles de riesgo;
  - los avisos señalan relaciones vigentes sin diligencia completa o con revisión vencida;
  - el cliente no entra y el director solo consulta.
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

os.environ.setdefault("DATABASE_URL", "postgresql://smoke:smoke@localhost:5432/smoke")
os.environ.setdefault("APP_ENV", "development")

from api import seguridad as seg  # noqa: E402
from api.rutas import aliados as ra  # noqa: E402
from core.cumplimiento import aliados as ali  # noqa: E402


def test_permisos():
    externo = seg.Usuario(9, "equipo", "E", "cliente", organizacion_id=1, alcance="organizacion")
    director = seg.Usuario(8, "dir", "D", "director_cumplimiento")
    rutas = [r for r in ra.router.routes if isinstance(r, APIRoute)]
    assert len(rutas) == 7
    for r in rutas:
        dep = r.dependant.dependencies[-1].call
        with pytest.raises(HTTPException):
            dep(externo)
        if r.methods & {"POST", "PATCH", "DELETE"}:
            with pytest.raises(HTTPException):
                dep(director)
        else:
            assert dep(director) is director


@pytest.fixture
def pg():
    url = os.getenv("TX_TEST_PG_URL")
    if not url:
        pytest.skip("Defina TX_TEST_PG_URL para probar contra PostgreSQL")
    from sqlalchemy import create_engine, text
    from tests._esquema import crear_esquema_minimo, id_adamo
    engine = create_engine(url)
    crear_esquema_minimo(engine)
    with engine.begin() as c:
        otra = c.execute(text("INSERT INTO organizaciones (nombre) VALUES ('Paycop') RETURNING id")).scalar_one()
    yield engine, id_adamo(engine), otra
    engine.dispose()


def test_alta_y_entidad_compartida(pg):
    engine, adamo, paycop = pg
    r1 = ali.crear(engine, adamo, {"nombre": "Cobre", "tipo_entidad": "psp", "pais": "Colombia",
                                   "estado": "activo", "servicios": ["pay_out", "dispersion"], "monedas": ["cop"]}, "jorge")
    r2 = ali.crear(engine, paycop, {"nombre": "cobre", "estado": "prospecto"}, "jorge")   # misma entidad
    a, p = ali.obtener(engine, adamo, r1), ali.obtener(engine, paycop, r2)
    assert a["aliado_id"] == p["aliado_id"] and a["organizaciones"] == 2
    assert a["estado"] == "activo" and p["estado"] == "prospecto"
    assert a["monedas"] == ["COP"] and a["otras_organizaciones"] == [{"nombre": "Paycop", "estado": "prospecto"}]
    assert a["historial"][0]["campo"] == "alta"
    with pytest.raises(ali.ErrorAliado):                       # no se repite en la misma organización
        ali.crear(engine, adamo, {"aliado_id": a["aliado_id"]}, "jorge")
    with pytest.raises(ali.ErrorAliado):
        ali.crear(engine, adamo, {"nombre": "X", "servicios": ["teletransporte"]}, "jorge")
    with pytest.raises(ali.ErrorAliado):
        ali.crear(engine, adamo, {"nombre": "Y", "nivel_riesgo": "Muy Alto"}, "jorge")


def test_aislamiento_por_organizacion(pg):
    engine, adamo, paycop = pg
    rid = ali.crear(engine, adamo, {"nombre": "Iris"}, "jorge")
    assert ali.listar(engine, paycop)["aliados"] == []
    with pytest.raises(LookupError):
        ali.obtener(engine, paycop, rid)
    with pytest.raises(LookupError):
        ali.actualizar(engine, paycop, rid, {"nombre": "Hackeado"}, {})
    with pytest.raises(LookupError):
        ali.cambiar(engine, paycop, rid, {"estado": "terminado", "motivo": "intento desde otra organización"}, "x")


def test_cambios_con_motivo_e_historial(pg):
    engine, adamo, _ = pg
    rid = ali.crear(engine, adamo, {"nombre": "Davivienda", "tipo_entidad": "banco", "estado": "onboarding"}, "jorge")
    with pytest.raises(ali.ErrorAliado):
        ali.cambiar(engine, adamo, rid, {"estado": "activo", "motivo": "ok"}, "jorge")       # motivo muy corto
    hechos = ali.cambiar(engine, adamo, rid, {"estado": "activo", "nivel_riesgo": "Bajo", "dd_estado": "completa",
                                              "proxima_revision": date(2027, 6, 1),
                                              "motivo": "Diligencia revisada y cuenta abierta"}, "jorge")
    assert len(hechos) == 4
    r = ali.obtener(engine, adamo, rid)
    assert r["estado"] == "activo" and r["nivel_riesgo"] == "Bajo" and r["dd_fecha"] == date.today()
    assert {h["campo"] for h in r["historial"]} == {"alta", "estado", "riesgo", "diligencia"}
    with pytest.raises(ali.ErrorAliado):
        ali.cambiar(engine, adamo, rid, {"estado": "activo", "motivo": "sin cambios reales aquí"}, "jorge")


def test_editar_entidad_y_relacion(pg):
    engine, adamo, paycop = pg
    rid = ali.crear(engine, adamo, {"nombre": "PEXTO - Cobre"}, "jorge")
    otro = ali.crear(engine, paycop, {"nombre": "Finity"}, "jorge")
    ali.actualizar(engine, adamo, rid, {"nombre": "Cobre", "razon_social": "PEXTO Colombia S.A.S.", "regulado": False},
                   {"exigencias": ["Recertificación AML anual", " ", "Recertificación AML anual"],
                    "correo_cumplimiento": "cumplimiento@cobre.co"})
    r = ali.obtener(engine, adamo, rid)
    assert r["nombre"] == "Cobre" and r["exigencias"] == ["Recertificación AML anual"]
    with pytest.raises(ali.ErrorAliado):
        ali.actualizar(engine, adamo, rid, {"nombre": "finity"}, {})            # nombre de otra entidad
    with pytest.raises(ali.ErrorAliado):
        ali.actualizar(engine, adamo, rid, {}, {"correo_cumplimiento": "no-es-correo"})
    assert otro


def test_avisos_y_resumen(pg):
    engine, adamo, _ = pg
    hoy = date(2026, 11, 27)
    a = ali.crear(engine, adamo, {"nombre": "Alfa", "estado": "activo"}, "j")                     # sin nada
    b = ali.crear(engine, adamo, {"nombre": "Beta", "estado": "activo", "tipo_entidad": "banco",
                                  "servicios": ["pay_in"], "nivel_riesgo": "Alto"}, "j")
    ali.cambiar(engine, adamo, b, {"dd_estado": "completa", "proxima_revision": hoy - timedelta(days=1),
                                   "motivo": "Revisión anual programada"}, "j")
    ali.crear(engine, adamo, {"nombre": "Gama", "estado": "terminado"}, "j")
    lista = ali.listar(engine, adamo, hoy)
    av = {x["nombre"]: [v["texto"] for v in x["avisos"]] for x in lista["aliados"]}
    assert any("Debida diligencia no iniciada" in t for t in av["Alfa"]) and "Sin calificación de riesgo" in av["Alfa"]
    assert any("Revisión vencida" in t for t in av["Beta"]) and not any("Debida" in t for t in av["Beta"])
    assert av["Gama"] == []
    assert lista["resumen"] == {"total": 3, "activos": 2, "diligencia_pendiente": 1, "revision_vencida": 1, "riesgo_alto": 1}
    assert [x["nombre"] for x in lista["aliados"]][-1] == "Gama"                                  # terminados al final
    assert a
