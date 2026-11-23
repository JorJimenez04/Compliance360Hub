"""Clientes de la organización y alertas del monitoreo (migración 040).

Lo que no puede fallar:
  - el compliance de los clientes (ficha, alertas, casos) es solo del equipo interno;
  - una alerta por empresa, regla y mes: reevaluar no duplica ni borra decisiones;
  - descartar, escalar o marcar posible ROS exige justificación y deja traza inmutable.

Las pruebas con base usan PostgreSQL real (TX_TEST_PG_URL, se vacía).
"""

from __future__ import annotations

import os

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

os.environ.setdefault("DATABASE_URL", "postgresql://smoke:smoke@localhost:5432/smoke")
os.environ.setdefault("APP_ENV", "development")

from api import seguridad as seg  # noqa: E402
from api.rutas import clientes as rc  # noqa: E402
from core.cumplimiento import alertas as al  # noqa: E402
from core.cumplimiento import clientes as cl  # noqa: E402

EXTERNOS = [seg.Usuario(9, "equipo", "E", "cliente", organizacion_id=1, alcance="organizacion"),
            seg.Usuario(8, "ceo", "C", "junta", organizacion_id=1)]


@pytest.mark.parametrize("u", EXTERNOS, ids=["cliente", "junta"])
def test_ninguna_ruta_de_compliance_llega_a_un_externo(u):
    for r in rc.router.routes:
        assert isinstance(r, APIRoute)
        dep = r.dependant.dependencies[-1].call
        with pytest.raises(HTTPException) as e:
            dep(u)
        assert e.value.status_code == 403, r.path


def test_transiciones_coherentes():
    assert set(al.TRANSICIONES) == set(al.ESTADOS)
    assert al.TRANSICIONES["posible_ros"] == set()
    for destinos in al.TRANSICIONES.values():
        assert destinos <= set(al.ESTADOS)


def test_meses_calendario():
    from datetime import date
    assert al._meses(date(2026, 3, 15), 3) == [(date(2026, 1, 1), date(2026, 1, 31)),
                                              (date(2026, 2, 1), date(2026, 2, 28)),
                                              (date(2026, 3, 1), date(2026, 3, 31))]


# ---------- Contra PostgreSQL ----------
@pytest.fixture
def pg(tmp_path):
    url = os.getenv("TX_TEST_PG_URL")
    if not url:
        pytest.skip("Defina TX_TEST_PG_URL para probar contra PostgreSQL")
    import pandas as pd
    from sqlalchemy import create_engine, text
    from core.monitoreo_tx.etl.sync import sincronizar
    from tests._esquema import crear_esquema_minimo
    from tests.test_monitoreo_tx import COLS, _fila
    engine = create_engine(url)
    crear_esquema_minimo(engine)
    ruta = tmp_path / "r.xlsx"
    with pd.ExcelWriter(ruta) as w:
        pd.DataFrame([_fila(i, f"a-{i}", 1_000_000) for i in range(1, 6)], columns=COLS).to_excel(w, sheet_name="CM GRUPO TECNO", index=False)
        pd.DataFrame([_fila(1, "b-1", 7_000)], columns=COLS).to_excel(w, sheet_name="PAXUM", index=False)
    sincronizar(ruta, engine, directorio_logs=tmp_path)
    with engine.begin() as c:
        adamo = c.execute(text("SELECT id FROM organizaciones WHERE nombre = 'Adamo'")).scalar_one()
        c.execute(text("INSERT INTO usuarios (username, nombre_completo, rol) VALUES ('ana', 'Ana', 'compliance')"))
    yield engine, adamo
    engine.dispose()


def _ids(engine):
    from sqlalchemy import text
    with engine.connect() as c:
        return {n: i for i, n in c.execute(text("SELECT id, nombre_reporte FROM tx_empresas"))}


def test_crear_clientes_desde_empresas_y_ficha(pg):
    engine, adamo = pg
    ids = _ids(engine)
    assert {e["nombre"] for e in cl.empresas_sin_cliente(engine, adamo)} == {"CM GRUPO TECNO", "PAXUM"}
    creados = cl.crear_desde_empresas(engine, adamo, list(ids.values()), "ana")
    assert len(creados) == 2 and cl.empresas_sin_cliente(engine, adamo) == []
    with pytest.raises(cl.ErrorCliente):                       # ya enlazadas: todo o nada
        cl.crear_desde_empresas(engine, adamo, [ids["PAXUM"]], "ana")
    cm = next(c for c in cl.listar(engine, adamo) if c["razon_social"] == "CM GRUPO TECNO")
    assert cm["estado"] == "Activo" and cm["empresas"][0]["nombre"] == "CM GRUPO TECNO"
    f = cl.actualizar(engine, cm["id"], {"nit": "901.234.567-8", "modelos_negocio": ["dispersion_pagos"],
                                         "nivel_riesgo": "Alto", "perfil_volumen_mensual": 1_000_000})
    assert f["nit"] == "901.234.567-8" and f["perfil_actualizado"] is not None
    for malo in ({"nivel_riesgo": "Muy Alto"}, {"modelos_negocio": ["x"]}, {"razon_social": " "}, {"estado": "Raro"}):
        with pytest.raises(cl.ErrorCliente):
            cl.actualizar(engine, cm["id"], malo)
    r = cl.resumen_operacion(engine, cm["id"])
    assert r["kpis"].monto_pagado == 5_000_000
    p = cl.perfil_vs_real(engine, cm["id"])
    assert p["meses"][-1]["desv_volumen"] == pytest.approx(5.0)


