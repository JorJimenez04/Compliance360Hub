"""
tests/test_api.py
API de la nueva interfaz (api/).

Las pruebas de sesión no tocan la base. Las de punta a punta necesitan una
base PostgreSQL de prueba con el esquema completo (python db/sync_db.py) y
datos cargados en Monitoreo Transaccional:

    $env:C360_API_TEST = "1"     # con DATABASE_URL apuntando a esa base
    python -m pytest tests/test_api.py -q
"""

from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://smoke:smoke@localhost:5432/smoke")
os.environ.setdefault("APP_ENV", "development")

from api import seguridad as seg  # noqa: E402


# ---------- Sesión (sin base) ----------
def test_token_firmado_y_verificado(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "k" * 43)
    u = seg.Usuario(id=7, username="ana", nombre="Ana", rol="compliance")
    token = seg.crear_token(u)
    assert seg.leer_token(token) == u
    cuerpo, firma = token.split(".")
    assert seg.leer_token(cuerpo + "." + firma[:-2] + "xx") is None          # firma alterada
    monkeypatch.setenv("SECRET_KEY", "z" * 43)
    assert seg.leer_token(token) is None                                      # otra clave


def test_token_vencido(monkeypatch):
    monkeypatch.setattr(seg, "DURACION_SESION_S", -1)
    assert seg.leer_token(seg.crear_token(seg.Usuario(1, "a", "A", "admin"))) is None


def test_bloqueo_tras_cinco_fallos():
    clave = f"prueba|{time.time()}"
    for _ in range(seg.MAX_FALLOS - 1):
        seg.registrar_fallo(clave)
    assert seg.bloqueado(clave) == 0
    seg.registrar_fallo(clave)
    assert 0 < seg.bloqueado(clave) <= seg.BLOQUEO_S
    seg.limpiar_fallos(clave)
    assert seg.bloqueado(clave) == 0


def test_modulos_segun_rol():
    assert "monitoreo" in seg.modulos_visibles("compliance")
    assert "monitoreo" not in seg.modulos_visibles("comercial")


# ---------- Punta a punta (requiere base de prueba) ----------
requiere_base = pytest.mark.skipif(os.getenv("C360_API_TEST") != "1",
                                   reason="Defina C360_API_TEST=1 con DATABASE_URL de una base de prueba")


@pytest.fixture
def cliente(monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("ADMIN_USERNAME", "admin_prueba")
    monkeypatch.setenv("ADMIN_PASSWORD", "Clave_De_Prueba_2026!")
    from api.main import app
    return TestClient(app)


def _entrar(c) -> None:
    r = c.post("/api/auth/login", json={"username": "admin_prueba", "password": "Clave_De_Prueba_2026!"})
    assert r.status_code == 200, r.text


@requiere_base
def test_sin_sesion_no_hay_datos(cliente):
    assert cliente.get("/api/monitoreo/resumen").status_code == 401
    assert cliente.get("/api/auth/yo").status_code == 401


@requiere_base
def test_login_fallido_y_exitoso(cliente):
    r = cliente.post("/api/auth/login", json={"username": "admin_prueba", "password": "mala"})
    assert r.status_code == 401
    r = cliente.post("/api/auth/login", json={"username": "admin_prueba", "password": "Clave_De_Prueba_2026!"})
    assert r.status_code == 200 and r.json()["rol"] == "admin" and "monitoreo" in r.json()["modulos"]
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert cliente.get("/api/auth/yo").json()["username"] == "admin_prueba"


@requiere_base
def test_cambios_exigen_cabecera_csrf(cliente):
    _entrar(cliente)
    assert cliente.post("/api/monitoreo/nube/desconectar").status_code == 403
    assert cliente.post("/api/auth/logout", headers={"X-C360": "1"}).status_code == 200
    assert cliente.get("/api/auth/yo").status_code == 401


@requiere_base
def test_tablero_y_transacciones(cliente):
    _entrar(cliente)
    res = cliente.get("/api/monitoreo/resumen").json()
    assert res["empresas"], "la base de prueba debe tener transacciones cargadas"
    e = max(res["empresas"], key=lambda x: x["transacciones"] or 0)
    op = cliente.get(f"/api/monitoreo/empresas/{e['id']}/opciones").json()
    params = {"desde": op["fecha_min"], "hasta": op["fecha_max"]}
    t = cliente.get(f"/api/monitoreo/empresas/{e['id']}/tablero", params=params).json()
    assert not t["vacio"] and t["kpis"]["total_movimientos"] == e["transacciones"]
    assert t["serie"] and t["composicion"] and len(t["actividad"]["valores"]) == 7
    assert all("•" in (f["id_beneficiario"] or "•") for f in t["ranking_monto"])     # documentos enmascarados

    p = cliente.get(f"/api/monitoreo/empresas/{e['id']}/transacciones",
                    params={**params, "pagina": 2, "tamano": 20}).json()
    assert p["total"] == e["transacciones"] and len(p["filas"]) == 20
    assert all(f["numero_cuenta"] is None or "•" in f["numero_cuenta"] for f in p["filas"])

    csv = cliente.get(f"/api/monitoreo/empresas/{e['id']}/transacciones.csv", params=params)
    assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")
    assert cliente.get(f"/api/monitoreo/empresas/{e['id']}/riesgo", params=params).json()["scoring"]
    assert cliente.get("/api/monitoreo/empresas/999999/opciones").status_code == 404


@requiere_base
def test_cargas_y_nube(cliente):
    _entrar(cliente)
    assert isinstance(cliente.get("/api/monitoreo/cargas").json()["cargas"], list)
    n = cliente.get("/api/monitoreo/nube").json()
    assert set(n) >= {"configurada", "lista", "revisiones", "archivos"}
    r = cliente.post("/api/monitoreo/cargas", headers={"X-C360": "1"},
                     files={"archivo": ("x.txt", b"hola", "text/plain")})
    assert r.status_code == 400
