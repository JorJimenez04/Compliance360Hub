"""Esquema mínimo de PostgreSQL para las pruebas del backend (api/ y core/).

Las pruebas no levantan todas las migraciones de la app completa: crean una versión
mínima de `usuarios` y aplican, tal cual, la de `clientes` (027), las del módulo de
monitoreo, multi-organización, ficha y alertas, y las del cliente (028–032).
Así se prueba el SQL real de esas migraciones.

La base indicada en TX_TEST_PG_URL se VACÍA.
"""

from __future__ import annotations

import pathlib

from sqlalchemy import Engine, text

MIGRACIONES = pathlib.Path(__file__).resolve().parent.parent / "db" / "migrations"
DEL_MODULO = ("027_clientes.sql", "028_cliente_personas.sql", "029_cliente_contratos.sql", "030_contrato_servicios.sql",
              "031_cliente_documentos.sql", "032_cliente_historial_riesgo.sql", "035_monitoreo_transaccional.sql", "036_tx_sincronizacion_nube.sql",
              "037_rol_cliente.sql", "038_organizaciones.sql", "039_ficha_organizacion.sql",
              "040_clientes_alertas.sql", "041_actividades_ciiu.sql", "042_documentacion_onedrive.sql", "043_rol_director_cumplimiento.sql",
              "044_eliminar_perfiles_anteriores.sql",
              "045_aliados_bancarios.sql",
              "046_requerimientos.sql",
              "047_tablero_reportes_uiaf.sql",
              "048_carpeta_compliance.sql")


def crear_esquema_minimo(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(
            "DROP TABLE IF EXISTS org_aliado_documentos, reportes_uiaf, requerimiento_beneficiarios, requerimiento_eventos, requerimientos, org_aliados_historial, org_aliados, aliados_bancarios, cliente_historial_riesgo, cliente_documentos, contrato_servicios, cliente_contratos, cliente_personas, cmp_documentos, cmp_beneficiarios_expediente, cmp_alerta_eventos, cmp_alertas, usuario_empresas, tx_archivos_nube, tx_revisiones_nube, tx_credenciales_nube, "
            "tx_transacciones, tx_sincronizaciones, tx_empresas, usuarios, clientes, organizaciones CASCADE"))
        conn.execute(text("CREATE TABLE usuarios (id SERIAL PRIMARY KEY, username TEXT UNIQUE, "
                          "nombre_completo TEXT, email TEXT UNIQUE, password_hash TEXT, rol TEXT, "
                          "activo INTEGER DEFAULT 1, ultimo_acceso TIMESTAMP, "
                          "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"))
        for nombre in DEL_MODULO:
            conn.execute(text((MIGRACIONES / nombre).read_text(encoding="utf-8")))


def id_adamo(engine: Engine) -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT id FROM organizaciones WHERE lower(nombre) = 'adamo'")).scalar_one()