def test_otra_organizacion_no_toma_empresas_ajenas(pg):
    from sqlalchemy import text
    engine, adamo = pg
    with engine.begin() as c:
        otra = c.execute(text("INSERT INTO organizaciones (nombre) VALUES ('Otra') RETURNING id")).scalar_one()
    with pytest.raises(cl.ErrorCliente):
        cl.crear_desde_empresas(engine, otra, list(_ids(engine).values()), "ana")


def test_alertas_un_registro_por_empresa_regla_y_mes(pg):
    engine, adamo = pg
    ids = _ids(engine)
    cm_id = cl.crear_desde_empresas(engine, adamo, [ids["CM GRUPO TECNO"]], "ana")[0]["id"]
    cl.actualizar(engine, cm_id, {"perfil_volumen_mensual": 1_000_000, "perfil_operaciones_mes": 1})
    r1 = al.evaluar(engine, [ids["CM GRUPO TECNO"]])
    assert r1.nuevas >= 2                                       # PERF-VOL y PERF-OPS
    r2 = al.evaluar(engine, [ids["CM GRUPO TECNO"]])
    assert r2.nuevas == 0 and r2.actualizadas == r1.nuevas      # sin duplicados
    lista = al.listar(engine, adamo, cliente_id=cm_id)
    reglas = {a["regla"] for a in lista}
    assert {"PERF-VOL", "PERF-OPS"} <= reglas and all(a["estado"] == "nueva" for a in lista)
    assert all(a["fecha_limite"] is not None for a in lista)


def test_gestion_con_justificacion_y_traza_inmutable(pg):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    engine, adamo = pg
    ids = _ids(engine)
    cm_id = cl.crear_desde_empresas(engine, adamo, [ids["CM GRUPO TECNO"]], "ana")[0]["id"]
    cl.actualizar(engine, cm_id, {"perfil_volumen_mensual": 1_000_000})
    al.evaluar(engine, [ids["CM GRUPO TECNO"]])
    a = next(x for x in al.listar(engine, adamo) if x["regla"] == "PERF-VOL")

    with pytest.raises(al.ErrorAlerta):                         # descartar sin justificación
        al.gestionar(engine, a["id"], "ana", estado="descartada")
    with pytest.raises(al.ErrorAlerta):                         # transición no permitida
        al.gestionar(engine, a["id"], "ana", estado="posible_ros", justificacion="x" * 20)
    with engine.connect() as c:
        ana = c.scalar(text("SELECT id FROM usuarios WHERE username = 'ana'"))
    al.gestionar(engine, a["id"], "ana", estado="en_analisis", analista_id=ana, nota="Se pidió soporte al cliente")
    d = al.gestionar(engine, a["id"], "jorge", estado="descartada",
                     justificacion="El cliente acreditó un contrato nuevo que explica el aumento")
    assert d["estado"] == "descartada" and d["decidida_por"] == "jorge" and d["analista"] == "Ana"

    # Reevaluar no reabre ni borra la decisión
    al.evaluar(engine, [ids["CM GRUPO TECNO"]])
    assert al.obtener(engine, a["id"])["estado"] == "descartada"

    with pytest.raises(al.ErrorAlerta):                         # reabrir exige motivo
        al.gestionar(engine, a["id"], "ana", estado="en_analisis")
    r = al.gestionar(engine, a["id"], "ana", estado="en_analisis", nota="Nuevo soporte inconsistente")
    assert r["justificacion"] is None and r["decidida_por"] is None

    acciones = [e["accion"] for e in al.eventos(engine, a["id"])]
    assert acciones[0] == "detectada" and acciones.count("estado") == 3 and "asignacion" in acciones
    with pytest.raises(DBAPIError):                             # la bitácora no se edita
        with engine.begin() as c:
            c.execute(text("UPDATE cmp_alerta_eventos SET nota = 'x' WHERE alerta_id = :a"), {"a": a["id"]})
    with pytest.raises(DBAPIError):                             # ni se cierra sin justificación por SQL directo
        with engine.begin() as c:
            c.execute(text("UPDATE cmp_alertas SET estado = 'escalada', justificacion = NULL WHERE id = :a"), {"a": a["id"]})


def test_el_analista_debe_ser_interno(pg):
    from sqlalchemy import text
    engine, adamo = pg
    ids = _ids(engine)
    cm_id = cl.crear_desde_empresas(engine, adamo, [ids["CM GRUPO TECNO"]], "ana")[0]["id"]
    cl.actualizar(engine, cm_id, {"perfil_volumen_mensual": 1})
    al.evaluar(engine, [ids["CM GRUPO TECNO"]])
    a = al.listar(engine, adamo)[0]
    with engine.begin() as c:
        ext = c.execute(text("INSERT INTO usuarios (username, rol, organizacion_id, alcance) "
                             "VALUES ('equipo', 'cliente', :o, 'organizacion') RETURNING id"), {"o": adamo}).scalar_one()
    with pytest.raises(al.ErrorAlerta):
        al.gestionar(engine, a["id"], "ana", analista_id=ext)


def test_si_la_empresa_cambia_de_organizacion_sus_alertas_la_siguen(pg):
    from sqlalchemy import text
    engine, adamo = pg
    ids = _ids(engine)
    cm_id = cl.crear_desde_empresas(engine, adamo, [ids["CM GRUPO TECNO"]], "ana")[0]["id"]
    cl.actualizar(engine, cm_id, {"perfil_volumen_mensual": 1})
    al.evaluar(engine, [ids["CM GRUPO TECNO"]])
    from core.monitoreo_tx.repositorio import EmpresasRepo
    with engine.begin() as c:
        otra = c.execute(text("INSERT INTO organizaciones (nombre) VALUES ('Otra') RETURNING id")).scalar_one()
    assert EmpresasRepo(engine).mover_a_organizacion(ids["CM GRUPO TECNO"], otra)["ok"]
    assert al.listar(engine, adamo) == []
    assert al.listar(engine, otra)
