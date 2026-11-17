"""
tests/test_monitoreo_tx.py
Módulo Monitoreo Transaccional (app/monitoreo_tx).

Las pruebas de lectura, cálculo y formato no tocan la base: reproducen con un
Excel sintético los problemas reales del reporte de AdamoPay (filas partidas,
filas de control, montos inválidos, codificación dañada).

Las de sincronización necesitan un PostgreSQL de pruebas, que se VACÍA:

    $env:TX_TEST_PG_URL = "postgresql://adamo:adamo_dev_2026@localhost:5432/tx_test"
    python -m pytest tests/test_monitoreo_tx.py -q

Sin esa variable se omiten.
"""

from __future__ import annotations

import os
import pathlib
from datetime import datetime, time

import pandas as pd
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://smoke:smoke@localhost:5432/smoke")
os.environ.setdefault("APP_ENV", "development")

from app.monitoreo_tx.domain.entidades import FiltrosTransacciones as Filtros  # noqa: E402
from app.monitoreo_tx.domain.metricas import calcular_kpis  # noqa: E402
from app.monitoreo_tx.etl.excel_loader import limpiar_hoja  # noqa: E402

COLS = [
    "No.", "FECHA", "HORA", "ID DE TRANSACCION", "TIPO DE TRANSACCION", "TIPO DE IDENTIFICACION",
    "BENEFICIARIO", "ID DE CLIENTE", "BANCO", "TIPO DE CUENTA", "NUMERO DE CUENTA", "MONTO (COP)",
    "COMISION (COP)", "MONTO TOTAL (COP)", "ESTADO", "SALDO (COP)", "DESCRIPCION",
]
F = datetime(2026, 1, 30)
H = time(10, 0, 0)


def _fila(no, id_tx, monto, estado="Pagado", benef="ANA PEREZ", desc=None, fecha=F):
    return [no, fecha, H, id_tx, "Debito", "C", benef, 1088007763, "Bancolombia", 37,
            "00123", monto, 0, -monto if isinstance(monto, int) else None, estado, 1_000_000, desc]


def _hoja_sucia() -> pd.DataFrame:
    filas = [
        _fila(5, "tx-5", 100_000),
        # Beneficiario partido en dos filas: el resto del registro queda desplazado
        [4, F, H, "tx-4", "Debito", "N", "CENTRO COMERCIAL DE"] + [None] * 10,
        ["ENTRETENIMIENTO", 8110293683, "Bancolombia", 37, 1600003360, 789_096, 0, -789_096,
         "Pagado", 316_148_787, " - CONEXMEDIA"] + [None] * 6,
        _fila(3, "tx-3", 50_000, estado="Retornado", desc="ACCOUNT NOT"),
        # Descripción partida
        ["AUTHORIZED"] + [None] * 16,
        _fila(2, "tx-2", 20_000, estado=None),           # sin estado
        _fila(1, "tx-1", "abc"),                          # monto inválido
        ["HASH: " + "A" * 64] + [None] * 16,              # fila de control
        [None] * 17,                                      # vacía
        # Mismo No. con distinto ID: transacciones distintas (caso real)
        _fila(6, "bolsillo-a", 1_000, estado="Aprobado"),
        _fila(6, "bolsillo-b", 2_000, estado="Aprobado"),
        # Fondeo: columnas de beneficiario con "-" (quedan vacías)
        [8, F, H, "fondeo-1", "Fondeo", "-", "-", "-", "-", "-", "-", 5_000, 0, 5_000, "Aprobado", 1_000, "TEST"],
    ]
    return pd.DataFrame(filas, columns=COLS, dtype=object)



