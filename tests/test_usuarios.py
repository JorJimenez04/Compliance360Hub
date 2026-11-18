"""Restablecer la clave de un cliente: solo el super_admin, solo clientes, clave visible una vez.

Las pruebas con base usan PostgreSQL real (TX_TEST_PG_URL); el resto corre sin base.
"""

from __future__ import annotations

import os
import pathlib

import bcrypt
import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

pytest.importorskip("sqlalchemy")

from api import seguridad as seg  # noqa: E402
from api.claves import clave_temporal, hash_clave  # noqa: E402
from api.rutas import usuarios as ru  # noqa: E402


def _dependencia(ruta: str, metodo: str):
    for r in ru.router.routes:
        if isinstance(r, APIRoute) and r.path == ruta and metodo in r.methods:
            return next(d.call for d in r.dependant.dependencies if d.call.__name__ == "_dep")
    raise AssertionError(f"Falta la ruta {metodo} {ruta}")


RUTAS = [("/api/usuarios/clientes", "GET"), ("/api/usuarios/clientes/{usuario_id}/restablecer-clave", "POST")]


@pytest.mark.parametrize("rol", ["admin", "compliance", "cliente", "agente", "manager_ops", "cic"])
@pytest.mark.parametrize("ruta, metodo", RUTAS)
def test_solo_el_super_admin_entra(rol, ruta, metodo):
    dep = _dependencia(ruta, metodo)
    with pytest.raises(HTTPException) as e:
        dep(seg.Usuario(5, "x", "X", rol))
    assert e.value.status_code == 403


@pytest.mark.parametrize("ruta, metodo", RUTAS)
def test_el_super_admin_pasa(ruta, metodo):
    u = seg.Usuario(1, "jefe", "Jefe", "super_admin")
    assert _dependencia(ruta, metodo)(u) is u


def test_el_menu_de_usuarios_solo_lo_ve_el_super_admin():
    assert "usuarios" in seg.modulos_visibles("super_admin")
    for rol in ("admin", "compliance", "cliente"):
        assert "usuarios" not in seg.modulos_visibles(rol)


def test_clave_temporal_es_fuerte_y_el_hash_la_verifica():
    claves = {clave_temporal() for _ in range(50)}
    assert len(claves) == 50
    for c in claves:
        assert len(c) == 16 and any(x.islower() for x in c) and any(x.isupper() for x in c) and any(x.isdigit() for x in c)
    assert bcrypt.checkpw(b"abc", hash_clave("abc").encode())


# ---------- Contra PostgreSQL ----------
@pytest.fixture
def pg(monkeypatch):
    url = os.getenv("TX_TEST_PG_URL")
    if not url:
        pytest.skip("Defina TX_TEST_PG_URL para probar contra PostgreSQL")
    from sqlalchemy import create_engine, text
    import db.database as bd
    engine = create_engine(url)
    base = pathlib.Path(__file__).resolve().parent.parent / "db" / "migrations"
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS usuario_empresas, tx_transacciones, tx_sincronizaciones, "
                          "tx_empresas, usuarios, clientes CASCADE"))
        conn.execute(text("CREATE TABLE clientes (id SERIAL PRIMARY KEY, razon_social TEXT, nit TEXT, "
                          "nivel_riesgo TEXT, estado TEXT)"))
        conn.execute(text("CREATE TABLE usuarios (id SERIAL PRIMARY KEY, username TEXT UNIQUE, "
                          "nombre_completo TEXT, email TEXT, password_hash TEXT, rol TEXT, activo INTEGER DEFAULT 1, "
                          "ultimo_acceso TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"))
        conn.execute(text((base / "035_monitoreo_transaccional.sql").read_text(encoding="utf-8")))
        conn.execute(text((base / "037_rol_cliente.sql").read_text(encoding="utf-8")))
        conn.execute(text("INSERT INTO tx_empresas (nombre_reporte) VALUES ('Mi Empresa')"))
        conn.execute(text("INSERT INTO usuarios (username, nombre_completo, rol, password_hash, activo) VALUES "
                          "('cli', 'Cliente Uno', 'cliente', 'viejo', 0), ('interno', 'Interno', 'compliance', 'intacto', 1)"))
        conn.execute(text("INSERT INTO usuario_empresas SELECT u.id, e.id, now() FROM usuarios u, tx_empresas e "
                          "WHERE u.username = 'cli'"))
    monkeypatch.setattr(bd, "engine", engine)
    registros = []
    monkeypatch.setattr(seg, "auditar", lambda *a, **k: registros.append((a, k)))
    yield engine, registros
    engine.dispose()


class _Peticion:
    headers: dict = {}
    client = None


def _id(engine, username):
    from sqlalchemy import text
    with engine.connect() as c:
        return c.execute(text("SELECT id FROM usuarios WHERE username = :u"), {"u": username}).scalar_one()


def test_listar_clientes_trae_solo_clientes_con_sus_empresas(pg):
    engine, _ = pg
    jefe = seg.Usuario(1, "jefe", "Jefe", "super_admin")
    lista = ru.listar_clientes(jefe)["clientes"]
    assert [c["username"] for c in lista] == ["cli"]
    assert lista[0]["empresas"] == "Mi Empresa" and lista[0]["activo"] is False


def test_restablecer_cambia_la_clave_reactiva_y_audita(pg):
    from sqlalchemy import text
    engine, registros = pg
    jefe = seg.Usuario(1, "jefe", "Jefe", "super_admin")
    r = ru.restablecer_clave(_id(engine, "cli"), _Peticion(), jefe)
    assert r["username"] == "cli" and len(r["clave_temporal"]) == 16
    with engine.connect() as c:
        h, activo = c.execute(text("SELECT password_hash, activo FROM usuarios WHERE username = 'cli'")).one()
    assert bcrypt.checkpw(r["clave_temporal"].encode(), h.encode())   # en la base solo queda el hash
    assert r["clave_temporal"] not in h and activo == 1
    assert len(registros) == 1 and registros[0][0][1] == "UPDATE"
    assert r["clave_temporal"] not in str(registros)                    # la clave no llega a la auditoría


def test_no_se_puede_tocar_a_un_usuario_interno_ni_inexistente(pg):
    from sqlalchemy import text
    engine, registros = pg
    jefe = seg.Usuario(1, "jefe", "Jefe", "super_admin")
    for uid in (_id(engine, "interno"), 999999):
        with pytest.raises(HTTPException) as e:
            ru.restablecer_clave(uid, _Peticion(), jefe)
        assert e.value.status_code == 404
    with engine.connect() as c:
        assert c.execute(text("SELECT password_hash FROM usuarios WHERE username = 'interno'")).scalar_one() == "intacto"
    assert registros == []
