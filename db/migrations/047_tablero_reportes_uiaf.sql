-- ============================================================
-- Compliance360 Hub -- Migración 047
-- Tablero general de cumplimiento (decisiones 2026-11-28):
--   1. Requerimientos: nuevo origen «director» (los que pide el director de cumplimiento)
--      y los beneficiarios involucrados, con la actividad que registra el equipo.
--   2. Reportes UIAF (ROS, AROS…) cargados en PDF por el oficial, por organización.
--      Reserva legal: solo los ve el equipo interno; nunca el cliente ni la junta.
-- Idempotente.
-- ============================================================

ALTER TABLE requerimientos DROP CONSTRAINT IF EXISTS requerimientos_origen_check;
ALTER TABLE requerimientos ADD CONSTRAINT requerimientos_origen_check
    CHECK (origen IN ('aliado', 'director', 'regulador', 'auditoria', 'oficial', 'otro'));

CREATE TABLE IF NOT EXISTS requerimiento_beneficiarios (
    id               SERIAL   PRIMARY KEY,
    requerimiento_id INTEGER  NOT NULL REFERENCES requerimientos(id) ON DELETE CASCADE,
    id_beneficiario  TEXT,                          -- documento, como viene en las transacciones
    nombre           TEXT     NOT NULL,
    actividad        TEXT,                          -- actividad del beneficiario (la registra el equipo)
    notas            TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_requerimiento_beneficiario
    ON requerimiento_beneficiarios (requerimiento_id, lower(COALESCE(id_beneficiario, nombre)));

CREATE TABLE IF NOT EXISTS reportes_uiaf (
    id                  SERIAL      PRIMARY KEY,
    organizacion_id     INTEGER     NOT NULL REFERENCES organizaciones(id),
    tipo                TEXT        NOT NULL CHECK (tipo IN ('ROS', 'AROS', 'otro')),
    periodo_desde       DATE,
    periodo_hasta       DATE,
    fecha_presentacion  DATE        NOT NULL,
    radicado            TEXT,                       -- número de radicado en SIREL
    cliente_id          INTEGER     REFERENCES clientes(id),   -- subcliente reportado (ROS)
    descripcion         TEXT,
    archivo_nombre      TEXT        NOT NULL,
    archivo_bytes       INTEGER     NOT NULL,
    archivo_sha256      VARCHAR(64) NOT NULL,
    archivo             BYTEA       NOT NULL,
    creado_por          TEXT        NOT NULL,
    creado_en           TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_reporte_uiaf_archivo UNIQUE (organizacion_id, archivo_sha256),
    CONSTRAINT ck_reporte_uiaf_periodo CHECK (periodo_hasta IS NULL OR periodo_desde IS NULL OR periodo_hasta >= periodo_desde)
);
CREATE INDEX IF NOT EXISTS idx_reportes_uiaf_org ON reportes_uiaf (organizacion_id, fecha_presentacion DESC);