def test_limpiar_hoja_repara_y_valida():
    r = limpiar_hoja(_hoja_sucia(), "Cliente A")
    df = r.df.set_index("id_transaccion")

    assert r.reparadas == 2
    assert df.loc["tx-4", "beneficiario"] == "CENTRO COMERCIAL DE ENTRETENIMIENTO"
    assert df.loc["tx-4", "numero_cuenta"] == "1600003360"
    assert df.loc["tx-4", "monto"] == 789_096
    assert df.loc["tx-4", "tipo_persona"] == "Jurídica"
    assert df.loc["tx-3", "descripcion"] == "ACCOUNT NOT AUTHORIZED"
    assert df.loc["tx-2", "estado"] == "Sin estado"
    assert df.loc["tx-5", "id_beneficiario"] == "1088007763"
    assert df.loc["tx-5", "numero_cuenta"] == "00123"
    assert {"bolsillo-a", "bolsillo-b"} <= set(df.index)
    assert "tx-1" not in df.index
    assert df.loc["fondeo-1", "tipo_persona"] == "Desconocido"
    assert df.loc["fondeo-1", "beneficiario"] is None or pd.isna(df.loc["fondeo-1", "beneficiario"])

    motivos = sorted(x["motivo"] for x in r.rechazos)
    assert motivos == ["Fila de control (hash de integridad)", "Monto no numérico"]


def test_kpis():
    df = limpiar_hoja(_hoja_sucia(), "Cliente A").df
    k = calcular_kpis(df)
    assert k.total_movimientos == 7
    # Pagos = débitos (6). El fondeo no cuenta como pago fallido.
    assert (k.pagos_enviados, k.pagos_exitosos) == (6, 2)
    assert k.monto_pagado == 889_096
    assert k.tasa_exito == pytest.approx(2 / 6)
    assert (k.fondeos, k.monto_fondeado) == (1, 5_000)


def test_tasa_descuenta_devoluciones_y_motivos():
    from app.monitoreo_tx.domain import metricas as m

    df = pd.DataFrame({
        "tipo_transaccion": ["Debito"] * 4 + ["Credito", "Fondeo", "Transferencia entre bolsillos"],
        "estado": ["Pagado"] * 3 + ["Sin estado", "Retornado", "Aprobado", "Aprobado"],
        "exitosa": [True] * 3 + [False] * 4,
        "monto": [100.0, 200.0, 300.0, 50.0, 100.0, 1_000.0, 70.0],
        "descripcion": [None] * 4 + ["ACCOUNT AND ID PROVIDED DO NOT MATCH - BANTOKENS.BTK", None, None],
    })
    k = m.calcular_kpis(df)
    # 3 pagos «Pagado», 1 volvió como devolución: llegaron 2 de 4 enviados
    assert k.tasa_exito == pytest.approx(2 / 4)
    assert (k.devoluciones, k.monto_devuelto) == (1, 100.0)

    comp = m.composicion_movimientos(df).set_index("clave")["movimientos"].to_dict()
    assert comp == {"pago_ok": 3, "pago_sin_estado": 1, "devolucion": 1, "fondeo": 1, "interno": 1}

    assert m.motivo_devolucion("ACCOUNT DOES NOT EXIST") == "La cuenta no existe o el número es inválido"
    assert m.motivo_devolucion("INACTIVE OR BLOCKED ACCOUNT") == "Cuenta inactiva, bloqueada o no autorizada"
    assert m.motivo_devolucion("PAGADO - BANTOKENS.BTK") == "Motivo no informado"
    assert m.motivo_devolucion(None) == "Motivo no informado"
    assert m.motivos_devolucion(df)["motivo"].tolist() == ["Cuenta y documento no coinciden"]


def test_periodo_anterior_y_granularidad():
    from datetime import date

    from app.monitoreo_tx.domain import metricas as m

    assert m.periodo_anterior(date(2026, 3, 1), date(2026, 3, 31)) == (date(2026, 1, 29), date(2026, 2, 28))
    assert m.granularidad_sugerida(date(2026, 1, 1), date(2026, 1, 31)) == "Diaria"
    assert m.granularidad_sugerida(date(2025, 1, 1), date(2025, 12, 31)) == "Semanal"
    assert m.granularidad_sugerida(date(2023, 1, 1), date(2025, 12, 31)) == "Mensual"
    assert m.variacion(110, 100) == pytest.approx(0.10)
    assert m.variacion(5, 0) is None



