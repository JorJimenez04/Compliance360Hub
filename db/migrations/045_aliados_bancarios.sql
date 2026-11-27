-- ============================================================
-- Compliance360 Hub -- Migración 045
-- Aliados bancarios (fase 2 de la migración, decisión 2026-11-27).
--
-- Dos niveles, para no repetir información:
--   aliados_bancarios       la ENTIDAD (banco, PSP, VASP…): se registra una sola vez
--   org_aliados             la RELACIÓN de una organización con esa entidad: estado,
--                           servicios, riesgo, debida diligencia, exigencias, contactos.
--                           Cobre puede ser aliado de Adamo y de Holdings BPO con
--                           relaciones independientes.
--   org_aliados_historial   bitácora de cada cambio de estado, riesgo y diligencia
--
-- La tabla vieja `aliados` (app Streamlit) NO se toca. Solo se copian, una vez y
-- limpios, los aliados que ya eran de Adamo (decisión de Jorge: el resto empieza vacío).
-- Idempotente.
-- ============================================================

CREATE TABLE IF NOT EXISTS aliados_bancarios (
    id              SERIAL       PRIMARY KEY,
    nombre          TEXT         NOT NULL,                 -- nombre comercial: Cobre, Davivienda…
    razon_social    TEXT,
    identificacion  TEXT,                                  -- NIT o identificación tributaria del país
    pais            TEXT,
    tipo_entidad    TEXT
        CHECK (tipo_entidad IN ('banco', 'psp', 'entidad_pagos', 'corresponsal', 'vasp', 'otro')),
    regulado        BOOLEAN      NOT NULL DEFAULT FALSE,
    regulador       TEXT,                                  -- SFC, FinCEN, CMF…
    licencia        TEXT,
    sitio_web       TEXT,
    notas           TEXT,
    creado_por      TEXT,
    creado_en       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_aliados_bancarios_nombre ON aliados_bancarios (lower(nombre));

CREATE TABLE IF NOT EXISTS org_aliados (
    id                     SERIAL     PRIMARY KEY,
    organizacion_id        INTEGER    NOT NULL REFERENCES organizaciones(id),
    aliado_id              INTEGER    NOT NULL REFERENCES aliados_bancarios(id),
    estado                 TEXT       NOT NULL DEFAULT 'prospecto'
        CHECK (estado IN ('prospecto', 'onboarding', 'activo', 'suspendido', 'terminado')),
    fecha_estado           DATE       NOT NULL DEFAULT CURRENT_DATE,
    fecha_inicio           DATE,
    servicios              TEXT[]     NOT NULL DEFAULT '{}',   -- pay_in, pay_out, dispersion…
    monedas                TEXT[]     NOT NULL DEFAULT '{}',
    nivel_riesgo           TEXT       CHECK (nivel_riesgo IN ('Alto', 'Medio', 'Bajo')),
    proxima_revision       DATE,
    dd_estado              TEXT       NOT NULL DEFAULT 'no_iniciada'
        CHECK (dd_estado IN ('no_iniciada', 'en_proceso', 'completa', 'rechazada')),
    dd_fecha               DATE,
    dd_nivel               TEXT       CHECK (dd_nivel IN ('simplificada', 'estandar', 'intensificada')),
    exigencias             TEXT[]     NOT NULL DEFAULT '{}',   -- lo que el aliado le exige a la organización
    contacto_cumplimiento  TEXT,
    correo_cumplimiento    TEXT,
    telefono_cumplimiento  TEXT,
    contacto_comercial     TEXT,
    correo_comercial       TEXT,
    notas                  TEXT,
    origen_aliado_id       INTEGER,                            -- id en la tabla vieja `aliados`, si vino de allá
    creado_por             TEXT,
    creado_en              TIMESTAMP  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en         TIMESTAMP  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_org_aliado UNIQUE (organizacion_id, aliado_id)
);
CREATE INDEX IF NOT EXISTS idx_org_aliados_organizacion ON org_aliados (organizacion_id);

CREATE TABLE IF NOT EXISTS org_aliados_historial (
    id              SERIAL     PRIMARY KEY,
    relacion_id     INTEGER    NOT NULL REFERENCES org_aliados(id) ON DELETE CASCADE,
    campo           TEXT       NOT NULL,                       -- estado | riesgo | diligencia | alta
    valor_anterior  TEXT,
    valor_nuevo     TEXT,
    motivo          TEXT,
    usuario         TEXT       NOT NULL,
    fecha           TIMESTAMP  NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_org_aliados_historial ON org_aliados_historial (relacion_id, fecha DESC);

-- ── Copia única y limpia de los aliados de Adamo desde la app anterior ──────
DO $$
DECLARE
    a        RECORD;
    nuevo    INTEGER;
    rel      INTEGER;
    riesgo   TEXT;
BEGIN
    IF to_regclass('aliados') IS NULL OR NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'aliados' AND column_name IN ('tipo_riel', 'organizacion_id', 'estado_hbpocorp')
        HAVING count(*) = 3) THEN
        RETURN;
    END IF;

    FOR a IN EXECUTE $q$
        SELECT al.* FROM aliados al JOIN organizaciones o ON o.id = al.organizacion_id
         WHERE o.nombre = 'Adamo'
           AND NOT EXISTS (SELECT 1 FROM org_aliados r WHERE r.origen_aliado_id = al.id)
         ORDER BY al.id $q$
    LOOP
        INSERT INTO aliados_bancarios (nombre, razon_social, identificacion, pais, regulado, licencia, notas, creado_por)
        VALUES (a.nombre_razon_social, a.nombre_razon_social, NULLIF(trim(a.nit), ''),
                NULLIF(a.jurisdicciones[1], ''), COALESCE(a.es_entidad_regulada, FALSE), a.numero_licencia,
                CASE WHEN cardinality(a.certificaciones) > 0
                     THEN 'Certificaciones (app anterior): ' || array_to_string(a.certificaciones, ', ') END,
                'migracion_045')
        ON CONFLICT (lower(nombre)) DO NOTHING
        RETURNING id INTO nuevo;
        IF nuevo IS NULL THEN
            SELECT id INTO nuevo FROM aliados_bancarios WHERE lower(nombre) = lower(a.nombre_razon_social);
        END IF;

        riesgo := CASE WHEN a.nivel_riesgo = 'Muy Alto' THEN 'Alto' ELSE a.nivel_riesgo END;

        INSERT INTO org_aliados (organizacion_id, aliado_id, estado, fecha_inicio, servicios, nivel_riesgo,
                                 proxima_revision, dd_estado, dd_fecha, contacto_cumplimiento,
                                 correo_cumplimiento, telefono_cumplimiento, notas, origen_aliado_id, creado_por)
        VALUES (a.organizacion_id, nuevo,
                CASE a.estado_pipeline WHEN 'Activo' THEN 'activo' WHEN 'Suspendido' THEN 'suspendido'
                     WHEN 'Terminado' THEN 'terminado' WHEN 'Prospecto' THEN 'prospecto' ELSE 'onboarding' END,
                a.fecha_vinculacion,
                CASE a.tipo_riel WHEN 'Dispersión' THEN ARRAY['dispersion'] WHEN 'Recaudo' THEN ARRAY['recaudo']
                     WHEN 'Crypto' THEN ARRAY['cripto'] ELSE '{}'::text[] END,
                riesgo, a.fecha_proxima_revision,
                CASE a.estado_due_diligence WHEN 'En Proceso' THEN 'en_proceso' WHEN 'Completado' THEN 'completa'
                     WHEN 'Rechazado' THEN 'rechazada' ELSE 'no_iniciada' END,
                a.fecha_due_diligence, a.representante_legal, a.email_contacto, a.telefono_contacto,
                concat_ws(E'\n',
                    NULLIF(a.observaciones_compliance, ''),
                    format('App anterior — relación con Holdings BPO: %s; Adamo Services: %s; Paycop: %s; SARLAFT: %s.',
                           a.estado_hbpocorp, a.estado_adamo, a.estado_paycop, a.estado_sarlaft)),
                a.id, 'migracion_045')
        ON CONFLICT (organizacion_id, aliado_id) DO NOTHING
        RETURNING id INTO rel;

        IF rel IS NOT NULL THEN
            INSERT INTO org_aliados_historial (relacion_id, campo, valor_nuevo, motivo, usuario)
            VALUES (rel, 'alta', 'Cargado desde la app anterior',
                    CASE WHEN a.nivel_riesgo = 'Muy Alto'
                         THEN 'Riesgo «Muy Alto» unificado en «Alto» (escala de 3 niveles).' END,
                    'migracion_045');
        END IF;
    END LOOP;
END $$;
