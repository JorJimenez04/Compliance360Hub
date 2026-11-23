-- ============================================================
-- Compliance360 Hub -- Migración 040
-- Compliance de los clientes de cada organización, alimentado por el
-- monitoreo transaccional.
--
--   clientes.*                  modelos de negocio y perfil transaccional
--                               DECLARADO (para compararlo con el real)
--   cmp_alertas                 alertas del monitoreo, persistidas y
--                               gestionables (una por empresa, regla y mes)
--   cmp_alerta_eventos          trazabilidad de cada decisión (solo inserción)
--   usuarios alcance 'empresas' se desactivan: los clientes de los clientes
--                               no tienen acceso a la plataforma (2026-11-23)
--
-- Las alertas, casos y la calificación de riesgo son de uso interno del
-- equipo de cumplimiento: ningún usuario externo las ve (lo impone la API).
--
-- Idempotente.
-- ============================================================

-- ── 1. Perfil del cliente ────────────────────────────────────
ALTER TABLE clientes
    ADD COLUMN IF NOT EXISTS tipo_persona            TEXT          NOT NULL DEFAULT 'juridica',
    ADD COLUMN IF NOT EXISTS modelos_negocio         TEXT[]        NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS perfil_volumen_mensual  NUMERIC(20,2),
    ADD COLUMN IF NOT EXISTS perfil_operaciones_mes  INTEGER,
    ADD COLUMN IF NOT EXISTS perfil_ticket_promedio  NUMERIC(20,2),
    ADD COLUMN IF NOT EXISTS perfil_paises           TEXT[]        NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS perfil_actualizado      DATE;

-- Un cliente creado desde el monitoreo aún no tiene NIT: se completa luego en su ficha
-- (el índice único por organización y NIT admite varios NULL).
ALTER TABLE clientes ALTER COLUMN nit DROP NOT NULL;

ALTER TABLE clientes DROP CONSTRAINT IF EXISTS clientes_tipo_persona_check;
ALTER TABLE clientes ADD CONSTRAINT clientes_tipo_persona_check CHECK (tipo_persona IN ('juridica', 'natural'));
ALTER TABLE clientes DROP CONSTRAINT IF EXISTS clientes_perfil_positivo_check;
ALTER TABLE clientes ADD CONSTRAINT clientes_perfil_positivo_check CHECK (
    COALESCE(perfil_volumen_mensual, 0) >= 0 AND COALESCE(perfil_operaciones_mes, 0) >= 0
    AND COALESCE(perfil_ticket_promedio, 0) >= 0);

-- ── 2. Alertas del monitoreo ─────────────────────────────────
-- (empresa, organización) como clave compuesta: si una empresa pasa a otra
-- organización, sus alertas la acompañan (ON UPDATE CASCADE).
CREATE UNIQUE INDEX IF NOT EXISTS uq_tx_empresas_id_organizacion ON tx_empresas (id, organizacion_id);

CREATE TABLE IF NOT EXISTS cmp_alertas (
    id                    BIGSERIAL    PRIMARY KEY,
    organizacion_id       INTEGER      NOT NULL,
    empresa_id            INTEGER      NOT NULL,
    regla                 TEXT         NOT NULL,      -- código de la regla (FRAG, VOL, PERF…)
    periodo               DATE         NOT NULL,      -- primer día del mes evaluado
    tipo                  TEXT,
    prioridad             TEXT         NOT NULL CHECK (prioridad IN ('Crítica', 'Alta', 'Media', 'Baja')),
    titulo                TEXT         NOT NULL,
    descripcion           TEXT,
    accion_requerida      TEXT,
    valor_detectado       NUMERIC(24,4),
    umbral                NUMERIC(24,4),
    requiere_reporte_uiaf BOOLEAN      NOT NULL DEFAULT FALSE,
    detectada_en          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizada_en        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_limite          DATE,
    estado                TEXT         NOT NULL DEFAULT 'nueva'
                              CHECK (estado IN ('nueva', 'en_analisis', 'descartada', 'escalada', 'posible_ros')),
    analista_id           INTEGER      REFERENCES usuarios(id) ON DELETE SET NULL,
    justificacion         TEXT,
    decidida_por          TEXT,
    decidida_en           TIMESTAMP,
    UNIQUE (empresa_id, regla, periodo),
    FOREIGN KEY (empresa_id, organizacion_id) REFERENCES tx_empresas (id, organizacion_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    -- Una decisión de cierre exige justificación y responsable
    CONSTRAINT cmp_alertas_decision_check CHECK (
        estado IN ('nueva', 'en_analisis')
        OR (COALESCE(length(trim(justificacion)), 0) >= 10 AND decidida_por IS NOT NULL AND decidida_en IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_cmp_alertas_org_estado ON cmp_alertas (organizacion_id, estado);
CREATE INDEX IF NOT EXISTS idx_cmp_alertas_empresa ON cmp_alertas (empresa_id, periodo DESC);

CREATE TABLE IF NOT EXISTS cmp_alerta_eventos (
    id               BIGSERIAL   PRIMARY KEY,
    alerta_id        BIGINT      NOT NULL REFERENCES cmp_alertas(id) ON DELETE RESTRICT,
    usuario          TEXT        NOT NULL,
    accion           TEXT        NOT NULL,     -- detectada, actualizada, estado, asignacion, nota
    estado_anterior  TEXT,
    estado_nuevo     TEXT,
    nota             TEXT,
    creado_en        TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cmp_alerta_eventos_alerta ON cmp_alerta_eventos (alerta_id, creado_en);

-- Bitácora inmutable: ni UPDATE ni DELETE
CREATE OR REPLACE FUNCTION fn_cmp_eventos_inmutables()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'cmp_alerta_eventos es de solo inserción';
END;
$$;
DROP TRIGGER IF EXISTS trg_cmp_eventos_inmutables ON cmp_alerta_eventos;
CREATE TRIGGER trg_cmp_eventos_inmutables
    BEFORE UPDATE OR DELETE ON cmp_alerta_eventos
    FOR EACH ROW EXECUTE FUNCTION fn_cmp_eventos_inmutables();

-- ── 3. Los clientes de los clientes no tienen acceso ─────────
UPDATE usuarios SET activo = 0, updated_at = CURRENT_TIMESTAMP
 WHERE rol = 'cliente' AND alcance = 'empresas' AND activo = 1;
