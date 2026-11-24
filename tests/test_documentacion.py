"""Documentación del cliente y de sus beneficiarios leída de su carpeta en OneDrive (migración 042).

Lo que no puede fallar:
  - cada archivo se reconoce por su nombre y lo asignado a mano no se pisa al volver a revisar;
  - lo que se borra de OneDrive deja de contar;
  - «Listo para banco» exige los cinco documentos de una persona jurídica;
  - los 10 beneficiarios más representativos tienen expediente y una vez abierto se conserva;
  - todo es solo del equipo interno.
"""

from __future__ import annotations

import os
from datetime import datetime

import pytest
from fastapi import HTTPException

os.environ.setdefault("DATABASE_URL", "postgresql://smoke:smoke@localhost:5432/smoke")
os.environ.setdefault("APP_ENV", "development")

from api import seguridad as seg  # noqa: E402
from api.rutas import clientes as rc  # noqa: E402
from core.cumplimiento import documentos as dc  # noqa: E402


@pytest.mark.parametrize("nombre, de_benef, esperado", [
    ("Certificado de Existencia CM 2026.pdf", False, "certificado_existencia"),
    ("camara_comercio.pdf", False, "certificado_existencia"),
    ("Composición accionaria.xlsx", False, "composicion_accionaria"),
    ("Contrato de servicios firmado.pdf", False, "contrato"),
    ("RUT 2026.pdf", False, "rut"),
    ("Cédula representante legal.pdf", False, "cedula_rl"),
    ("cc rl.jpg", False, "cedula_rl"),
    ("cedula.pdf", True, "documento_identidad"),
    ("Certificación bancaria Bancolombia.pdf", True, "certificacion_bancaria"),
    ("foto.png", False, None),
])
def test_reconoce_por_nombre(nombre, de_benef, esperado):
    assert dc.reconocer(nombre, de_benef) == esperado


def test_enlaces_y_nombres():
    assert dc.validar_enlace("https://holdingsbposas-my.sharepoint.com/:f:/g/personal/x/abc") is not None
    assert dc.validar_enlace("  ") is None
    with pytest.raises(dc.ErrorCarpeta):
        dc.validar_enlace("http://evil.example.com/x")
    assert dc.nombre_carpeta_beneficiario("1088007763", "LUIS / GOMEZ") == "1088007763 - LUIS GOMEZ"
    assert dc.tipo_persona_beneficiario("N", None) == "juridica"
    assert dc.tipo_persona_beneficiario("C", "Natural") == "natural"


def test_rutas_solo_internas():
    externo = seg.Usuario(9, "equipo", "E", "cliente", organizacion_id=1, alcance="organizacion")
    for r in rc.router.routes:
        if "documenta" in r.path or "expedientes" in r.path or "/api/documentos" in r.path:
            with pytest.raises(HTTPException) as e:
                r.dependant.dependencies[-1].call(externo)
            assert e.value.status_code == 403


class LectorFalso:
    """OneDrive simulado: un árbol de carpetas en memoria."""
    def __init__(self, arbol):
        self.arbol = arbol
        self.resueltos = 0

    def resolver(self, enlace):
        self.resueltos += 1
        return {"drive_id": "d1", "item_id": "raiz", "nombre": "CM Grupo Tecno"}

    def hijos(self, drive, item_id):
        return self.arbol.get(item_id, [])


def _carpeta(i, n):
    return {"id": i, "name": n, "folder": {}}


def _archivo(i, n):
    return {"id": i, "name": n, "file": {}, "size": 10, "webUrl": f"https://x.sharepoint.com/{i}",
            "lastModifiedDateTime": "2026-11-20T10:00:00Z"}


@pytest.fixture
def pg(tmp_path):
    url = os.getenv("TX_TEST_PG_URL")
    if not url:
        pytest.skip("Defina TX_TEST_PG_URL para probar contra PostgreSQL")
    import pandas as pd
    from sqlalchemy import create_engine, text
    from core.cumplimiento import clientes as cl
    from core.monitoreo_tx.etl.sync import sincronizar
    from tests._esquema import crear_esquema_minimo
    from tests.test_monitoreo_tx import COLS
    engine = create_engine(url)
    crear_esquema_minimo(engine)
    filas = [[n, datetime(2026, 3, 1 + n % 27), "10:00:00", f"t-{n}", "Debito", "C", f"BENEF {n}", 1000 + n,
              "Bancolombia", 37, f"00{n:04d}", 1_000_000 * (20 - n), 0, -1_000_000 * (20 - n), "Pagado", 9, None]
             for n in range(1, 13)]                                     # 12 beneficiarios, montos decrecientes
    ruta = tmp_path / "r.xlsx"
    with pd.ExcelWriter(ruta) as w:
        pd.DataFrame(filas, columns=COLS).to_excel(w, sheet_name="CM GRUPO TECNO", index=False)
    sincronizar(ruta, engine, directorio_logs=tmp_path)
    with engine.connect() as c:
        adamo = c.execute(text("SELECT id FROM organizaciones WHERE nombre = 'Adamo'")).scalar_one()
        ids = list(c.scalars(text("SELECT id FROM tx_empresas")))
    cid = cl.crear_desde_empresas(engine, adamo, ids, "ana")[0]["id"]
    cl.actualizar(engine, cid, {"carpeta_onedrive": "https://holdingsbposas-my.sharepoint.com/:f:/g/personal/x/abc"})
    yield engine, cid
    engine.dispose()


