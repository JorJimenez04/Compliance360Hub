-- ============================================================
-- Compliance360 Hub -- Migración 035
-- Módulo Monitoreo Transaccional (transacciones de clientes AdamoPay)
-- Idempotente : CREATE TABLE / INDEX IF NOT EXISTS
--
-- tx_empresas       : una fila por hoja del reporte de AdamoPay (una empresa
--                     cliente). Se enlaza con la ficha KYC de clientes.
-- tx_transacciones  : un movimiento del reporte. Clave natural
--                     (cliente, no_registro, id_transaccion), donde cliente es
--                     el nombre de la hoja (= tx_empresas.nombre_reporte).
-- tx_sincronizaciones: bitácora de cada carga (archivo, SHA-256, conteos).
-- ============================================================

CREATE TABLE IF NOT EXISTS tx_empresas (
    id              SERIAL       PRIMARY KEY,
    nombre_reporte  TEXT         NOT NULL UNIQUE,
    cliente_id      INTEGER      REFERENCES clientes(id) ON DELETE SET NULL,
    activa          BOOLEAN      NOT NULL DEFAULT TRUE,
    notas           TEXT,
    created_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tx_empresas_cliente
    ON tx_empresas (cliente_id);

CREATE TABLE IF NOT EXISTS tx_transacciones (
    id                  BIGSERIAL        PRIMARY KEY,
    cliente             TEXT             NOT NULL,
    no_registro         INTEGER          NOT NULL,
    id_transaccion      TEXT             NOT NULL,
    fecha               DATE             NOT NULL,
    hora                VARCHAR(8),
    fecha_hora          TIMESTAMP,
    tipo_transaccion    TEXT,
    tipo_identificacion TEXT,
    tipo_persona        VARCHAR(15)      NOT NULL,
    beneficiario        TEXT,
    id_beneficiario     TEXT,
    banco               TEXT,
    tipo_cuenta         TEXT,
    numero_cuenta       TEXT,
    monto               DOUBLE PRECISION NOT NULL,
    comision            DOUBLE PRECISION NOT NULL DEFAULT 0,
    monto_total         DOUBLE PRECISION,
    saldo               DOUBLE PRECISION,
    estado              TEXT             NOT NULL,
    exitosa             BOOLEAN          NOT NULL,
    descripcion         TEXT,
    referencia_externa  TEXT,
    exportado_por       TEXT,
    row_hash            VARCHAR(20)      NOT NULL,
    sincronizado_en     TIMESTAMP        NOT NULL,
    CONSTRAINT uq_tx_natural UNIQUE (cliente, no_registro, id_transaccion)
);

CREATE INDEX IF NOT EXISTS idx_tx_cliente_fecha
    ON tx_transacciones (cliente, fecha);
CREATE INDEX IF NOT EXISTS idx_tx_cliente_estado
    ON tx_transacciones (cliente, estado);
CREATE INDEX IF NOT EXISTS idx_tx_id_transaccion
    ON tx_transacciones (id_transaccion);
CREATE INDEX IF NOT EXISTS idx_tx_id_beneficiario
    ON tx_transacciones (id_beneficiario);

CREATE TABLE IF NOT EXISTS tx_sincronizaciones (
    id              SERIAL     PRIMARY KEY,
    iniciado_en     TIMESTAMP  NOT NULL,
    finalizado_en   TIMESTAMP,
    archivo         TEXT       NOT NULL,
    archivo_sha256  VARCHAR(64),
    resultado       VARCHAR(10) NOT NULL CHECK (resultado IN ('OK','OMITIDA','ERROR')),
    usuario         TEXT,
    clientes        INTEGER    NOT NULL DEFAULT 0,
    filas_leidas    INTEGER    NOT NULL DEFAULT 0,
    insertadas      INTEGER    NOT NULL DEFAULT 0,
    actualizadas    INTEGER    NOT NULL DEFAULT 0,
    sin_cambios     INTEGER    NOT NULL DEFAULT 0,
    rechazadas      INTEGER    NOT NULL DEFAULT 0,
    reparadas       INTEGER    NOT NULL DEFAULT 0,
    eliminadas      INTEGER    NOT NULL DEFAULT 0,
    mensaje         TEXT
);

CREATE INDEX IF NOT EXISTS idx_tx_sinc_resultado
    ON tx_sincronizaciones (resultado, id);

CREATE OR REPLACE FUNCTION fn_tx_empresas_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_tx_empresas_updated_at ON tx_empresas;
CREATE TRIGGER trg_tx_empresas_updated_at
    BEFORE UPDATE ON tx_empresas
    FOR EACH ROW EXECUTE FUNCTION fn_tx_empresas_updated_at();

-- Verificación de completitud de cada carga (numeración consecutiva y saldo corrido).
-- ADD COLUMN IF NOT EXISTS: aplica también a bases donde la tabla ya existía.
ALTER TABLE tx_sincronizaciones ADD COLUMN IF NOT EXISTS faltantes        INTEGER NOT NULL DEFAULT 0;
ALTER TABLE tx_sincronizaciones ADD COLUMN IF NOT EXISTS descuadres_saldo INTEGER NOT NULL DEFAULT 0;
ALTER TABLE tx_sincronizaciones ADD COLUMN IF NOT EXISTS verificacion     TEXT;
