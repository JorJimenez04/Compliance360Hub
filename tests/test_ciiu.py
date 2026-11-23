"""Actividades CIIU y modelos de negocio automáticos (migración 041).

Lo que no puede fallar:
  - la lista es la oficial del DANE (502 clases) más los códigos DIAN de personas naturales;
  - cada regla CIIU → modelo apunta a códigos y modelos que existen;
  - la ficha solo acepta hasta cuatro actividades válidas y sin repetir;
  - el alta manual de clientes valida lo mismo que la edición.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://smoke:smoke@localhost:5432/smoke")
os.environ.setdefault("APP_ENV", "development")

from core.cumplimiento import ciiu  # noqa: E402
from core.cumplimiento import clientes as cl  # noqa: E402


def test_lista_oficial_completa():
    d = ciiu.como_dict()
    dane = [a for a in d["actividades"] if a["seccion"] != "DIAN"]
    assert len(dane) == 502
    assert len(d["divisiones"]) == 88
    assert len([s for s in d["secciones"] if s != "DIAN"]) == 21
    assert ciiu.actividad("6619").descripcion.startswith("Otras actividades auxiliares")
    assert ciiu.actividad("0010") is not None          # asalariados (DIAN)
    assert ciiu.actividad("9999") is None


def test_reglas_consistentes():
    assert ciiu.validar_reglas() == []


def test_modelos_automaticos_y_sugeridos():
    assert ciiu.actividad("9200").principal == "juegos_azar"
    a = ciiu.actividad("6619")
    assert a.principal == "pasarela_pagos" and "dispersion_pagos" in a.sugeridos and "pasarela_pagos" not in a.sugeridos
    assert ciiu.actividad("5310").principal is None and ciiu.actividad("5310").sugeridos == ("remesas",)
    assert ciiu.actividad("4711").principal == "comercio_general"      # por división
    assert ciiu.actividad("1311").principal is None                    # manufactura: se elige a mano
    principales, sugeridos = ciiu.modelos_de(["6619", "4791", "6619"])
    assert principales == ["pasarela_pagos", "ecommerce"]
    assert "marketplace" in sugeridos and not set(principales) & set(sugeridos)


@pytest.mark.parametrize("codigos, error", [
    (["6619", "6619"], "repetidas"), (["6619", "4791", "6201", "7020", "6910"], "cuatro"), (["1234"], "no válidos")])
def test_actividades_invalidas(codigos, error):
    with pytest.raises(cl.ErrorCliente, match=error):
        cl.validar_actividades(codigos)


def test_actividades_validas_en_orden():
    assert cl.validar_actividades([" 6619", "", "4791"]) == ["6619", "4791"]
    assert cl._texto_ciiu(["6619"]).startswith("6619 - Otras actividades auxiliares")
    assert cl._texto_ciiu([]) is None


# ---------- Contra PostgreSQL ----------
@pytest.fixture
def pg():
    url = os.getenv("TX_TEST_PG_URL")
    if not url:
        pytest.skip("Defina TX_TEST_PG_URL para probar contra PostgreSQL")
    from sqlalchemy import create_engine, text
    from tests._esquema import crear_esquema_minimo
    engine = create_engine(url)
    crear_esquema_minimo(engine)
    with engine.connect() as c:
        adamo = c.execute(text("SELECT id FROM organizaciones WHERE nombre = 'Adamo'")).scalar_one()
    yield engine, adamo
    engine.dispose()


def test_alta_manual_y_edicion(pg):
    engine, adamo = pg
    cid = cl.crear(engine, adamo, {"razon_social": "  CM Grupo Tecno ", "nit": "901419688-5",
                                   "actividades_ciiu": ["6619", "4791"],
                                   "modelos_negocio": ["dispersion_pagos", "ecommerce"], "nivel_riesgo": "Alto"}, "ana")
    f = cl.obtener(engine, cid)
    assert f["razon_social"] == "CM Grupo Tecno" and f["estado"] == "Prospecto" and f["tipo_persona"] == "juridica"
    assert f["actividades_ciiu"] == ["6619", "4791"] and [a["codigo"] for a in f["actividades"]] == ["6619", "4791"]
    assert f["sector_ciiu"].startswith("6619 - ")
    assert f["fecha_ultima_calificacion"] is not None
    cl.actualizar(engine, cid, {"actividades_ciiu": ["9200"], "sector_ciiu": "texto que se ignora"})
    f = cl.obtener(engine, cid)
    assert f["actividades_ciiu"] == ["9200"] and f["sector_ciiu"].startswith("9200 - ")
    cl.actualizar(engine, cid, {"actividades_ciiu": []})
    assert cl.obtener(engine, cid)["sector_ciiu"] is None


def test_alta_manual_rechaza_datos_invalidos(pg):
    engine, adamo = pg
    with pytest.raises(cl.ErrorCliente):
        cl.crear(engine, adamo, {"razon_social": " "}, "ana")
    with pytest.raises(cl.ErrorCliente):
        cl.crear(engine, adamo, {"razon_social": "X SAS", "actividades_ciiu": ["0000"]}, "ana")
    with pytest.raises(cl.ErrorCliente):
        cl.crear(engine, adamo, {"razon_social": "X SAS", "nivel_riesgo": "Muy Alto"}, "ana")
    cl.crear(engine, adamo, {"razon_social": "A SAS", "nit": "900"}, "ana")
    with pytest.raises(Exception, match="uq_clientes_organizacion_nit"):
        cl.crear(engine, adamo, {"razon_social": "B SAS", "nit": "900"}, "ana")


def test_base_rechaza_mas_de_cuatro_o_codigos_mal_formados(pg):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    engine, adamo = pg
    for valor in (["6619", "4791", "6201", "7020", "6910"], ["66A9"]):
        with pytest.raises(IntegrityError), engine.begin() as c:
            c.execute(text("INSERT INTO clientes (razon_social, organizacion_id, actividades_ciiu) VALUES ('Z', :o, :a)"),
                      {"o": adamo, "a": valor})
    with engine.begin() as c:
        c.execute(text("UPDATE organizaciones SET actividades_ciiu = '{6619}' WHERE id = :o"), {"o": adamo})
