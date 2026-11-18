"""
tests/test_cliente.py
Rol externo «cliente»: ve solo Tablero y Transacciones de SUS empresas.

Lo que se protege aquí es lo que no puede fallar:
  - un cliente nunca ve datos de otra empresa (cambiando el id en la URL, por ejemplo);
  - un cliente nunca llega a Riesgo, exportes, cargas, OneDrive ni al enlace con la ficha KYC;
  - cambiar el rol de alguien invalida su sesión.

Casi todo corre sin base de datos. Las pruebas con PostgreSQL usan TX_TEST_PG_URL
(la base indicada se vacía), igual que tests/test_monitoreo_tx.py.
"""

from __future__ import annotations

import os
import pathlib
import time

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://smoke:smoke@localhost:5432/smoke")
os.environ.setdefault("APP_ENV", "development")

from core.monitoreo_tx.domain.entidades import EmpresaVista, FiltrosTransacciones  # noqa: E402
from core.monitoreo_tx.domain.errores import NoEncontrado, PermisoDenegado  # noqa: E402
from core.monitoreo_tx.servicio import MonitoreoService  # noqa: E402

PROPIA = EmpresaVista(id=1, nombre_reporte="Mi Empresa", activa=True, cliente_id=7,
                      razon_social="Mi Empresa SAS", nit="900.111.222-3", nivel_riesgo="Alto")
AJENA = EmpresaVista(id=2, nombre_reporte="Otra Empresa", activa=True)
CLIENTE = {"id": 10, "username": "cli", "rol": "cliente"}
CLIENTE_SIN_EMPRESAS = {"id": 11, "username": "cli2", "rol": "cliente"}
COMPLIANCE = {"id": 1, "username": "ana", "rol": "compliance"}


class RepoEmpresas:
    """Doble del repositorio: dos empresas y una asignación (usuario 10 → empresa 1)."""
    _todas = {1: PROPIA, 2: AJENA}
    _asignadas = {10: {1}}

    def listar(self, solo_activas=False):
        return list(self._todas.values())

    def obtener(self, empresa_id):
        return self._todas.get(empresa_id)

    def ids_de_usuario(self, usuario_id):
        return set(self._asignadas.get(usuario_id, set()))


class RepoCargas:
    def ultima_exitosa(self):
        return None


class RepoTransacciones:
    def conteo_por_cliente(self):
        return {"Mi Empresa": 5, "Otra Empresa": 99}

    def rango_fechas(self, cliente):
        return (None, None)

    def estados(self, cliente):
        return []


@pytest.fixture
def srv():
    s = MonitoreoService(engine=None)
    s.empresas_repo = RepoEmpresas()
    s.transacciones = RepoTransacciones()
    s.sincronizaciones = RepoCargas()
    return s


# ---------- Alcance por empresa (servicio) ----------
def test_cliente_solo_lista_sus_empresas(srv):
    assert [e.id for e in srv.empresas(CLIENTE)] == [1]
    assert srv.empresas(CLIENTE_SIN_EMPRESAS) == []


def test_interno_ve_todas_las_empresas(srv):
    assert {e.id for e in srv.empresas(COMPLIANCE)} == {1, 2}


def test_cliente_accede_a_su_empresa(srv):
    assert srv.opciones_filtro(CLIENTE, 1).tiene_datos is False   # llega a la consulta (sin datos de prueba)


def test_empresa_ajena_e_inexistente_se_ven_igual(srv):
    """No se confirma al cliente que otra empresa exista: mismo error y mismo mensaje."""
    with pytest.raises(NoEncontrado) as ajena:
        srv.opciones_filtro(CLIENTE, 2)
    with pytest.raises(NoEncontrado) as inexistente:
        srv.opciones_filtro(CLIENTE, 999)
    assert str(ajena.value) == str(inexistente.value)


@pytest.mark.parametrize("operacion", [
    lambda s, u: s.transacciones_filtradas(u, 2, FiltrosTransacciones()),
    lambda s, u: s.kpis_periodo_anterior(u, 2, FiltrosTransacciones()),
    lambda s, u: s.opciones_filtro(u, 2),
])
def test_cliente_no_lee_empresas_ajenas(srv, operacion):
    with pytest.raises(NoEncontrado):
        operacion(srv, CLIENTE)
    with pytest.raises(NoEncontrado):
        operacion(srv, CLIENTE_SIN_EMPRESAS)