@pytest.mark.parametrize("dañado, esperado", [
    ("MARIANA PATIÃ‘O HERNANDEZ", "MARIANA PATIÑO HERNANDEZ"),       # Ñ leída como Windows-1252
    ("ESTEFANY ALARCÃ“N PINEDA", "ESTEFANY ALARCÓN PINEDA"),
    ("NICOLÃ\x81S ARTURO", "NICOLÁS ARTURO"),                         # byte que cp1252 no define
    ("DIANA MARCELA NIÃƒâ€˜O GALINDO", "DIANA MARCELA NIÑO GALINDO"),  # dañado dos veces
    ("YERFERSON IBAÃ±EZ BLANCO", "YERFERSON IBAÑEZ BLANCO"),          # conserva las mayúsculas
    ("JUAN BAUTISTA LARGO SUAREZÂ", "JUAN BAUTISTA LARGO SUAREZ"),    # resto de espacio no separable
    ("SÃO PAULO", "SÃO PAULO"),                                       # texto legítimo: no se toca
    ("CAFÉ Y ÑOÑO", "CAFÉ Y ÑOÑO"),
])
def test_reparar_codificacion(dañado, esperado):
    from app.monitoreo_tx.etl.excel_loader import _limpiar_texto
    assert _limpiar_texto(dañado) == esperado



CSV_CLIENTE = (
    "No.;FECHA;HORA;ID DE TRANSACCION;TIPO DE TRANSACCION;TIPO DE IDENTIFICACION;BENEFICIARIO;ID DE CLIENTE;"
    "BANCO;TIPO DE CUENTA;NUMERO DE CUENTA;MONTO (COP);COMISION (COP);MONTO TOTAL (COP);ESTADO;SALDO (COP);DESCRIPCION\r\n"
    "4;12/11/2026;17:11:42;tx-4;Debito;PPT;JORGE GOMEZ;1000349307;Bre-B;breb;@3187774226;735078;1900;-736978;Pagado;150992986;\r\n"
    # Nombre partido por un salto de línea: el resto del registro queda en la fila siguiente
    "3;05/10/2026;11:29:52;tx-3;Debito;C;YURI TATIANA ACOSTA\r\n"
    ";1096063506;Bancolombia;37;09000005219;5145832;2400;-5148232;Pagado;163421171;\r\n"
    "\r\n"
    "2;01/06/2026;10:47:44;tx-2;Credito;C;LUISA DAZA;1011200585;BreB;breb;@LDA585;617498;0;617498;Retornado;168988582;INVALID ACCOUNT NUMBER\r\n"
    "1;28/05/2026;09:50:49;fondeo-1;Fondeo;-;-;-;-;-;-;169606080;0;169606080;Aprobado;169606080;-\r\n"
)



def test_ranking_de_clientes():
    from app.monitoreo_tx.domain.metricas import top_beneficiarios

    def tx(doc, nombre, monto, estado="Pagado", tipo="Debito"):
        return {"id_beneficiario": doc, "beneficiario": nombre, "monto": monto, "estado": estado,
                "exitosa": estado == "Pagado", "tipo_transaccion": tipo, "fecha_hora": pd.Timestamp("2026-06-01")}

    df = pd.DataFrame([
        tx("1", "ANA", 100), tx("1", "ANA", 100), tx("1", "ANA", 100),   # 3 pagos, 300
        tx("2", "LUIS", 1_000),                                          # 1 pago, 1.000
        tx("3", "EVA", 50, estado="Rechazado"),                          # no exitoso: no cuenta
        tx("2", "LUIS", 1_000, estado="Retornado", tipo="Credito"),      # devolución: no cuenta
    ])
    por_monto = top_beneficiarios(df, por="monto")
    assert list(por_monto["beneficiario"]) == ["LUIS", "ANA"] and list(por_monto["posicion"]) == [1, 2]
    assert round(por_monto.loc[0, "pct"], 4) == round(1_000 / 1_300, 4)
    por_pagos = top_beneficiarios(df, por="pagos")
    assert list(por_pagos["beneficiario"]) == ["ANA", "LUIS"] and por_pagos.loc[0, "pct"] == 0.75
    assert top_beneficiarios(df.iloc[0:0]).empty



