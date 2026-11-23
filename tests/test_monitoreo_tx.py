"""
tests/test_monitoreo_tx.py
Módulo Monitoreo Transaccional (core/monitoreo_tx).

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

from core.monitoreo_tx.domain.entidades import FiltrosTransacciones as Filtros  # noqa: E402
from core.monitoreo_tx.domain.metricas import calcular_kpis  # noqa: E402
from core.monitoreo_tx.etl.excel_loader import limpiar_hoja  # noqa: E402

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
    from core.monitoreo_tx.domain import metricas as m

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

    from core.monitoreo_tx.domain import metricas as m

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
    from core.monitoreo_tx.etl.excel_loader import _limpiar_texto
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
    from core.monitoreo_tx.domain.metricas import top_beneficiarios

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
    from core.monitoreo_tx.formato import formato_cop
    sp = "\u00a0"
    assert formato_cop(1_234_567) == f"${sp}1.234.567"
    assert formato_cop(42_300_000, compacto=True) == f"${sp}42,3{sp}M"
    assert formato_cop(20_382_643_487, compacto=True) == f"${sp}20.383{sp}M"
    assert formato_cop(1_250_000_000_000, compacto=True) == f"${sp}1,25{sp}billones"
    assert formato_cop(950_000, compacto=True) == f"${sp}950.000"


def test_enmascarar_deja_solo_el_final():
    from core.monitoreo_tx.formato import enmascarar
    assert enmascarar("12345678901") == "•••••••8901"
    assert enmascarar(1088007763) == "••••••7763"
    assert enmascarar("123456") == "••••••"   # mostrar 4 de 6 lo revelaría casi entero
    assert enmascarar(None) is None


def test_csv_de_un_cliente(tmp_path):
    from core.monitoreo_tx.etl.excel_loader import ErrorEstructuraExcel, leer_csv_cliente

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
    from core.monitoreo_tx.domain.errores import PermisoDenegado
    from core.monitoreo_tx.servicio import MonitoreoService

    srv = MonitoreoService(engine=None)   # si llegara a la base, fallaría con otro error
    user = {"id": 1, "username": "x", "rol": rol}
    with pytest.raises(PermisoDenegado):
        srv.empresas(user)
    with pytest.raises(PermisoDenegado):
        srv.transacciones_filtradas(user, 1, Filtros())
    with pytest.raises(PermisoDenegado):
        srv.cargar_archivo(user, pathlib.Path("x.xlsx"), "x.xlsx")


def test_menu_y_modulo_usan_los_mismos_roles():
    from core.monitoreo_tx.config import ROLES_CARGA, ROLES_MONITOREO
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
    from sqlalchemy import create_engine
    from tests._esquema import crear_esquema_minimo
    engine = create_engine(url)
    crear_esquema_minimo(engine)   # 035–038 sobre clientes y usuarios mínimos
    yield engine
    engine.dispose()


def test_sincronizacion_incremental(excel, tmp_path, engine_pg):
    from core.monitoreo_tx.etl.sync import sincronizar
    from core.monitoreo_tx.repositorio import EmpresasRepo, TransaccionesRepo

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
    from core.monitoreo_tx.etl.sync import sincronizar
    from core.monitoreo_tx.repositorio import TransaccionesRepo

    logs = tmp_path / "logs"
    sincronizar(excel, engine_pg, directorio_logs=logs)
    ruta = tmp_path / "historial.csv"
    ruta.write_bytes(CSV_CLIENTE.encode("utf-8-sig"))
    r = sincronizar(ruta, engine_pg, directorio_logs=logs, cliente="Cliente A", eliminar_faltantes=True)
    assert r.resultado == "OK" and r.insertadas + r.actualizadas == 4 and r.eliminadas > 0
    # Cliente B no viene en el CSV y no se toca
    assert TransaccionesRepo(engine_pg).conteo_por_cliente() == {"Cliente A": 4, "Cliente B": 1}


def test_carga_interrumpida_queda_como_error_y_se_puede_reintentar(excel, tmp_path, engine_pg, monkeypatch):
    from core.monitoreo_tx.etl import sync as modulo_sync
    from core.monitoreo_tx.repositorio import SincronizacionesRepo, TransaccionesRepo

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
    from core.monitoreo_tx.domain.continuidad import verificar_continuidad
    # Fondeo de 1.000, dos pagos y una devolución: cada saldo = anterior + monto total
    c = verificar_continuidad(_cuenta([1, 2, 3, 4], [1000, 700, 500, 600], [1000, -300, -200, 100]))
    assert c.completa and not c.parcial
    assert (c.no_inicial, c.no_final, c.saldos_verificados) == (1, 4, 3)


def test_continuidad_detecta_huecos_y_descuadres():
    from core.monitoreo_tx.domain.continuidad import verificar_continuidad
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
    from core.monitoreo_tx.domain.continuidad import verificar_continuidad
    # Exporte que empieza en el 100; el 101 aparece dos veces (movimiento entre bolsillos)
    c = verificar_continuidad(_cuenta([100, 101, 101, 102], [500, 400, 300, 200], [-1, -100, -100, -100]))
    assert c.parcial and c.faltantes == 0
    assert c.descuadres_saldo == 0          # los repetidos no se comparan
    assert verificar_continuidad(_cuenta([], [], [])).movimientos == 0


def test_sincronizacion_registra_la_completitud(excel, tmp_path, engine_pg):
    from core.monitoreo_tx.etl.sync import sincronizar
    from core.monitoreo_tx.repositorio import SincronizacionesRepo

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


# ---------- Carga automática desde la nube ----------
class _Resp:
    def __init__(self, status, datos=None, contenido=b""):
        self.status_code, self._datos, self.content, self.text = status, datos, contenido, ""

    def json(self):
        return self._datos


class _GraphFalso:
    """Simula Microsoft Graph: token, carpeta raíz paginada, subcarpetas y descarga."""

    def __init__(self, csv: bytes):
        self.csv, self.llamadas = csv, []
        self.en_la_raiz = True
        self.busqueda = []

    def post(self, url, data=None, timeout=None):
        self.llamadas.append(("POST", url))
        assert data["grant_type"] == "client_credentials"
        return _Resp(200, {"access_token": "tok", "expires_in": 3600})

    def get(self, url, headers=None, timeout=None, allow_redirects=True):
        self.llamadas.append(("GET", url))
        assert headers["Authorization"] == "Bearer tok"
        if "root:/AdamoPay_Datos?" in url:
            if not self.en_la_raiz:
                return _Resp(404, {"error": {"message": "itemNotFound"}})
            return _Resp(200, {"id": "raiz", "name": "AdamoPay_Datos", "folder": {}})
        if "/root/search(" in url:
            return _Resp(200, {"value": self.busqueda})
        if "/items/raiz/children" in url:
            return _Resp(200, {"value": [{"id": "f1", "name": "Cliente A", "folder": {}}],
                               "@odata.nextLink": "https://graph.microsoft.com/v1.0/pagina2"})
        if url.endswith("/pagina2"):
            return _Resp(200, {"value": [{"id": "s1", "name": "suelto.csv", "file": {}},
                                         {"id": "f2", "name": "_descartados", "folder": {}}]})
        if "/items/f1/children" in url:
            return _Resp(200, {"value": [
                {"id": "c1", "name": "2026-11-12_historial.csv", "file": {}, "size": len(self.csv),
                 "cTag": "v1", "lastModifiedDateTime": "2026-11-12T22:00:00Z"},
                {"id": "x1", "name": "notas.docx", "file": {}, "cTag": "v1"},
            ]})
        if "/items/c1/content" in url:
            return _Resp(200, contenido=self.csv)
        return _Resp(404, {"error": {"message": "no existe"}})


def _config_falsa():
    from core.monitoreo_tx.nube.fuentes import ConfigOneDrive
    return ConfigOneDrive(tenant_id="t", client_id="c", client_secret="s", usuario="jorge@empresa.co")


def test_onedrive_lista_subcarpetas_pagina_e_ignora_lo_que_no_aplica(tmp_path):
    from core.monitoreo_tx.nube.fuentes import FuenteOneDrive

    graph = _GraphFalso(CSV_CLIENTE.encode("utf-8-sig"))
    fuente = FuenteOneDrive(_config_falsa(), sesion=graph)
    listado = fuente.listar()
    assert [(a.empresa, a.nombre, a.version) for a in listado.archivos] == [
        ("Cliente A", "2026-11-12_historial.csv", "v1")]
    assert listado.sueltos == ["suelto.csv"]                  # sin empresa: no se carga
    assert listado.ignorados == ["Cliente A/notas.docx"]       # formato no admitido
    assert not any("/items/f2/" in u for _, u in graph.llamadas)   # _descartados no se recorre
    assert sum(1 for m, _ in graph.llamadas if m == "POST") == 1   # el token se reutiliza
    destino = fuente.descargar(listado.archivos[0], tmp_path / "x.csv")
    assert destino.read_bytes() == graph.csv


def test_onedrive_credenciales_rechazadas_dan_error_claro():
    from core.monitoreo_tx.nube.fuentes import ErrorFuente, FuenteOneDrive

    class _Rechazo(_GraphFalso):
        def post(self, url, data=None, timeout=None):
            return _Resp(401, {"error_description": "AADSTS7000215: Invalid client secret"})

    with pytest.raises(ErrorFuente, match="credenciales"):
        FuenteOneDrive(_config_falsa(), sesion=_Rechazo(b"")).listar()


def test_configuracion_onedrive_desde_entorno(monkeypatch):
    from core.monitoreo_tx.nube.fuentes import ConfigOneDrive
    for k in ("TX_ONEDRIVE_TENANT_ID", "TX_ONEDRIVE_CLIENT_ID", "TX_ONEDRIVE_CLIENT_SECRET",
              "TX_ONEDRIVE_USUARIO", "TX_ONEDRIVE_DRIVE_ID", "TX_ONEDRIVE_CARPETA"):
        monkeypatch.delenv(k, raising=False)
    assert ConfigOneDrive.desde_entorno() is None
    monkeypatch.setenv("TX_ONEDRIVE_TENANT_ID", "t")
    monkeypatch.setenv("TX_ONEDRIVE_CLIENT_ID", "c")
    cfg = ConfigOneDrive.desde_entorno()
    assert cfg.delegado and cfg.carpeta == "AdamoPay_Datos"   # sin secreto: inicio de sesión con código
    monkeypatch.setenv("TX_ONEDRIVE_CLIENT_SECRET", "s")
    assert ConfigOneDrive.desde_entorno() is None            # modo aplicación: falta el dueño del drive
    monkeypatch.setenv("TX_ONEDRIVE_USUARIO", "jorge@empresa.co")
    cfg = ConfigOneDrive.desde_entorno()
    assert not cfg.delegado and cfg.usuario == "jorge@empresa.co"


@pytest.fixture
def engine_pg_nube(engine_pg):
    from sqlalchemy import text
    migracion = pathlib.Path(__file__).resolve().parent.parent / "db" / "migrations" / "036_tx_sincronizacion_nube.sql"
    with engine_pg.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS tx_archivos_nube, tx_revisiones_nube, tx_credenciales_nube CASCADE"))
        conn.execute(text(migracion.read_text(encoding="utf-8")))
    return engine_pg


def test_revision_carga_lo_nuevo_una_sola_vez(tmp_path, engine_pg_nube):
    from core.monitoreo_tx.nube.fuentes import FuenteOneDrive
    from core.monitoreo_tx.nube.sincronizacion import revisar, ultimas_revisiones, ultimos_archivos
    from core.monitoreo_tx.repositorio import TransaccionesRepo

    graph = _GraphFalso(CSV_CLIENTE.encode("utf-8-sig"))
    fuente = FuenteOneDrive(_config_falsa(), sesion=graph)

    r1 = revisar(fuente, engine_pg_nube)
    assert (r1.resultado, r1.archivos_vistos, r1.archivos_nuevos, r1.cargados) == ("OK", 1, 1, 1)
    # El CSV sintético no trae saldos encadenados: la verificación lo señala (y no hay huecos)
    assert r1.archivos[0].completitud.startswith("0 faltante")
    assert TransaccionesRepo(engine_pg_nube).conteo_por_cliente() == {"Cliente A": 4}
    assert "suelto" in r1.mensaje

    # Misma versión: no se vuelve a descargar
    descargas = sum(1 for _, u in graph.llamadas if u.endswith("/content"))
    r2 = revisar(fuente, engine_pg_nube)
    assert (r2.archivos_nuevos, r2.cargados) == (0, 0)
    assert sum(1 for _, u in graph.llamadas if u.endswith("/content")) == descargas

    assert [x["resultado"] for x in ultimas_revisiones(engine_pg_nube)] == ["OK", "OK"]
    assert ultimos_archivos(engine_pg_nube)[0]["empresa"] == "Cliente A"


def test_revision_registra_error_de_un_archivo_y_sigue(tmp_path, engine_pg_nube):
    from core.monitoreo_tx.nube.fuentes import FuenteCarpeta
    from core.monitoreo_tx.nube.sincronizacion import revisar

    (tmp_path / "datos" / "Cliente A").mkdir(parents=True)
    (tmp_path / "datos" / "Cliente B").mkdir(parents=True)
    (tmp_path / "datos" / "Cliente A" / "malo.csv").write_text("esto no es un historial", encoding="utf-8")
    (tmp_path / "datos" / "Cliente B" / "bueno.csv").write_bytes(CSV_CLIENTE.encode("utf-8-sig"))
    r = revisar(FuenteCarpeta(tmp_path / "datos"), engine_pg_nube)
    assert r.resultado == "CON_ERRORES" and r.errores == 1 and r.cargados == 1
    assert {x.empresa: x.resultado for x in r.archivos} == {"Cliente A": "ERROR", "Cliente B": "OK"}


def test_dos_revisiones_no_corren_a_la_vez(tmp_path, engine_pg_nube):
    from sqlalchemy import text
    from core.monitoreo_tx.nube.fuentes import FuenteCarpeta
    from core.monitoreo_tx.nube.sincronizacion import LLAVE_BLOQUEO, revisar

    (tmp_path / "vacia").mkdir()
    with engine_pg_nube.connect() as otra:
        otra.execute(text("SELECT pg_advisory_lock(:k)"), {"k": LLAVE_BLOQUEO})
        assert revisar(FuenteCarpeta(tmp_path / "vacia"), engine_pg_nube).resultado == "EN_CURSO"
        otra.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LLAVE_BLOQUEO})
    assert revisar(FuenteCarpeta(tmp_path / "vacia"), engine_pg_nube).resultado == "OK"



# ---------- Modo delegado: inicio de sesión con código ----------
class _GraphDelegado(_GraphFalso):
    """Como _GraphFalso, pero con device code, refresh token rotativo y /me."""

    def __init__(self, csv: bytes):
        super().__init__(csv)
        self.refresh_vigente = "r1"
        self.pendiente = True

    def post(self, url, data=None, timeout=None):
        self.llamadas.append(("POST", url))
        if url.endswith("/devicecode"):
            assert "offline_access" in data["scope"] and "Files.Read" in data["scope"]
            return _Resp(200, {"device_code": "dc", "user_code": "ABCD-1234",
                               "verification_uri": "https://microsoft.com/devicelogin", "expires_in": 900})
        if data["grant_type"].endswith("device_code"):
            if self.pendiente:
                return _Resp(400, {"error": "authorization_pending"})
            return _Resp(200, {"access_token": "tok", "refresh_token": "r1", "expires_in": 3600})
        assert data["grant_type"] == "refresh_token" and "client_secret" not in data
        if data["refresh_token"] != self.refresh_vigente:
            return _Resp(400, {"error": "invalid_grant", "error_description": "AADSTS70008: expired"})
        self.refresh_vigente = "r2"           # Microsoft rota el refresh token
        return _Resp(200, {"access_token": "tok", "refresh_token": "r2", "expires_in": 3600})

    def get(self, url, headers=None, timeout=None, allow_redirects=True):
        if "/me?" in url:
            return _Resp(200, {"userPrincipalName": "jorge@holdingsbpo.co"})
        # modo delegado: solo el drive del usuario conectado (las páginas siguientes las da Graph)
        assert "/me/drive" in url or url.endswith("/pagina2")
        return super().get(url.replace("/me/drive", "/users/x/drive"), headers, timeout, allow_redirects)


def test_conexion_con_codigo_espera_y_luego_entrega_la_cuenta():
    from core.monitoreo_tx.nube.fuentes import ConfigOneDrive, completar_conexion, iniciar_conexion

    cfg = ConfigOneDrive(tenant_id="t", client_id="c")
    graph = _GraphDelegado(b"")
    flujo = iniciar_conexion(cfg, graph)
    assert flujo["user_code"] == "ABCD-1234"
    assert completar_conexion(cfg, flujo["device_code"], graph) is None      # aún no inicia sesión
    graph.pendiente = False
    r = completar_conexion(cfg, flujo["device_code"], graph)
    assert (r["refresh_token"], r["cuenta"]) == ("r1", "jorge@holdingsbpo.co")


def test_delegado_lee_me_drive_y_guarda_el_token_rotado():
    from core.monitoreo_tx.nube.fuentes import ConfigOneDrive, ErrorConexion, FuenteOneDrive

    cfg = ConfigOneDrive(tenant_id="t", client_id="c")
    graph = _GraphDelegado(CSV_CLIENTE.encode("utf-8-sig"))
    guardados = []
    fuente = FuenteOneDrive(cfg, sesion=graph, refresh_token="r1", cuenta="jorge@holdingsbpo.co",
                            al_renovar=guardados.append)
    assert len(fuente.listar().archivos) == 1
    assert guardados == ["r2"]                       # el nuevo refresh token se guarda
    assert "jorge@holdingsbpo.co" in fuente.descripcion()

    with pytest.raises(ErrorConexion):               # sin conexión no se puede crear la fuente
        FuenteOneDrive(cfg, sesion=graph)
    vencida = FuenteOneDrive(cfg, sesion=graph, refresh_token="viejo")
    with pytest.raises(ErrorConexion, match="vuelva a conectar"):
        vencida.listar()


def test_credencial_se_guarda_cifrada_y_se_renueva(engine_pg_nube, monkeypatch):
    from sqlalchemy import text
    from core.monitoreo_tx.nube import credenciales

    monkeypatch.setenv("SECRET_KEY", "x" * 43)
    credenciales.guardar(engine_pg_nube, "refresh-secreto", "jorge@holdingsbpo.co", "jorge")
    with engine_pg_nube.connect() as conn:
        crudo = conn.execute(text("SELECT token_cifrado FROM tx_credenciales_nube")).scalar()
    assert "refresh-secreto" not in crudo                                    # no queda en claro
    assert credenciales.leer(engine_pg_nube)["refresh_token"] == "refresh-secreto"

    credenciales.renovar(engine_pg_nube, "refresh-nuevo")
    assert credenciales.leer(engine_pg_nube)["refresh_token"] == "refresh-nuevo"

    monkeypatch.setenv("SECRET_KEY", "y" * 43)                               # otra clave: no se puede leer
    assert credenciales.leer(engine_pg_nube) is None
    assert credenciales.info(engine_pg_nube)["cuenta"] == "jorge@holdingsbpo.co"
    credenciales.eliminar(engine_pg_nube)
    assert credenciales.info(engine_pg_nube) is None



def test_onedrive_encuentra_la_carpeta_fuera_de_la_raiz():
    from core.monitoreo_tx.nube.fuentes import ErrorFuente, FuenteOneDrive

    graph = _GraphFalso(CSV_CLIENTE.encode("utf-8-sig"))
    graph.en_la_raiz = False
    # OneDrive respalda «Documentos»: la carpeta quedó dentro
    graph.busqueda = [
        {"id": "raiz", "name": "AdamoPay_Datos", "folder": {},
         "parentReference": {"path": "/drive/root:/Documentos/2.%20DESARROLLOS_GITHUB/Documentos"}},
        {"id": "otro", "name": "AdamoPay_Datos_viejo", "folder": {}},        # nombre parecido: no cuenta
        {"id": "arch", "name": "AdamoPay_Datos", "file": {}},                 # un archivo: no cuenta
    ]
    fuente = FuenteOneDrive(_config_falsa(), sesion=graph)
    assert len(fuente.listar().archivos) == 1
    assert fuente.ruta_encontrada == "Documentos/2. DESARROLLOS_GITHUB/Documentos/AdamoPay_Datos"
    assert "Documentos/2. DESARROLLOS_GITHUB" in fuente.descripcion()

    graph.busqueda = []
    with pytest.raises(ErrorFuente, match="Créela en la raíz"):
        FuenteOneDrive(_config_falsa(), sesion=graph).listar()

    graph.busqueda = [{"id": "a", "name": "AdamoPay_Datos", "folder": {}},
                      {"id": "b", "name": "adamopay_datos", "folder": {}}]
    with pytest.raises(ErrorFuente, match="Hay 2 carpetas"):
        FuenteOneDrive(_config_falsa(), sesion=graph).listar()


def test_serie_desde_diario_alinea_periodos_y_solo_cuenta_pagos_exitosos():
    from core.monitoreo_tx.domain import metricas
    from datetime import date
    diario = pd.DataFrame({
        "fecha": [date(2026, 1, 5), date(2026, 1, 5), date(2026, 3, 2)],
        "tipo_transaccion": ["Débito", "Crédito", "Débito"],
        "exitosa": [True, True, False],
        "transacciones": [2, 1, 4], "monto": [100.0, 30.0, 999.0],
    })
    s = metricas.serie_desde_diario(diario, "Mensual", date(2026, 1, 1), date(2026, 3, 31))
    assert len(s) == 3                                   # enero, febrero (vacío) y marzo
    assert s["monto"].tolist() == [100.0, 0.0, 0.0] and s["pagos"].tolist() == [2, 0, 0]
    vacia = metricas.serie_desde_diario(diario.iloc[0:0], "Mensual", date(2026, 1, 1), date(2026, 3, 31))
    assert len(vacia) == 3 and vacia["monto"].sum() == 0