def test_conteo_solo_de_sus_empresas(srv):
    assert srv.conteo_por_empresa(CLIENTE) == {"Mi Empresa": 5}
    assert srv.conteo_por_empresa(COMPLIANCE) == {"Mi Empresa": 5, "Otra Empresa": 99}


# ---------- Lo interno nunca llega al cliente (servicio) ----------
@pytest.mark.parametrize("operacion", [
    lambda s, u: s.evaluar_riesgo(u, 1, FiltrosTransacciones()),
    lambda s, u: s.csv_transacciones(u, 1, FiltrosTransacciones()),
    lambda s, u: s.continuidad(u, 1),
    lambda s, u: s.bitacora(u),
    lambda s, u: s.estado_nube(u),
    lambda s, u: s.enlazar_cliente(u, 1, 5),
    lambda s, u: s.cambiar_estado(u, 1, False),
    lambda s, u: s.clientes_disponibles(u),
])
def test_cliente_no_accede_a_funciones_internas(srv, operacion):
    with pytest.raises(PermisoDenegado):
        operacion(srv, CLIENTE)


def test_el_rol_cliente_no_entra_a_streamlit_ni_a_las_funciones_de_carga():
    from core.monitoreo_tx.config import ROL_CLIENTE, ROLES_CARGA, ROLES_CONSULTA, ROLES_MONITOREO
    assert ROL_CLIENTE not in ROLES_MONITOREO     # el menú de Streamlit usa ROLES_MONITOREO
    assert ROL_CLIENTE not in ROLES_CARGA
    assert ROLES_CONSULTA == ROLES_MONITOREO | {ROL_CLIENTE}


# ---------- Sesión ----------
def test_modulos_del_cliente():
    from api import seguridad as seg
    assert seg.modulos_visibles("cliente") == ["monitoreo"]          # sin auditoría
    assert "auditoria" in seg.modulos_visibles("compliance")


def test_sesion_del_cliente_dura_menos(monkeypatch):
    from api import seguridad as seg
    monkeypatch.setenv("SECRET_KEY", "k" * 43)
    assert seg.duracion_sesion("cliente") <= 3600
    assert seg.duracion_sesion("compliance") == seg.DURACION_SESION_S
    antes = time.time()
    token = seg.crear_token(seg.Usuario(10, "cli", "Cli", "cliente"))
    import json
    cuerpo = token.split(".")[0]
    datos = json.loads(seg._unb64(cuerpo))
    assert datos["exp"] - antes <= seg.DURACION_SESION_CLIENTE_S + 5
    assert seg.opciones_cookie("cliente")["max_age"] == seg.duracion_sesion("cliente")


class _Resultado:
    def __init__(self, fila):
        self._fila = fila

    def first(self):
        return self._fila


class _Conexion:
    def __init__(self, fila):
        self._fila = fila

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, *a, **k):
        return _Resultado(self._fila)


class _Motor:
    def __init__(self, fila):
        self._fila = fila

    def connect(self):
        return _Conexion(self._fila)


@pytest.mark.parametrize("rol_en_base, vigente", [("cliente", True), ("compliance", False), (None, False)])
def test_cambiar_el_rol_invalida_la_sesion(monkeypatch, rol_en_base, vigente):
    """La cookie lleva el rol de cuando se inició sesión; si en la base cambió (o se desactivó), deja de valer."""
    from api import seguridad as seg
    import db.database as bd
    monkeypatch.setattr(bd, "engine", _Motor(None if rol_en_base is None else (rol_en_base,)))
    assert seg.sigue_activo(seg.Usuario(10, "cli", "Cli", "cliente")) is vigente


# ---------- API: rutas internas cerradas al cliente ----------
# Sin cliente HTTP: se evalúa la dependencia de rol que cada ruta declara y se llaman
# las funciones de ruta directamente, que es donde se decide qué ve cada quien.
from fastapi import HTTPException  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402

from api import seguridad as seg  # noqa: E402

U_CLIENTE = seg.Usuario(10, "cli", "Cli", "cliente")
U_COMPLIANCE = seg.Usuario(1, "ana", "Ana", "compliance")


