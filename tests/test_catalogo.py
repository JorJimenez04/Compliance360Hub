"""Catálogo de cumplimiento: integridad y reglas del paquete de vinculación (sin base de datos)."""

from __future__ import annotations

import pytest

from core.cumplimiento import catalogo as cat


def test_cada_modelo_apunta_a_documentos_y_regimenes_que_existen():
    for m in cat.MODELOS:
        assert m.riesgo_sugerido in cat.NIVELES, m.codigo
        assert set(m.documentos) <= set(cat.DOCUMENTOS), m.codigo
        assert all(cat.regimen(r) for r in m.regimenes), m.codigo
        assert set(m.monitoreo) <= {"fiat", "cripto"} and m.monitoreo, m.codigo
        assert m.por_que, m.codigo


def test_codigos_unicos():
    for coleccion in (cat.MODELOS, cat.SERVICIOS, cat.REGIMENES):
        codigos = [x.codigo for x in coleccion]
        assert len(codigos) == len(set(codigos))
    assert set(cat.DOCUMENTOS_BASE) <= set(cat.DOCUMENTOS)


def test_estan_todos_los_servicios_del_oficial():
    codigos = {s.codigo for s in cat.SERVICIOS}
    assert {"oficial_cumplimiento", "kyc_kyb", "screening", "monitoreo_fiat", "monitoreo_cripto",
            "reporteria_uiaf", "auditoria", "capacitacion"} <= codigos


def test_mas_riesgo_pide_mas_y_vence_antes():
    alto, medio, bajo = (cat.requisitos(["dispersion_pagos"], n) for n in ("Alto", "Medio", "Bajo"))
    assert len(alto) > len(medio) > len(bajo)
    vig = lambda reqs, c: next(r.vigencia_meses for r in reqs if r.documento.codigo == c)
    assert vig(alto, "formulario_vinculacion") == 12 and vig(medio, "formulario_vinculacion") == 24 \
        and vig(bajo, "formulario_vinculacion") == 36
    assert "extractos_bancarios" in {r.documento.codigo for r in alto}
    assert "extractos_bancarios" not in {r.documento.codigo for r in bajo}


def test_lo_que_pide_el_modelo_se_exige_aunque_el_riesgo_sea_bajo():
    codigos = {r.documento.codigo for r in cat.requisitos(["exchange_cripto"], "Bajo")}
    assert {"wallets_declaradas", "reporte_kyt", "politica_travel_rule", "proof_of_reserves"} <= codigos


def test_sin_duplicados_y_con_origen_combinado():
    reqs = cat.requisitos(["exchange_cripto", "on_off_ramp"], "Alto")
    codigos = [r.documento.codigo for r in reqs]
    assert len(codigos) == len(set(codigos))
    wallets = next(r for r in reqs if r.documento.codigo == "wallets_declaradas")
    assert set(wallets.origen) == {"exchange_cripto", "on_off_ramp"}


def test_persona_natural_no_recibe_documentos_societarios():
    codigos = {r.documento.codigo for r in cat.requisitos(["comercio_general"], "Alto", cat.PN)}
    assert "camara_comercio" not in codigos and "composicion_accionaria" not in codigos
    assert "documento_identidad" in codigos


def test_riesgo_sugerido_toma_el_mas_alto():
    assert cat.riesgo_sugerido(["comercio_general"]) == "Bajo"
    assert cat.riesgo_sugerido(["comercio_general", "exchange_cripto"]) == "Alto"
    assert cat.riesgo_sugerido([]) is None
    assert cat.monitoreo_sugerido(["dispersion_pagos", "exchange_cripto"]) == ("fiat", "cripto")


@pytest.mark.parametrize("modelos, nivel", [(["no_existe"], "Alto"), (["dispersion_pagos"], "Muy Alto")])
def test_entradas_invalidas(modelos, nivel):
    with pytest.raises(ValueError):
        cat.requisitos(modelos, nivel)


def test_el_catalogo_es_serializable():
    import json
    d = cat.como_dict()
    assert json.loads(json.dumps(d))["modelos"]
