"""
Tablas del módulo en SQLAlchemy Core.

Las crea la migración db/migrations/035_monitoreo_transaccional.sql; aquí solo
se describen para construir consultas sin escribir SQL a mano. Si se cambia
una columna, se cambia primero la migración.
"""

from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, Float, Integer, MetaData, String, Table, Text,
)

metadata = MetaData()

tx_empresas = Table(
    "tx_empresas", metadata,
    Column("id", Integer, primary_key=True),
    Column("nombre_reporte", Text, nullable=False, unique=True),
    Column("cliente_id", Integer),
    Column("activa", Boolean, nullable=False),
    Column("notas", Text),
    Column("created_at", DateTime),
    Column("updated_at", DateTime),
)

tx_transacciones = Table(
    "tx_transacciones", metadata,
    Column("id", BigInteger, primary_key=True),
    Column("cliente", Text, nullable=False),  # nombre de la hoja = tx_empresas.nombre_reporte
    Column("no_registro", Integer, nullable=False),
    Column("id_transaccion", Text, nullable=False),
    Column("fecha", Date, nullable=False),
    Column("hora", String(8)),
    Column("fecha_hora", DateTime),
    Column("tipo_transaccion", Text),
    Column("tipo_identificacion", Text),
    Column("tipo_persona", String(15), nullable=False),
    Column("beneficiario", Text),
    Column("id_beneficiario", Text),
    Column("banco", Text),
    Column("tipo_cuenta", Text),
    Column("numero_cuenta", Text),
    Column("monto", Float, nullable=False),
    Column("comision", Float, nullable=False),
    Column("monto_total", Float),
    Column("saldo", Float),
    Column("estado", Text, nullable=False),
    Column("exitosa", Boolean, nullable=False),
    Column("descripcion", Text),
    Column("referencia_externa", Text),
    Column("exportado_por", Text),
    Column("row_hash", String(20), nullable=False),
    Column("sincronizado_en", DateTime, nullable=False),
)

tx_sincronizaciones = Table(
    "tx_sincronizaciones", metadata,
    Column("id", Integer, primary_key=True),
    Column("iniciado_en", DateTime, nullable=False),
    Column("finalizado_en", DateTime),
    Column("archivo", Text, nullable=False),
    Column("archivo_sha256", String(64)),
    Column("resultado", String(10), nullable=False),
    Column("usuario", Text),
    Column("clientes", Integer),
    Column("filas_leidas", Integer),
    Column("insertadas", Integer),
    Column("actualizadas", Integer),
    Column("sin_cambios", Integer),
    Column("rechazadas", Integer),
    Column("reparadas", Integer),
    Column("eliminadas", Integer),
    Column("mensaje", Text),
    Column("faltantes", Integer),          # números de «No.» ausentes (todas las empresas de la carga)
    Column("descuadres_saldo", Integer),   # movimientos cuyo saldo no cuadra con el anterior
    Column("verificacion", Text),          # JSON: detalle de continuidad por empresa
)

# Ficha KYC del módulo Gestión de Clientes (migración 027); solo lectura desde aquí
clientes = Table(
    "clientes", metadata,
    Column("id", Integer, primary_key=True),
    Column("razon_social", Text),
    Column("nit", Text),
    Column("nivel_riesgo", Text),
    Column("estado", Text),
)