def _dependencia_de_rol(metodo: str, ruta: str):
    """La dependencia de rol (requiere_roles) de una ruta: es la primera que declara."""
    from api.rutas.monitoreo import router
    for r in router.routes:
        if isinstance(r, APIRoute) and r.path == ruta and metodo.upper() in r.methods:
            return r.dependant.dependencies[0].call
    raise AssertionError(f"No existe la ruta {metodo.upper()} {ruta}")


RUTAS_INTERNAS = [
    ("get", "/api/monitoreo/empresas/{empresa_id}/riesgo"),
    ("get", "/api/monitoreo/empresas/{empresa_id}/transacciones.csv"),
    ("get", "/api/monitoreo/cargas"),
    ("get", "/api/monitoreo/nube"),
    ("get", "/api/monitoreo/empresas"),
    ("patch", "/api/monitoreo/empresas/{empresa_id}"),
    ("post", "/api/monitoreo/cargas"),
    ("post", "/api/monitoreo/nube/sincronizar"),
    ("post", "/api/monitoreo/nube/conectar"),
    ("post", "/api/monitoreo/nube/completar"),
    ("post", "/api/monitoreo/nube/desconectar"),
]
RUTAS_DEL_CLIENTE = [
    ("get", "/api/monitoreo/resumen"),
    ("get", "/api/monitoreo/empresas/{empresa_id}/opciones"),
    ("get", "/api/monitoreo/empresas/{empresa_id}/tablero"),
    ("get", "/api/monitoreo/empresas/{empresa_id}/transacciones"),
]


@pytest.mark.parametrize("metodo, ruta", RUTAS_INTERNAS)
def test_rutas_internas_responden_403_al_cliente(metodo, ruta):
    dep = _dependencia_de_rol(metodo, ruta)
    with pytest.raises(HTTPException) as e:
        dep(u=U_CLIENTE)
    assert e.value.status_code == 403
    assert dep(u=U_COMPLIANCE) == U_COMPLIANCE      # el equipo interno sigue entrando


@pytest.mark.parametrize("metodo, ruta", RUTAS_DEL_CLIENTE)
def test_rutas_del_cliente_le_dejan_pasar(metodo, ruta):
    dep = _dependencia_de_rol(metodo, ruta)
    assert dep(u=U_CLIENTE) == U_CLIENTE
    with pytest.raises(HTTPException) as e:          # pero no a quien no tiene ningún rol de consulta
        dep(u=seg.Usuario(5, "x", "X", "comercial"))
    assert e.value.status_code == 403


def test_no_hay_rutas_de_monitoreo_sin_clasificar():
    """Si alguien agrega una ruta nueva, este test obliga a decidir si el cliente la ve o no."""
    from api.rutas.monitoreo import router
    conocidas = {(m.upper(), r) for m, r in RUTAS_INTERNAS + RUTAS_DEL_CLIENTE}
    reales = {(m, r.path) for r in router.routes if isinstance(r, APIRoute) for m in r.methods if m != "HEAD"}
    assert reales == conocidas


@pytest.fixture
def rutas(monkeypatch, srv):
    import api.rutas.monitoreo as modulo
    monkeypatch.setattr(modulo, "servicio", lambda: srv)
    monkeypatch.setattr(modulo, "registrar_auditoria", lambda *a, **k: None)
    return modulo


@pytest.mark.parametrize("llamada", [
    lambda r, eid: r.opciones(eid, u=U_CLIENTE),
    lambda r, eid: r.tablero(eid, None, None, None, "", None, u=U_CLIENTE),
    lambda r, eid: r.transacciones(eid, None, None, None, "", 1, 50, u=U_CLIENTE),
])
@pytest.mark.parametrize("empresa_id", [2, 999])
def test_empresa_ajena_responde_404_al_cliente(rutas, llamada, empresa_id):
    with pytest.raises(HTTPException) as e:
        llamada(rutas, empresa_id)
    assert e.value.status_code == 404


def test_resumen_del_cliente_no_trae_datos_internos(rutas):
    datos = rutas.resumen(u=U_CLIENTE)
    assert [e["id"] for e in datos["empresas"]] == [1]
    e = datos["empresas"][0]
    assert e["nivel_riesgo"] is None and e["nit"] is None and e["cliente_id"] is None
    assert e["razon_social"] is None and e["enlazada"] is False
    assert datos["puede_cargar"] is False
    assert "Alto" not in str(datos) and "900.111.222-3" not in str(datos)