def test_formato_cop():
    from app.monitoreo_tx.ui.formato import formato_cop
    sp = "\u00a0"
    assert formato_cop(1_234_567) == f"${sp}1.234.567"
    assert formato_cop(42_300_000, compacto=True) == f"${sp}42,3{sp}M"
    assert formato_cop(20_382_643_487, compacto=True) == f"${sp}20.383{sp}M"
    assert formato_cop(1_250_000_000_000, compacto=True) == f"${sp}1,25{sp}billones"
    assert formato_cop(950_000, compacto=True) == f"${sp}950.000"


def test_enmascarar_deja_solo_el_final():
    from app.monitoreo_tx.ui.formato import enmascarar
    assert enmascarar("12345678901") == "•••••••8901"
    assert enmascarar(1088007763) == "••••••7763"
    assert enmascarar("123456") == "••••••"   # mostrar 4 de 6 lo revelaría casi entero
    assert enmascarar(None) is None


def test_csv_de_un_cliente(tmp_path):
    from app.monitoreo_tx.etl.excel_loader import ErrorEstructuraExcel, leer_csv_cliente

    ruta = tmp_path / "historial.csv"
    ruta.write_bytes(CSV_CLIENTE.encode("utf-8-sig"))
    hoja = leer_csv_cliente(ruta, "Cliente A")[0]
    assert len(hoja.df) == 4 and hoja.reparadas == 1 and not hoja.rechazos
    reparada = hoja.df.set_index("id_transaccion").loc["tx-3"]
    assert (reparada["beneficiario"], reparada["id_beneficiario"], reparada["monto"]) == (
        "YURI TATIANA ACOSTA", "1096063506", 5145832)
    assert str(hoja.df["fecha"].max()) == "2026-11-12"   # día/mes/año
    with pytest.raises(ErrorEstructuraExcel):
        leer_csv_cliente(ruta, "")


# ---------- Permisos (sin base: se rechaza antes de consultar) ----------
@pytest.mark.parametrize("rol", ["comercial", "consulta", "cic", "agente", "manager_ops", None])
def test_roles_sin_acceso_no_consultan(rol):
    from app.monitoreo_tx.domain.errores import PermisoDenegado
    from app.monitoreo_tx.servicio import MonitoreoService

    srv = MonitoreoService(engine=None)   # si llegara a la base, fallaría con otro error
    user = {"id": 1, "username": "x", "rol": rol}
    with pytest.raises(PermisoDenegado):
        srv.empresas(user)
    with pytest.raises(PermisoDenegado):
        srv.transacciones_filtradas(user, 1, Filtros())
    with pytest.raises(PermisoDenegado):
        srv.cargar_archivo(user, pathlib.Path("x.xlsx"), "x.xlsx")


def test_menu_y_modulo_usan_los_mismos_roles():
    from app.monitoreo_tx.config import ROLES_CARGA, ROLES_MONITOREO
    assert ROLES_MONITOREO == {"super_admin", "admin", "compliance"}
    assert ROLES_CARGA <= ROLES_MONITOREO


# ---------- Sincronización contra PostgreSQL ----------
@pytest.fixture
def excel(tmp_path):
    ruta = tmp_path / "maestro.xlsx"
    with pd.ExcelWriter(ruta) as w:
        _hoja_sucia().to_excel(w, sheet_name="Cliente A", index=False)
        pd.DataFrame([_fila(1, "b-1", 7_000)], columns=COLS).to_excel(w, sheet_name="Cliente B", index=False)
    return ruta


