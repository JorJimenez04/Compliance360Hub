-- ============================================================
-- Compliance360 Hub -- Migración 039
-- Ficha de la organización: qué servicios contrató, a qué régimen
-- pertenece, sus modelos de negocio, su nivel de riesgo y quién es
-- su oficial de cumplimiento.
--
-- Los CÓDIGOS (servicios, régimen, modelos) se definen en
-- core/cumplimiento/catalogo.py y la API los valida contra él: así el
-- catálogo queda versionado en git y la base solo guarda lo elegido.
--
-- Idempotente: ADD COLUMN IF NOT EXISTS / DROP CONSTRAINT IF EXISTS.
-- ============================================================

ALTER TABLE organizaciones
    ADD COLUMN IF NOT EXISTS tipo_persona       TEXT    NOT NULL DEFAULT 'juridica',
    ADD COLUMN IF NOT EXISTS servicios          TEXT[]  NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS modelos_negocio    TEXT[]  NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS regimen            TEXT,
    ADD COLUMN IF NOT EXISTS nivel_riesgo       TEXT    NOT NULL DEFAULT 'Sin calificar',
    ADD COLUMN IF NOT EXISTS fecha_calificacion DATE,
    ADD COLUMN IF NOT EXISTS proxima_revision   DATE,
    -- Oficial principal: alguien del equipo interno (usuarios sin organización)
    ADD COLUMN IF NOT EXISTS oficial_principal_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    -- El suplente puede ser una persona externa a la plataforma
    ADD COLUMN IF NOT EXISTS oficial_suplente   TEXT,
    ADD COLUMN IF NOT EXISTS fecha_designacion  DATE,
    ADD COLUMN IF NOT EXISTS acta_designacion   TEXT;

ALTER TABLE organizaciones DROP CONSTRAINT IF EXISTS organizaciones_tipo_persona_check;
ALTER TABLE organizaciones ADD CONSTRAINT organizaciones_tipo_persona_check
    CHECK (tipo_persona IN ('juridica', 'natural'));

-- Enfoque basado en riesgo: tres niveles (decisión 2026-11-23)
ALTER TABLE organizaciones DROP CONSTRAINT IF EXISTS organizaciones_nivel_riesgo_check;
ALTER TABLE organizaciones ADD CONSTRAINT organizaciones_nivel_riesgo_check
    CHECK (nivel_riesgo IN ('Sin calificar', 'Alto', 'Medio', 'Bajo'));

CREATE INDEX IF NOT EXISTS idx_organizaciones_oficial ON organizaciones (oficial_principal_id);
CREATE INDEX IF NOT EXISTS idx_organizaciones_proxima_revision ON organizaciones (proxima_revision);