def test_resumen_interno_conserva_el_detalle(rutas):
    datos = rutas.resumen(u=U_COMPLIANCE)
    assert {e["id"] for e in datos["empresas"]} == {1, 2}
    propia = next(e for e in datos["empresas"] if e["id"] == 1)
    assert propia["nivel_riesgo"] == "Alto" and propia["nit"] == "900.111.222-3"


def test_perfil_del_cliente_solo_monitoreo():
    from api.rutas.auth import _perfil
    p = _perfil(U_CLIENTE)
    assert p["modulos"] == ["monitoreo"] and p["rol"] == "cliente"


def test_la_consulta_del_cliente_queda_auditada(monkeypatch, rutas):
    registros = []
    monkeypatch.setattr(rutas, "registrar_auditoria", lambda *a, **k: registros.append((a, k)))
    rutas._auditar_consulta(U_CLIENTE, 1, "el tablero")
    rutas._auditar_consulta(U_COMPLIANCE, 1, "el tablero")      # los internos no generan este registro
    assert len(registros) == 1 and registros[0][0][1] == "READ"


# ---------- Contra PostgreSQL (TX_TEST_PG_URL) ----------
@pytest.fixture
def engine_pg():
    url = os.getenv("TX_TEST_PG_URL")
    if not url:
        pytest.skip("Defina TX_TEST_PG_URL para probar contra PostgreSQL")
    from sqlalchemy import create_engine, text
    engine = create_engine(url)
    base = pathlib.Path(__file__).resolve().parent.parent / "db" / "migrations"
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS usuario_empresas, tx_transacciones, tx_sincronizaciones, "
                          "tx_empresas, usuarios, clientes CASCADE"))
        conn.execute(text("CREATE TABLE clientes (id SERIAL PRIMARY KEY, razon_social TEXT, nit TEXT, "
                          "nivel_riesgo TEXT, estado TEXT)"))
        conn.execute(text("CREATE TABLE usuarios (id SERIAL PRIMARY KEY, username TEXT UNIQUE, "
                          "nombre_completo TEXT, email TEXT, password_hash TEXT, rol TEXT, activo INTEGER DEFAULT 1)"))
        conn.execute(text((base / "035_monitoreo_transaccional.sql").read_text(encoding="utf-8")))
        conn.execute(text((base / "037_rol_cliente.sql").read_text(encoding="utf-8")))
    yield engine
    engine.dispose()


def test_asignacion_y_alcance_contra_postgres(engine_pg):
    from sqlalchemy import text
    from core.monitoreo_tx.repositorio import EmpresasRepo
    with engine_pg.begin() as conn:
        conn.execute(text("INSERT INTO tx_empresas (nombre_reporte) VALUES ('Mi Empresa'), ('Otra Empresa')"))
        conn.execute(text("INSERT INTO usuarios (username, rol) VALUES ('cli', 'cliente')"))
        ids = {r[1]: r[0] for r in conn.execute(text("SELECT id, nombre_reporte FROM tx_empresas"))}
        uid = conn.execute(text("SELECT id FROM usuarios WHERE username = 'cli'")).scalar_one()
        conn.execute(text("INSERT INTO usuario_empresas (usuario_id, empresa_id) VALUES (:u, :e)"),
                     {"u": uid, "e": ids["Mi Empresa"]})

    srv = MonitoreoService(engine_pg)
    user = {"id": uid, "username": "cli", "rol": "cliente"}
    assert EmpresasRepo(engine_pg).ids_de_usuario(uid) == {ids["Mi Empresa"]}
    assert [e.nombre_reporte for e in srv.empresas(user)] == ["Mi Empresa"]
    with pytest.raises(NoEncontrado):
        srv.opciones_filtro(user, ids["Otra Empresa"])


def test_la_base_acepta_el_rol_cliente_y_rechaza_uno_inventado(engine_pg):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    with engine_pg.begin() as conn:
        conn.execute(text("INSERT INTO usuarios (username, rol) VALUES ('ok', 'cliente')"))
    with pytest.raises(IntegrityError):
        with engine_pg.begin() as conn:
            conn.execute(text("INSERT INTO usuarios (username, rol) VALUES ('mal', 'rol_inventado')"))