@pytest.fixture
def engine_pg():
    url = os.getenv("TX_TEST_PG_URL")
    if not url:
        pytest.skip("Defina TX_TEST_PG_URL para probar la sincronización contra PostgreSQL")
    from sqlalchemy import create_engine, text
    engine = create_engine(url)
    migracion = pathlib.Path(__file__).resolve().parent.parent / "db" / "migrations" / "035_monitoreo_transaccional.sql"
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS tx_transacciones, tx_sincronizaciones, tx_empresas CASCADE"))
        # La migración 035 referencia clientes (027); en una base vacía basta una mínima
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS clientes (id SERIAL PRIMARY KEY, razon_social TEXT, "
            "nit TEXT, nivel_riesgo TEXT, estado TEXT)"))
        conn.execute(text(migracion.read_text(encoding="utf-8")))
    yield engine
    engine.dispose()


def test_sincronizacion_incremental(excel, tmp_path, engine_pg):
    from app.monitoreo_tx.etl.sync import sincronizar
    from app.monitoreo_tx.repositorio import EmpresasRepo, TransaccionesRepo

    logs = tmp_path / "logs"
    r1 = sincronizar(excel, engine_pg, directorio_logs=logs)
    assert (r1.resultado, r1.insertadas, r1.rechazadas) == ("OK", 8, 2)
    assert r1.archivo_rechazos
    assert r1.empresas_nuevas == ["Cliente A", "Cliente B"]

    # Mismo archivo -> se omite
    assert sincronizar(excel, engine_pg, directorio_logs=logs).resultado == "OMITIDA"

    # Se modifica un estado y se agrega una fila -> 1 actualizada, 1 insertada
    hoja = _hoja_sucia()
    hoja.loc[0, "ESTADO"] = "Retornado"
    hoja.loc[len(hoja)] = _fila(7, "tx-7", 9_000)
    with pd.ExcelWriter(excel) as w:
        hoja.to_excel(w, sheet_name="Cliente A", index=False)
    r3 = sincronizar(excel, engine_pg, directorio_logs=logs, eliminar_faltantes=True)
    assert (r3.insertadas, r3.actualizadas, r3.sin_cambios) == (1, 1, 6)
    assert r3.eliminadas == 1  # Cliente B ya no viene en el archivo

    repo = TransaccionesRepo(engine_pg)
    assert repo.conteo_por_cliente() == {"Cliente A": 8}
    assert "Sin estado" in repo.estados("Cliente A")
    assert len(repo.consultar("Cliente A", Filtros(texto="entreten"))) == 1
    assert len(repo.consultar("Cliente A", Filtros(texto="100%"))) == 0
    assert len(repo.consultar("Cliente A", Filtros(estados=("Aprobado",)))) == 3
    assert repo.consultar("Cliente A", Filtros(estados=())).empty
    # La ficha de Cliente B se conserva aunque ya no tenga transacciones
    assert {e.nombre_reporte for e in EmpresasRepo(engine_pg).listar()} == {"Cliente A", "Cliente B"}


def test_csv_solo_afecta_a_su_empresa(excel, tmp_path, engine_pg):
    from app.monitoreo_tx.etl.sync import sincronizar
    from app.monitoreo_tx.repositorio import TransaccionesRepo

    logs = tmp_path / "logs"
    sincronizar(excel, engine_pg, directorio_logs=logs)
    ruta = tmp_path / "historial.csv"
    ruta.write_bytes(CSV_CLIENTE.encode("utf-8-sig"))
    r = sincronizar(ruta, engine_pg, directorio_logs=logs, cliente="Cliente A", eliminar_faltantes=True)
    assert r.resultado == "OK" and r.insertadas + r.actualizadas == 4 and r.eliminadas > 0
    # Cliente B no viene en el CSV y no se toca
    assert TransaccionesRepo(engine_pg).conteo_por_cliente() == {"Cliente A": 4, "Cliente B": 1}


