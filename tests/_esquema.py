"""Esquema mínimo de PostgreSQL para las pruebas del backend (api/ y core/).

Las pruebas no levantan las 38 migraciones de la app completa: crean versiones
mínimas de `clientes` y `usuarios` (las tablas de la app Streamlit que el backend
usa) y aplican, tal cual, las migraciones del módulo y de multi-organización.
Así se prueba el SQL real de esas migraciones.

La base indicada en TX_TEST_PG_URL se VACÍA.
"""

from __future__ import annotations

import pathlib

from sqlalchemy import Engine, text

MIGRACIONES = pathlib.Path(__file__).resolve().parent.parent / "db" / "migrations"
DEL_MODULO = ("035_monitoreo_transaccional.sql", "036_tx_sincronizacion_nube.sql",
              "037_rol_cliente.sql", "038_organizaciones.sql")


def crear_esquema_minimo(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(
            "DROP TABLE IF EXISTS usuario_empresas, tx_archivos_nube, tx_revisiones_nube, tx_credenciales_nube, "
            "tx_transacciones, tx_sincronizaciones, tx_empresas, usuarios, clientes, organizaciones CASCADE"))
        conn.execute(text("CREATE TABLE clientes (id SERIAL PRIMARY KEY, razon_social TEXT, nit TEXT UNIQUE, "
                          "nivel_riesgo TEXT, estado TEXT)"))
        conn.execute(text("CREATE TABLE usuarios (id SERIAL PRIMARY KEY, username TEXT UNIQUE, "
                          "nombre_completo TEXT, email TEXT UNIQUE, password_hash TEXT, rol TEXT, "
                          "activo INTEGER DEFAULT 1, ultimo_acceso TIMESTAMP, "
                          "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"))
        for nombre in DEL_MODULO:
            conn.execute(text((MIGRACIONES / nombre).read_text(encoding="utf-8")))


def id_adamo(engine: Engine) -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT id FROM organizaciones WHERE lower(nombre) = 'adamo'")).scalar_one()