ARBOL = {
    "raiz": [_carpeta("corp", "Documentación corporativa"), _carpeta("ben", "Beneficiarios"), _archivo("suelto", "Notas.txt")],
    "corp": [_archivo("a1", "Certificado de existencia.pdf"), _archivo("a2", "Composicion accionaria.pdf"),
             _archivo("a3", "Contrato.pdf"), _archivo("a4", "RUT.pdf"), _archivo("a5", "escaneo_001.pdf")],
    "ben": [_carpeta("b1", "1001 - BENEF 1"), _carpeta("b12", "1012 - BENEF 12"), _archivo("x", "suelto.pdf")],
    "b1": [_archivo("c1", "cedula.pdf"), _archivo("c2", "certificacion bancaria.pdf")],
    "b12": [_archivo("c3", "cedula.pdf")],
}


def test_revisar_y_listo_para_banco(pg):
    engine, cid = pg
    lector = LectorFalso(ARBOL)
    r = dc.revisar(engine, cid, lector)
    assert r == {"archivos_propios": 6, "carpetas_beneficiarios": 2, "archivos_beneficiarios": 3, "retirados": 0}
    e = dc.estado_propio(engine, cid)
    assert e["faltan"] == ["Cédula del representante legal"] and not e["listo_para_banco"]
    assert {a["nombre_archivo"] for a in e["otros_archivos"]} == {"escaneo_001.pdf", "Notas.txt"}
    # Asignación manual: se conserva al volver a revisar
    doc = next(a for a in e["otros_archivos"] if a["nombre_archivo"] == "escaneo_001.pdf")
    dc.asignar(engine, doc["id"], "cedula_rl", "ana")
    dc.revisar(engine, cid, lector)
    assert lector.resueltos == 1                                     # el enlace se resuelve una sola vez
    e = dc.estado_propio(engine, cid)
    assert e["listo_para_banco"] and e["faltan"] == []
    # Un archivo borrado de OneDrive deja de contar
    ARBOL2 = {**ARBOL, "corp": [x for x in ARBOL["corp"] if x["id"] != "a3"]}
    assert dc.revisar(engine, cid, LectorFalso(ARBOL2))["retirados"] == 1
    assert dc.estado_propio(engine, cid)["faltan"] == ["Contrato"]


def test_expedientes_beneficiarios(pg):
    engine, cid = pg
    dc.revisar(engine, cid, LectorFalso(ARBOL))
    r = dc.expedientes_beneficiarios(engine, cid)
    ids = [e["id_beneficiario"] for e in r["expedientes"]]
    assert ids[:10] == [str(1000 + n) for n in range(1, 11)]        # top 10 por monto, en orden
    assert "1012" in ids                                              # tiene carpeta: también tiene expediente
    b1 = next(e for e in r["expedientes"] if e["id_beneficiario"] == "1001")
    assert b1["completo"] and b1["carpeta_nombre"] == "1001 - BENEF 1"
    b2 = next(e for e in r["expedientes"] if e["id_beneficiario"] == "1002")
    assert not b2["completo"] and b2["carpeta_sugerida"] == "1002 - BENEF 2" and b2["carpeta_nombre"] is None
    # Manual, cerrar y conservar
    dc.abrir_expediente(engine, cid, "1011", "ana")
    assert "1011" in [e["id_beneficiario"] for e in dc.expedientes_beneficiarios(engine, cid)["expedientes"]]
    with pytest.raises(dc.ErrorCarpeta):
        dc.abrir_expediente(engine, cid, "999999", "ana")
    assert dc.cerrar_expediente(engine, cid, "1003")
    assert "1003" not in [e["id_beneficiario"] for e in dc.expedientes_beneficiarios(engine, cid)["expedientes"]]


def test_error_de_carpeta_queda_registrado(pg):
    engine, cid = pg

    class Roto(LectorFalso):
        def resolver(self, enlace):
            raise dc.ErrorCarpeta("La cuenta conectada a OneDrive no tiene acceso a esa carpeta.")
    with pytest.raises(dc.ErrorCarpeta):
        dc.revisar(engine, cid, Roto({}))
    assert "no tiene acceso" in dc.estado_propio(engine, cid)["carpeta"]["error"]