def test_carga_interrumpida_queda_como_error_y_se_puede_reintentar(excel, tmp_path, engine_pg, monkeypatch):
    from app.monitoreo_tx.etl import sync as modulo_sync
    from app.monitoreo_tx.repositorio import SincronizacionesRepo, TransaccionesRepo

    original = modulo_sync._sincronizar_cliente
    llamadas = {"n": 0}

    def interrumpir_en_la_segunda_hoja(*args, **kwargs):
        llamadas["n"] += 1
        if llamadas["n"] == 2:
            raise KeyboardInterrupt()
        return original(*args, **kwargs)

    monkeypatch.setattr(modulo_sync, "_sincronizar_cliente", interrumpir_en_la_segunda_hoja)
    with pytest.raises(KeyboardInterrupt):
        modulo_sync.sincronizar(excel, engine_pg, directorio_logs=tmp_path)
    ultima = SincronizacionesRepo(engine_pg).listar(1)[0]
    assert ultima["resultado"] == "ERROR" and ultima["insertadas"] == 0
    assert TransaccionesRepo(engine_pg).contar() == 0          # la transacción se deshizo

    monkeypatch.setattr(modulo_sync, "_sincronizar_cliente", original)
    r = modulo_sync.sincronizar(excel, engine_pg, directorio_logs=tmp_path)   # sin --forzar
    assert r.resultado == "OK" and r.insertadas == 8


# ---------- Completitud: numeración consecutiva y saldo corrido ----------
def _cuenta(nos, saldos, montos):
    return pd.DataFrame({"no_registro": nos, "saldo": saldos, "monto_total": montos})


def test_continuidad_completa():
    from app.monitoreo_tx.domain.continuidad import verificar_continuidad
    # Fondeo de 1.000, dos pagos y una devolución: cada saldo = anterior + monto total
    c = verificar_continuidad(_cuenta([1, 2, 3, 4], [1000, 700, 500, 600], [1000, -300, -200, 100]))
    assert c.completa and not c.parcial
    assert (c.no_inicial, c.no_final, c.saldos_verificados) == (1, 4, 3)


def test_continuidad_detecta_huecos_y_descuadres():
    from app.monitoreo_tx.domain.continuidad import verificar_continuidad
    c = verificar_continuidad(_cuenta(
        [1, 2, 5, 6, 7, 9],
        [1000, 700, 400, 350, 999, 100],
        [1000, -300, -100, -50, -50, -10],
    ))
    assert c.faltantes == 3 and c.ejemplos_faltantes == ["3–4", "8"]
    # 5 no se compara (le falta el anterior); 7 no cuadra: 350 - 50 = 300 ≠ 999
    assert c.descuadres_saldo == 1 and c.ejemplos_descuadre == [7]
    assert not c.completa and "faltante" in c.resumen()


def test_continuidad_historial_parcial_y_numeros_repetidos():
    from app.monitoreo_tx.domain.continuidad import verificar_continuidad
    # Exporte que empieza en el 100; el 101 aparece dos veces (movimiento entre bolsillos)
    c = verificar_continuidad(_cuenta([100, 101, 101, 102], [500, 400, 300, 200], [-1, -100, -100, -100]))
    assert c.parcial and c.faltantes == 0
    assert c.descuadres_saldo == 0          # los repetidos no se comparan
    assert verificar_continuidad(_cuenta([], [], [])).movimientos == 0


def test_sincronizacion_registra_la_completitud(excel, tmp_path, engine_pg):
    from app.monitoreo_tx.etl.sync import sincronizar
    from app.monitoreo_tx.repositorio import SincronizacionesRepo

    r = sincronizar(excel, engine_pg, directorio_logs=tmp_path)
    # En la hoja sintética el No. 7 no existe, y el 1 se rechaza (monto inválido):
    # lo guardado empieza en el 2, así que el historial queda marcado como parcial
    a = r.verificacion["Cliente A"]
    assert a["faltantes"] == 1 and a["ejemplos_faltantes"] == ["7"] and a["parcial"]
    assert r.verificacion["Cliente B"]["completa"]
    assert r.faltantes == 1
    assert any("Cliente A" in adv and "faltante" in adv for adv in r.advertencias)
    fila = SincronizacionesRepo(engine_pg).listar(1)[0]
    assert fila["faltantes"] == 1 and "Cliente A" in fila["verificacion"]
