"""Personas vinculadas, contratos y calificación de riesgo (migrados de la app anterior).

Lo que no puede fallar:
  - los accionistas no suman más del 100 %;
  - cada cambio de nivel de riesgo queda en el historial, venga de donde venga;
  - una calificación exige motivo y usa tres niveles;
  - un contrato por empresa del grupo, con sus servicios activos o terminados;
  - el equipo externo y el director no modifican nada.
"""

from __future__ import annotations

import os

import pytest
from fastapi import HTTPException

os.environ.setdefault("DATABASE_URL", "postgresql://smoke:smoke@localhost:5432/smoke")
os.environ.setdefault("APP_ENV", "development")

from api import seguridad as seg  # noqa: E402
from api.rutas import clientes as rc  # noqa: E402
from core.cumplimiento import clientes as cl  # noqa: E402
from core.cumplimiento import vinculados as vc  # noqa: E402

RUTAS = ("/personas", "/contratos", "/riesgo", "/documentos-anteriores")


def test_permisos():
    externo = seg.Usuario(9, "equipo", "E", "cliente", organizacion_id=1, alcance="organizacion")
    director = seg.Usuario(8, "dir", "D", "director_cumplimiento")
    for r in rc.router.routes:
        if not any(x in r.path for x in RUTAS):
            continue
        dep = r.dependant.dependencies[-1].call
        with pytest.raises(HTTPException):
            dep(externo)
        if r.methods & {"POST", "PATCH"}:
            with pytest.raises(HTTPException):
                dep(director)
        else:
            assert dep(director) is director


@pytest.fixture
def pg():
    url = os.getenv("TX_TEST_PG_URL")
    if not url:
        pytest.skip("Defina TX_TEST_PG_URL para probar contra PostgreSQL")
    from sqlalchemy import create_engine
    from tests._esquema import crear_esquema_minimo, id_adamo
    engine = create_engine(url)
    crear_esquema_minimo(engine)
    cid = cl.crear(engine, id_adamo(engine), {"razon_social": "CM Grupo Tecno", "nivel_riesgo": "Medio"}, "ana")
    yield engine, cid
    engine.dispose()


def test_personas_y_participacion(pg):
    engine, cid = pg
    a = vc.crear_persona(engine, cid, {"nombre_completo": "Ana Pérez", "rol": "Accionista", "pct_participacion": 60,
                                       "tipo_documento": "CC", "numero_documento": "123"}, "ana")
    vc.crear_persona(engine, cid, {"nombre_completo": "Luis Gómez", "rol": "Accionista", "pct_participacion": 40,
                                   "es_pep": True}, "ana")
    with pytest.raises(vc.ErrorVinculado, match="sumarían"):
        vc.crear_persona(engine, cid, {"nombre_completo": "Otro Socio", "rol": "Accionista", "pct_participacion": 1}, "ana")
    vc.crear_persona(engine, cid, {"nombre_completo": "Rep Legal", "rol": "Representante Legal"}, "ana")
    with pytest.raises(vc.ErrorVinculado):
        vc.crear_persona(engine, cid, {"nombre_completo": "X", "rol": "Accionista"}, "ana")
    with pytest.raises(vc.ErrorVinculado):
        vc.crear_persona(engine, cid, {"nombre_completo": "Sin Rol Valido", "rol": "Jefe"}, "ana")
    r = vc.resumen_personas(vc.listar_personas(engine, cid))
    assert r == {"total": 3, "pep": 1, "en_listas": 0, "participacion_accionistas": 100.0,
                 "tiene_representante": True, "tiene_beneficiario_final": False}
    # Retirar a un accionista libera su participación
    vc.actualizar_persona(engine, cid, a, {"activo": False})
    assert vc.resumen_personas(vc.listar_personas(engine, cid))["participacion_accionistas"] == 40.0
    assert len(vc.listar_personas(engine, cid)) == 2 and len(vc.listar_personas(engine, cid, incluir_inactivas=True)) == 3
    with pytest.raises(LookupError):
        vc.actualizar_persona(engine, cid, 99999, {"notas": "x"})


def test_contratos_y_servicios(pg):
    engine, cid = pg
    vc.guardar_contrato(engine, cid, "Adamo Services", {"estado": "Activo", "fecha_inicio": "2026-01-01",
                        "fecha_vencimiento": "2027-01-01", "contrato_firmado": True,
                        "servicios": ["Dispersión", "Compliance 360"]}, "ana")
    vc.guardar_contrato(engine, cid, "Adamo Services", {"servicios": ["Dispersión"]}, "ana")   # mismo contrato
    c = vc.listar_contratos(engine, cid)
    assert len(c) == 1 and c[0]["estado"] == "Activo" and c[0]["contrato_firmado"] is True
    assert {(s["servicio"], s["estado"]) for s in c[0]["servicios"]} == {("Dispersión", "Activo"), ("Compliance 360", "Terminado")}
    assert c[0]["dias_para_vencer"] is not None
    with pytest.raises(vc.ErrorVinculado):
        vc.guardar_contrato(engine, cid, "Otra SAS", {}, "ana")
    with pytest.raises(vc.ErrorVinculado):
        vc.guardar_contrato(engine, cid, "Paycop", {"fecha_inicio": "2026-05-01", "fecha_vencimiento": "2026-01-01"}, "ana")
    with pytest.raises(vc.ErrorVinculado):
        vc.guardar_contrato(engine, cid, "Paycop", {"servicios": ["Otro"]}, "ana")


def test_todo_cambio_de_riesgo_queda_en_el_historial(pg):
    engine, cid = pg
    h = vc.historial_riesgo(engine, cid)
    assert len(h) == 1 and h[0]["nivel_nuevo"] == "Medio" and "inicial" in h[0]["motivo"]
    cl.actualizar(engine, cid, {"nivel_riesgo": "Alto"}, "ana")             # desde la ficha
    cl.actualizar(engine, cid, {"nivel_riesgo": "Alto", "notas": "x"}, "ana")   # sin cambio de nivel: no registra
    vc.calificar(engine, cid, "Bajo", 25, "Revisión anual con soportes completos", None, "jefe", None)
    h = vc.historial_riesgo(engine, cid)
    assert [x["nivel_nuevo"] for x in h] == ["Bajo", "Alto", "Medio"]
    assert h[0]["nivel_anterior"] == "Alto" and h[0]["puntaje_nuevo"] == 25 and h[0]["registrado_por"] == "jefe"
    f = cl.obtener(engine, cid)
    assert f["nivel_riesgo"] == "Bajo" and f["puntaje_riesgo"] == 25
    with pytest.raises(vc.ErrorVinculado, match="motivo"):
        vc.calificar(engine, cid, "Alto", None, "corto", None, "jefe", None)
    with pytest.raises(vc.ErrorVinculado, match="Nivel"):
        vc.calificar(engine, cid, "Muy Alto", None, "Motivo suficientemente largo", None, "jefe", None)


def test_documentos_anteriores(pg):
    from sqlalchemy import text
    engine, cid = pg
    assert vc.documentos_anteriores(engine, cid) == []
    with engine.begin() as c:
        c.execute(text("INSERT INTO cliente_documentos (cliente_id, titulo, carpeta, url) "
                       "VALUES (:c, 'RUT 2025', 'Onboarding', 'https://x')"), {"c": cid})
    assert [d["titulo"] for d in vc.documentos_anteriores(engine, cid)] == ["RUT 2025"]
