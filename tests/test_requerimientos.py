"""Requerimientos de compliance (migración 046).

Lo que no puede fallar:
  - consecutivo REQ-AAAA-NNN por organización, sin saltos ni repetidos;
  - se dirige a la organización o a uno de SUS clientes; si lo pide un aliado, debe ser aliado de ESA organización;
  - una organización nunca ve ni toca los requerimientos de otra;
  - «Enviado» exige resumen; cerrar o pasar a seguimiento exige motivo; todo queda en la bitácora;
  - el semáforo de plazo (atrasado, por vencer, fuera de plazo) es correcto;
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
from api.rutas import requerimientos as rr  # noqa: E402
from core.cumplimiento import aliados as ali  # noqa: E402
from core.cumplimiento import clientes as cl  # noqa: E402
from core.cumplimiento import requerimientos as rq  # noqa: E402

HOY = date.today()


def test_permisos():
    externo = seg.Usuario(9, "equipo", "E", "cliente", organizacion_id=1, alcance="organizacion")
    director = seg.Usuario(8, "dir", "D", "director_cumplimiento")
    rutas = [r for r in rr.router.routes if isinstance(r, APIRoute)]
    assert len(rutas) == 11
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
    adamo = id_adamo(engine)
    with engine.begin() as c:
        otra = c.execute(text("INSERT INTO organizaciones (nombre) VALUES ('Paycop') RETURNING id")).scalar_one()
    paxum = cl.crear(engine, adamo, {"razon_social": "Paxum", "nivel_riesgo": "Medio"}, "jorge")
    ajeno = cl.crear(engine, otra, {"razon_social": "Cliente de Paycop", "nit": "900999", "nivel_riesgo": "Bajo"}, "jorge")
    cobre = ali.crear(engine, adamo, {"nombre": "Cobre", "estado": "activo"}, "jorge")
    finity = ali.crear(engine, otra, {"nombre": "Finity", "estado": "activo"}, "jorge")
    yield engine, {"adamo": adamo, "paycop": otra, "paxum": paxum, "ajeno": ajeno, "cobre": cobre, "finity": finity}
    engine.dispose()


def _req(**k):
    base = {"dirigido_a": "organizacion", "origen": "oficial", "tipo": "otro", "asunto": "Actualizar matriz de riesgo",
            "fecha_recibido": HOY - timedelta(days=2)}
    return {**base, **k}


def test_consecutivo_por_organizacion(pg):
    engine, x = pg
    a1 = rq.crear(engine, x["adamo"], _req(), "jorge")
    a2 = rq.crear(engine, x["adamo"], _req(), "jorge")
    p1 = rq.crear(engine, x["paycop"], _req(), "jorge")
    anio = (HOY - timedelta(days=2)).year
    assert (a1["consecutivo"], a2["consecutivo"], p1["consecutivo"]) == (f"REQ-{anio}-001", f"REQ-{anio}-002", f"REQ-{anio}-001")
    q = rq.obtener(engine, x["adamo"], a1["id"])
    assert q["responsable"] == "jorge" and q["estado"] == "recibido" and q["eventos"][0]["tipo"] == "alta"


def test_dirigido_y_origen_validos(pg):
    engine, x = pg
    r = rq.crear(engine, x["adamo"], _req(dirigido_a="cliente", cliente_id=x["paxum"], origen="aliado",
                                          relacion_aliado_id=x["cobre"], tipo="kyc_kyb", asunto="KYC actualizado de Paxum",
                                          referencias_tx=["TX-1", "TX-1", " ", "TX-2"]), "jorge")
    q = rq.obtener(engine, x["adamo"], r["id"])
    assert q["cliente"] == "Paxum" and q["aliado"] == "Cobre" and q["referencias_tx"] == ["TX-1", "TX-2"]
    errores = [
        _req(dirigido_a="cliente"),                                         # sin cliente
        _req(dirigido_a="cliente", cliente_id=x["ajeno"]),                  # cliente de otra organización
        _req(origen="aliado"),                                              # sin aliado
        _req(origen="aliado", relacion_aliado_id=x["finity"]),              # aliado de otra organización
        _req(tipo="inventado"), _req(asunto="x"),
        _req(fecha_recibido=HOY + timedelta(days=1)),
        _req(fecha_limite=HOY - timedelta(days=10)),
        _req(carpeta_evidencias="C:/carpeta"),
    ]
    for datos in errores:
        with pytest.raises(rq.ErrorRequerimiento):
            rq.crear(engine, x["adamo"], datos, "jorge")
    # dirigido a la organización: el cliente se ignora; origen no aliado: el aliado se ignora
    r2 = rq.crear(engine, x["adamo"], _req(cliente_id=x["paxum"], relacion_aliado_id=x["cobre"]), "jorge")
    q2 = rq.obtener(engine, x["adamo"], r2["id"])
    assert q2["cliente_id"] is None and q2["relacion_aliado_id"] is None


def test_aislamiento(pg):
    engine, x = pg
    r = rq.crear(engine, x["adamo"], _req(), "jorge")
    assert rq.listar(engine, x["paycop"])["requerimientos"] == []
    for fn in (lambda: rq.obtener(engine, x["paycop"], r["id"]),
               lambda: rq.actualizar(engine, x["paycop"], r["id"], {"asunto": "Cambiado desde otra"}, "x"),
               lambda: rq.cambiar_estado(engine, x["paycop"], r["id"], "cerrado", "x", comentario="cerrado desde otra org"),
               lambda: rq.agregar_nota(engine, x["paycop"], r["id"], "nota ajena", "x")):
        with pytest.raises(LookupError):
            fn()


def test_flujo_de_estados_y_bitacora(pg):
    engine, x = pg
    r = rq.crear(engine, x["adamo"], _req(fecha_limite=HOY + timedelta(days=5)), "jorge")
    rq.cambiar_estado(engine, x["adamo"], r["id"], "en_preparacion", "jorge")
    with pytest.raises(rq.ErrorRequerimiento):
        rq.cambiar_estado(engine, x["adamo"], r["id"], "enviado", "jorge", resumen_respuesta="corto")
    with pytest.raises(rq.ErrorRequerimiento):
        rq.cambiar_estado(engine, x["adamo"], r["id"], "enviado", "jorge", resumen_respuesta="Se envió la matriz actualizada",
                          fecha_envio=HOY + timedelta(days=1))
    rq.cambiar_estado(engine, x["adamo"], r["id"], "enviado", "jorge", resumen_respuesta="Se envió la matriz actualizada")
    with pytest.raises(rq.ErrorRequerimiento):
        rq.cambiar_estado(engine, x["adamo"], r["id"], "cerrado", "jorge", comentario="ok")
    rq.cambiar_estado(engine, x["adamo"], r["id"], "seguimiento", "jorge", comentario="El banco pidió un anexo adicional")
    rq.agregar_nota(engine, x["adamo"], r["id"], "Se solicitó el anexo al cliente", "jorge")
    cambios = rq.actualizar(engine, x["adamo"], r["id"], {"prioridad": "alta", "asunto": "Actualizar matriz de riesgo"}, "jorge")
    assert cambios == ["prioridad"]
    q = rq.obtener(engine, x["adamo"], r["id"])
    assert q["estado"] == "seguimiento" and q["fecha_envio"] == HOY and q["abierto"]
    assert [e["tipo"] for e in q["eventos"]] == ["edicion", "nota", "estado", "estado", "estado", "alta"]
    with pytest.raises(rq.ErrorRequerimiento):
        rq.cambiar_estado(engine, x["adamo"], r["id"], "seguimiento", "jorge", comentario="ya está en seguimiento")


def test_semaforo_de_plazos(pg):
    engine, x = pg
    hoy = HOY
    atrasado = rq.crear(engine, x["adamo"], _req(fecha_recibido=hoy - timedelta(days=10), fecha_limite=hoy - timedelta(days=1)), "j")
    por_vencer = rq.crear(engine, x["adamo"], _req(fecha_limite=hoy + timedelta(days=2)), "j")
    rq.crear(engine, x["adamo"], _req(fecha_limite=hoy + timedelta(days=20)), "j")
    rq.crear(engine, x["adamo"], _req(), "j")                                                  # sin plazo
    tarde = rq.crear(engine, x["adamo"], _req(fecha_recibido=hoy - timedelta(days=10), fecha_limite=hoy - timedelta(days=5)), "j")
    rq.cambiar_estado(engine, x["adamo"], tarde["id"], "enviado", "j", resumen_respuesta="Se respondió con retraso")
    lista = rq.listar(engine, x["adamo"], hoy)
    plazos = {q["id"]: q["plazo"] for q in lista["requerimientos"]}
    assert plazos[atrasado["id"]] == "atrasado" and plazos[por_vencer["id"]] == "por_vencer"
    assert plazos[tarde["id"]] == "fuera_de_plazo"
    assert lista["resumen"] == {"abiertos": 4, "atrasados": 1, "por_vencer": 1, "fuera_de_plazo": 1, "total": 5,
                                "sin_evidencia_respuesta": 0}
    assert lista["requerimientos"][0]["id"] == atrasado["id"]                       # abiertos y más urgentes primero
    assert lista["requerimientos"][-1]["id"] == tarde["id"]


def test_vistas_por_cliente_y_por_aliado(pg):
    engine, x = pg
    rq.crear(engine, x["adamo"], _req(dirigido_a="cliente", cliente_id=x["paxum"], origen="aliado", relacion_aliado_id=x["cobre"]), "j")
    rq.crear(engine, x["adamo"], _req(origen="aliado", relacion_aliado_id=x["cobre"]), "j")
    rq.crear(engine, x["adamo"], _req(), "j")
    assert len(rq.por_cliente(engine, x["paxum"])) == 1
    assert len(rq.por_aliado(engine, x["adamo"], x["cobre"])) == 2
    assert rq.por_aliado(engine, x["paycop"], x["cobre"]) == []
    op = rq.opciones(engine, x["adamo"])
    assert [c["razon_social"] for c in op["clientes"]] == ["Paxum"] and [a["nombre"] for a in op["aliados"]] == ["Cobre"]
