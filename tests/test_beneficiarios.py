"""Beneficiarios de un cliente, tomados de sus transacciones (perfil 360).

Lo que no puede fallar:
  - se agrupan por documento y solo cuentan como pagos los débitos exitosos;
  - las señales de revisión (varios nombres, cuenta compartida, concentración, rechazos) se detectan;
  - los números de cuenta nunca salen completos;
  - la ruta es solo del equipo interno.
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
from core.cumplimiento import beneficiarios as bf  # noqa: E402


def test_enmascara_cuentas():
    assert bf.enmascarar("1600003360") == "•••• 3360"
    assert bf.enmascarar("123") == "123"
    assert bf.enmascarar(None) is None and bf.enmascarar(" ") is None


def test_rutas_solo_internas():
    externo = seg.Usuario(9, "equipo", "E", "cliente", organizacion_id=1, alcance="organizacion")
    for r in rc.router.routes:
        if "beneficiarios" in r.path:
            with pytest.raises(HTTPException) as e:
                r.dependant.dependencies[-1].call(externo)
            assert e.value.status_code == 403


@pytest.fixture
def pg(tmp_path):
    url = os.getenv("TX_TEST_PG_URL")
    if not url:
        pytest.skip("Defina TX_TEST_PG_URL para probar contra PostgreSQL")
    import pandas as pd
    from sqlalchemy import create_engine
    from core.cumplimiento import clientes as cl
    from core.monitoreo_tx.etl.sync import sincronizar
    from tests._esquema import crear_esquema_minimo
    from tests.test_monitoreo_tx import COLS
    engine = create_engine(url)
    crear_esquema_minimo(engine)

    def fila(no, idb, nombre, monto, cuenta, estado="Pagado", tipo="Debito", dia=1):
        return [no, datetime(2026, 3, dia), "10:00:00", f"t-{no}", tipo, "C", nombre, idb, "Bancolombia", 37,
                cuenta, monto, 0, -monto, estado, 1_000_000, None]
    filas = [
        fila(1, 111, "ANA PEREZ", 800_000, "0001112222", dia=1),
        fila(2, 111, "ANA P PEREZ", 200_000, "0001112222", dia=5),        # otro nombre, misma cédula
        fila(3, 222, "LUIS GOMEZ", 50_000, "0001112222", dia=6),          # usa la cuenta de Ana
        fila(4, 333, "MARIA RUIZ", 10_000, "0009998888", estado="Rechazado", dia=7),
        fila(5, 333, "MARIA RUIZ", 10_000, "0009998888", estado="Rechazado", dia=8),
        fila(6, 333, "MARIA RUIZ", 10_000, "0009998888", estado="Rechazado", dia=9),
        fila(7, 999, "FONDEO", 5_000_000, None, estado="Aprobado", tipo="Fondeo", dia=2),  # no es pago
    ]
    ruta = tmp_path / "r.xlsx"
    with pd.ExcelWriter(ruta) as w:
        pd.DataFrame(filas, columns=COLS).to_excel(w, sheet_name="CM GRUPO TECNO", index=False)
    sincronizar(ruta, engine, directorio_logs=tmp_path)
    from sqlalchemy import text
    with engine.connect() as c:
        adamo = c.execute(text("SELECT id FROM organizaciones WHERE nombre = 'Adamo'")).scalar_one()
        ids = list(c.scalars(text("SELECT id FROM tx_empresas")))
    cid = cl.crear_desde_empresas(engine, adamo, ids, "ana")[0]["id"]
    yield engine, cid
    engine.dispose()


def test_beneficiarios_y_senales(pg):
    engine, cid = pg
    r = bf.listar(engine, cid)
    por_id = {b["id_beneficiario"]: b for b in r["beneficiarios"]}
    assert set(por_id) == {"111", "222", "333"}                       # el fondeo no es un beneficiario
    assert r["monto_total"] == 1_050_000 and r["pagos_total"] == 3
    ana = por_id["111"]
    assert ana["pagos"] == 2 and ana["monto"] == 1_000_000 and r["beneficiarios"][0]["id_beneficiario"] == "111"
    assert {"varios_nombres", "cuenta_compartida", "concentracion"} <= set(ana["senales"])
    assert ana["cuentas"] == ["•••• 2222"]
    assert "cuenta_compartida" in por_id["222"]["senales"]
    maria = por_id["333"]
    assert maria["pagos"] == 0 and maria["rechazos"] == 3 and "rechazos" in maria["senales"]
    movs = bf.movimientos_de(engine, cid, "111")
    assert len(movs) == 2 and all(m["cuenta"] == "•••• 2222" for m in movs)
    assert bf.movimientos_de(engine, cid, "11") == []                 # coincidencia exacta, no parcial
