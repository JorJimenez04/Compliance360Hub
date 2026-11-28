-- ============================================================
-- Compliance360 Hub -- Migración 048
-- Cierre de la fase 2 (decisiones 2026-11-28):
--   1. Carpeta Compliance de cada organización (un solo enlace): la plataforma encuentra
--      por nombre las carpetas de subclientes, aliados bancarios y requerimientos.
--   2. Documentos de cada aliado bancario leídos de su carpeta, y vencimientos de
--      contrato, póliza y licencia (se escriben a mano: el PDF no se lee por dentro).
--   3. Evidencias de cada requerimiento (1. Solicitud, 2. Soportes, 3. Respuesta).
--   4. Clave de origen en los requerimientos creados desde una sugerencia de la plataforma,
--      para no sugerir dos veces lo mismo.
-- La plataforma solo lee OneDrive. Idempotente.
-- ============================================================

ALTER TABLE organizaciones
    ADD COLUMN IF NOT EXISTS carpeta_compliance   TEXT,
    ADD COLUMN IF NOT EXISTS carpeta_drive_id     TEXT,
    ADD COLUMN IF NOT EXISTS carpeta_item_id      TEXT,
    ADD COLUMN IF NOT EXISTS carpeta_nombre       TEXT,
    ADD COLUMN IF NOT EXISTS carpeta_revisada_en  TIMESTAMP,
    ADD COLUMN IF NOT EXISTS carpeta_error        TEXT,
    ADD COLUMN IF NOT EXISTS carpeta_resumen      JSONB;      -- qué encontró la última revisión

-- Cómo se enlazó la carpeta del subcliente: pegada a mano o encontrada en la carpeta Compliance
ALTER TABLE clientes
    ADD COLUMN IF NOT EXISTS carpeta_origen TEXT NOT NULL DEFAULT 'manual';
ALTER TABLE clientes DROP CONSTRAINT IF EXISTS clientes_carpeta_origen_check;
ALTER TABLE clientes ADD CONSTRAINT clientes_carpeta_origen_check CHECK (carpeta_origen IN ('manual', 'compliance'));

ALTER TABLE org_aliados
    ADD COLUMN IF NOT EXISTS carpeta_item_id      TEXT,
    ADD COLUMN IF NOT EXISTS carpeta_web_url      TEXT,
    ADD COLUMN IF NOT EXISTS carpeta_nombre       TEXT,
    ADD COLUMN IF NOT EXISTS carpeta_revisada_en  TIMESTAMP,
    ADD COLUMN IF NOT EXISTS vence_contrato       DATE,
    ADD COLUMN IF NOT EXISTS vence_poliza         DATE,
    ADD COLUMN IF NOT EXISTS vence_licencia       DATE;

CREATE TABLE IF NOT EXISTS org_aliado_documentos (
    id              BIGSERIAL  PRIMARY KEY,
    relacion_id     INTEGER    NOT NULL REFERENCES org_aliados(id) ON DELETE CASCADE,
    codigo          TEXT,                         -- NULL: archivo no reconocido
    item_id         TEXT       NOT NULL,
    nombre_archivo  TEXT       NOT NULL,
    ruta            TEXT,
    web_url         TEXT,
    tamano          BIGINT,
    modificado_en   TIMESTAMP,
    detectado_en    TIMESTAMP  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    asignacion      TEXT       NOT NULL DEFAULT 'auto' CHECK (asignacion IN ('auto', 'manual')),
    asignado_por    TEXT,
    UNIQUE (relacion_id, item_id)
);

ALTER TABLE requerimientos
    ADD COLUMN IF NOT EXISTS carpeta_item_id      TEXT,
    ADD COLUMN IF NOT EXISTS carpeta_web_url      TEXT,       -- encontrada en la carpeta Compliance
    ADD COLUMN IF NOT EXISTS ev_solicitud         INTEGER,    -- archivos en «1. Solicitud» (NULL: sin carpeta)
    ADD COLUMN IF NOT EXISTS ev_soportes          INTEGER,
    ADD COLUMN IF NOT EXISTS ev_respuesta         INTEGER,
    ADD COLUMN IF NOT EXISTS carpeta_revisada_en  TIMESTAMP,
    ADD COLUMN IF NOT EXISTS clave_origen         TEXT;       -- sugerencia que lo originó
CREATE INDEX IF NOT EXISTS idx_requerimientos_clave ON requerimientos (organizacion_id, clave_origen) WHERE clave_origen IS NOT NULL;
