"""Tablero general de cumplimiento y reportes UIAF (migración 047).

Lo que no puede fallar:
  - los montos por subcliente, la participación y la comparación con el perfil declarado;
  - los beneficiarios representativos salen con el documento enmascarado;
  - el filtro por organización no mezcla datos de otra;
  - los avisos automáticos se disparan (sobre perfil, sin documentos, posible ROS…);
  - los reportes UIAF: solo PDF, sin duplicados, subcliente de la misma organización;
  - requerimientos con beneficiarios y origen «director»;
  - permisos: el cliente no entra, el director consulta y no carga, solo el super_admin elimina.
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
from api.rutas import tablero as rt  # noqa: E402
from core.cumplimiento import clientes as cl  # noqa: E402
from core.cumplimiento import reportes_uiaf as ru  # noqa: E402
from core.cumplimiento import requerimientos as rq  # noqa: E402
from core.cumplimiento import tablero as tb  # noqa: E402

PDF = b"%PDF-1.4\n% prueba\n"
HOY = date.today()


def test_permisos_y_menu():
    externo = seg.Usuario(9, "equipo", "E", "cliente", organizacion_id=1, alcance="organizacion")
    director = seg.Usuario(8, "dir", "D", "director_cumplimiento")
    compliance = seg.Usuario(7, "ana", "A", "compliance")
    for r in (r for r in rt.router.routes if isinstance(r, APIRoute)):
        dep = r.dependant.dependencies[-1].call
        with pytest.raises(HTTPException):
            dep(externo)
        if r.methods & {"POST", "DELETE"}:
            with pytest.raises(HTTPException):
                dep(director)
        else:
            assert dep(director) is director
        if r.path.endswith("/eliminar"):
            with pytest.raises(HTTPException):
                dep(compliance)
    assert seg.modulos_visibles("director_cumplimiento")[0] == "tablero"        # su pantalla de inicio
    assert "tablero" in seg.modulos_visibles("super_admin")
    assert "tablero" not in seg.modulos_visibles("cliente") and "tablero" not in seg.modulos_visibles("junta")


def test_enmascarar():
    assert tb.enmascarar_documento("1020304050") == "****4050"
    assert tb.enmascarar_documento("123") == "123" and tb.enmascarar_documento(None) is None


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
        paycop = c.execute(text("INSERT INTO organizaciones (nombre) VALUES ('Paycop') RETURNING id")).scalar_one()
    paxum = cl.crear(engine, adamo, {"razon_social": "Paxum", "nivel_riesgo": "Medio"}, "jorge")
    cm = cl.crear(engine, adamo, {"razon_social": "CM Grupo Tecno", "nit": "900222", "nivel_riesgo": "Bajo"}, "jorge")
    ajeno = cl.crear(engine, paycop, {"razon_social": "Cliente Paycop", "nit": "900333", "nivel_riesgo": "Bajo"}, "jorge")
    with engine.begin() as c:
        c.execute(text("UPDATE clientes SET perfil_volumen_mensual = 1000 WHERE id = :p"), {"p": paxum})
        emp = {}
        for n, o, cid in (("PAXUM", adamo, paxum), ("CM", adamo, cm), ("SUELTA", adamo, None), ("PAY", paycop, ajeno)):
            emp[n] = c.execute(text("INSERT INTO tx_empresas (nombre_reporte, organizacion_id, cliente_id) VALUES (:n, :o, :c) RETURNING id"),
                               {"n": n, "o": o, "c": cid}).scalar_one()
        filas = []
        mes = HOY.replace(day=1)
        # Paxum: 1.500 en el mes (50 % sobre su perfil de 1.000); el beneficiario 1020304050 recibe 1.200
        filas += [("PAXUM", "Débito", True, 600, "Ana", "1020304050"), ("PAXUM", "Débito", True, 600, "Ana", "1020304050"),
                  ("PAXUM", "Débito", True, 300, "Beto", "88889999"), ("PAXUM", "Débito", False, 999, "Beto", "88889999"),
                  ("PAXUM", "Crédito", True, 100, "Beto", "88889999")]
        filas += [("CM", "Débito", True, 500, "Ceci", "77776666"), ("SUELTA", "Débito", True, 50, "Dani", "1111"),
                  ("PAY", "Débito", True, 9000, "Otro", "5555")]
        for i, (cli, tipo, ok, monto, ben, doc) in enumerate(filas):
            c.execute(text("INSERT INTO tx_transacciones (cliente, no_registro, id_transaccion, fecha, tipo_transaccion, "
                           "tipo_persona, beneficiario, id_beneficiario, monto, estado, exitosa, row_hash, sincronizado_en) "
                           "VALUES (:c, :i, :t, :f, :tipo, 'Natural', :b, :d, :m, :e, :ok, 'x', now())"),
                      {"c": cli, "i": i, "t": f"T{i}", "f": mes, "tipo": tipo, "b": ben, "d": doc, "m": monto,
                       "e": "Pagado" if ok else "Rechazado", "ok": ok})
        c.execute(text("INSERT INTO cmp_alertas (organizacion_id, empresa_id, regla, periodo, prioridad, titulo, estado, "
                       "justificacion, decidida_por, decidida_en) VALUES (:o, :e, 'VOL', :p, 'Alta', 'Volumen atípico', "
                       "'posible_ros', 'Movimientos sin soporte económico', 'jorge', now())"),
                  {"o": adamo, "e": emp["PAXUM"], "p": mes})
    yield engine, {"adamo": adamo, "paycop": paycop, "paxum": paxum, "cm": cm, "ajeno": ajeno}
    engine.dispose()


def test_tablero_por_subcliente(pg):
    engine, x = pg
    t = tb.tablero(engine, organizacion_id=x["adamo"])
    assert [o["nombre"] for o in t["organizaciones"]] == ["Adamo"]
    assert t["kpis"]["monto_pagado"] == 2050 and t["kpis"]["pagos_exitosos"] == 5         # sin Paycop
    subs = {s["nombre"]: s for s in t["organizaciones"][0]["subclientes"]}
    p = subs["Paxum"]
    assert p["monto_pagado"] == 1500 and p["pagos_enviados"] == 4 and p["devoluciones"] == 1
    assert round(p["participacion"], 3) == round(1500 / 2050, 3)
    assert round(p["desviacion_perfil"], 2) == 0.5
    assert p["top_beneficiarios"][0]["documento"] == "****4050" and p["top_beneficiarios"][0]["monto"] == 1200
    assert round(p["concentracion_top3"], 2) == 1.0
    assert any(n.startswith("Sin subcliente asignado (SUELTA)") for n in subs)
    textos = " | ".join(a["texto"] for a in t["avisos"])
    assert "posible ROS" in textos and "Paxum opera 50% por encima" in textos
    assert "CM Grupo Tecno opera sin perfil transaccional" in textos and "sin subcliente asignado" in textos
    assert t["alertas"]["posible_ros"] == 1 and t["posible_ros"][0]["subcliente"] == "Paxum"
    todo = tb.tablero(engine)
    assert todo["kpis"]["monto_pagado"] == 11050 and len(todo["organizaciones"]) == 2


def test_periodo_y_comparacion(pg):
    engine, x = pg
    mes = HOY.replace(day=1)
    t = tb.tablero(engine, mes, HOY, x["adamo"])
    assert t["periodo"]["comparado"] and t["kpis"]["variacion_monto"] is None          # sin periodo anterior
    vacio = tb.tablero(engine, mes - timedelta(days=400), mes - timedelta(days=370), x["adamo"])
    assert vacio["kpis"]["monto_pagado"] == 0 and vacio["organizaciones"][0]["subclientes"] == []


def test_reportes_uiaf(pg):
    engine, x = pg
    rid = ru.guardar(engine, x["adamo"], {"tipo": "ROS", "fecha_presentacion": HOY, "radicado": "123", "cliente_id": x["paxum"]},
                     "C:\\carpeta\\ros.pdf", PDF, "jorge")
    errores = [({"tipo": "ROS", "fecha_presentacion": HOY}, b"no es pdf"),
               ({"tipo": "XYZ", "fecha_presentacion": HOY}, PDF + b"1"),
               ({"tipo": "ROS", "fecha_presentacion": HOY + timedelta(days=1)}, PDF + b"2"),
               ({"tipo": "AROS", "fecha_presentacion": HOY}, PDF + b"3"),                         # AROS sin periodo
               ({"tipo": "ROS", "fecha_presentacion": HOY, "cliente_id": x["ajeno"]}, PDF + b"4"),
               ({"tipo": "ROS", "fecha_presentacion": HOY}, PDF)]                                 # duplicado
    for datos, contenido in errores:
        with pytest.raises(ru.ErrorReporte):
            ru.guardar(engine, x["adamo"], datos, "r.pdf", contenido, "jorge")
    lista = ru.listar(engine, x["adamo"])
    assert len(lista) == 1 and lista[0]["archivo_nombre"] == "ros.pdf" and lista[0]["subcliente"] == "Paxum"
    assert ru.archivo(engine, rid)["archivo"] == PDF
    t = tb.tablero(engine, organizacion_id=x["adamo"])
    assert t["reportes_uiaf"]["ros"] == 1
    with pytest.raises(LookupError):
        ru.eliminar(engine, x["paycop"], rid)
    assert ru.eliminar(engine, x["adamo"], rid)["tipo"] == "ROS"


def test_requerimientos_con_beneficiarios_y_director(pg):
    engine, x = pg
    r = rq.crear(engine, x["adamo"], {"dirigido_a": "cliente", "cliente_id": x["paxum"], "origen": "director", "tipo": "rfi_transacciones",
                                      "asunto": "Soporte de pagos a Ana", "fecha_recibido": HOY,
                                      "beneficiarios": [{"id_beneficiario": "1020304050", "nombre": "Ana", "actividad": "Comercio de ropa"},
                                                        {"id_beneficiario": "1020304050", "nombre": "Ana"}]}, "jorge")
    q = rq.obtener(engine, x["adamo"], r["id"])
    assert q["origen"] == "director" and q["beneficiarios"] == [
        {"id_beneficiario": "1020304050", "nombre": "Ana", "actividad": "Comercio de ropa", "notas": None}]
    assert rq.actualizar(engine, x["adamo"], r["id"], {"beneficiarios": q["beneficiarios"]}, "jorge") == []
    assert rq.actualizar(engine, x["adamo"], r["id"], {"beneficiarios": []}, "jorge") == ["beneficiarios"]
    with pytest.raises(rq.ErrorRequerimiento):
        rq.actualizar(engine, x["adamo"], r["id"], {"beneficiarios": [{"nombre": " "}]}, "jorge")
    assert [b["nombre"] for b in rq.buscar_beneficiarios(engine, x["paxum"], "an")] == ["Ana"]
    assert rq.buscar_beneficiarios(engine, x["paxum"], "Otro") == []                            # de otra organización
    rq.actualizar(engine, x["adamo"], r["id"], {"beneficiarios": [{"id_beneficiario": "1020304050", "nombre": "Ana"}]}, "jorge")
    t = tb.tablero(engine, organizacion_id=x["adamo"])
    assert t["requerimientos"][0]["beneficiarios"][0]["id_beneficiario"] == "****4050"
