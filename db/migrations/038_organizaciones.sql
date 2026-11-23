-- ============================================================
-- Compliance360 Hub -- Migración 038
-- Plataforma multi-organización (compliance como servicio).
--
-- Cada cliente de la plataforma es una ORGANIZACIÓN (Adamo, CM Grupo Tecno…),
-- sujeto obligado por sí misma. Sus clientes (contrapartes), sus rieles y sus
-- empresas de monitoreo le pertenecen, y ningún usuario de una organización
-- puede ver datos de otra.
--
--   organizaciones                 tabla nueva
--   clientes.organizacion_id       a quién pertenece la contraparte
--   aliados.organizacion_id        a quién pertenece el riel / aliado
--   tx_empresas.organizacion_id    a quién pertenece la empresa monitoreada
--   usuarios.organizacion_id       NULL = equipo de la plataforma (internos);
--                                  obligatorio para los roles externos
--   usuarios.alcance               solo rol «cliente»: 'organizacion' (ve toda su
--                                  organización) o 'empresas' (solo las de
--                                  usuario_empresas, comportamiento de la 037)
--   rol «junta»                    tablero ejecutivo de su organización
--
-- Datos existentes: todo queda en la organización «Adamo». Los clientes
-- externos creados con la 037 conservan exactamente lo que ya veían
-- (alcance 'empresas').
--
-- Transición: mientras la app Streamlit siga creando clientes, aliados y
-- empresas sin indicar organización, la columna toma por defecto la de Adamo.
--
-- Idempotente: se puede ejecutar varias veces. Todo corre en una transacción
-- (db/sync_db.py la envuelve): si algo falla, no queda nada a medias.
-- ============================================================

-- ── 1. Organizaciones ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS organizaciones (
    id          SERIAL      PRIMARY KEY,
    nombre      TEXT        NOT NULL,
    nit         TEXT,
    activa      BOOLEAN     NOT NULL DEFAULT TRUE,
    notas       TEXT,
    creado_por  TEXT        NOT NULL DEFAULT 'sistema',
    created_at  TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Nombre único sin distinguir mayúsculas; NIT único cuando se informa
CREATE UNIQUE INDEX IF NOT EXISTS uq_organizaciones_nombre ON organizaciones (lower(nombre));
CREATE UNIQUE INDEX IF NOT EXISTS uq_organizaciones_nit ON organizaciones (nit) WHERE nit IS NOT NULL;

CREATE OR REPLACE FUNCTION fn_organizaciones_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_organizaciones_updated_at ON organizaciones;
CREATE TRIGGER trg_organizaciones_updated_at
    BEFORE UPDATE ON organizaciones
    FOR EACH ROW EXECUTE FUNCTION fn_organizaciones_updated_at();

INSERT INTO organizaciones (nombre, notas, creado_por)
SELECT 'Adamo', 'Organización inicial: datos existentes antes de la migración 038', 'migracion_038'
WHERE NOT EXISTS (SELECT 1 FROM organizaciones WHERE lower(nombre) = 'adamo');

-- ── 2. organizacion_id en clientes, aliados y tx_empresas ────
DO $$
DECLARE
    adamo INTEGER;
    tabla TEXT;
BEGIN
    SELECT id INTO adamo FROM organizaciones WHERE lower(nombre) = 'adamo';

    FOREACH tabla IN ARRAY ARRAY['clientes', 'aliados', 'tx_empresas'] LOOP
        -- En producción existen las tres; la guarda permite aplicar la migración sobre
        -- esquemas parciales (pruebas automáticas que solo crean el módulo de monitoreo).
        CONTINUE WHEN to_regclass(tabla) IS NULL;
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS organizacion_id INTEGER '
                       'REFERENCES organizaciones(id) ON DELETE RESTRICT', tabla);
        EXECUTE format('UPDATE %I SET organizacion_id = %s WHERE organizacion_id IS NULL', tabla, adamo);
        EXECUTE format('ALTER TABLE %I ALTER COLUMN organizacion_id SET DEFAULT %s', tabla, adamo);
        EXECUTE format('ALTER TABLE %I ALTER COLUMN organizacion_id SET NOT NULL', tabla);
        EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I (organizacion_id)',
                       'idx_' || tabla || '_organizacion', tabla);
    END LOOP;
END;
$$;

-- El NIT pasa a ser único dentro de cada organización: una misma empresa puede
-- ser cliente (o riel) de dos organizaciones distintas.
ALTER TABLE clientes DROP CONSTRAINT IF EXISTS clientes_nit_key;
CREATE UNIQUE INDEX IF NOT EXISTS uq_clientes_organizacion_nit ON clientes (organizacion_id, nit);

DO $$
BEGIN
    IF to_regclass('aliados') IS NOT NULL THEN
        ALTER TABLE aliados DROP CONSTRAINT IF EXISTS aliados_nit_key;
        CREATE UNIQUE INDEX IF NOT EXISTS uq_aliados_organizacion_nit ON aliados (organizacion_id, nit);
    END IF;
END;
$$;

-- Una empresa de monitoreo solo puede enlazarse con un cliente de su misma
-- organización (garantizado por la base, no solo por la aplicación).
CREATE UNIQUE INDEX IF NOT EXISTS uq_clientes_id_organizacion ON clientes (id, organizacion_id);
ALTER TABLE tx_empresas DROP CONSTRAINT IF EXISTS tx_empresas_cliente_misma_org_fkey;
ALTER TABLE tx_empresas ADD CONSTRAINT tx_empresas_cliente_misma_org_fkey
    FOREIGN KEY (cliente_id, organizacion_id) REFERENCES clientes (id, organizacion_id);

-- ── 3. Usuarios: organización, alcance y rol «junta» ─────────
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS organizacion_id INTEGER
    REFERENCES organizaciones(id) ON DELETE RESTRICT;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS alcance TEXT;
CREATE INDEX IF NOT EXISTS idx_usuarios_organizacion ON usuarios (organizacion_id);

ALTER TABLE usuarios DROP CONSTRAINT IF EXISTS usuarios_rol_check;
ALTER TABLE usuarios ADD CONSTRAINT usuarios_rol_check
  CHECK (rol IN (
    'super_admin',
    'compliance',
    'manager_ops',
    'manager_comercial',
    'manager_legal',
    'agente',
    'cic',
    'admin',
    'comercial',
    'agente_kyc',
    'agente_operativo',
    'consulta',
    'cliente',
    'junta'
  ));

-- Los clientes externos de la 037 pasan a Adamo y conservan su alcance por empresa
UPDATE usuarios
   SET organizacion_id = (SELECT id FROM organizaciones WHERE lower(nombre) = 'adamo')
 WHERE rol = 'cliente' AND organizacion_id IS NULL;
UPDATE usuarios SET alcance = 'empresas' WHERE rol = 'cliente' AND alcance IS NULL;

-- Roles externos (cliente, junta) siempre con organización; internos nunca
ALTER TABLE usuarios DROP CONSTRAINT IF EXISTS usuarios_organizacion_check;
ALTER TABLE usuarios ADD CONSTRAINT usuarios_organizacion_check
  CHECK ((rol IN ('cliente', 'junta')) = (organizacion_id IS NOT NULL));

-- El alcance solo aplica (y es obligatorio) para el rol cliente.
-- COALESCE: un CHECK que evalúa a NULL se da por cumplido; así un cliente sin
-- alcance se rechaza en vez de colarse.
ALTER TABLE usuarios DROP CONSTRAINT IF EXISTS usuarios_alcance_check;
ALTER TABLE usuarios ADD CONSTRAINT usuarios_alcance_check
  CHECK (
    CASE WHEN rol = 'cliente'
         THEN COALESCE(alcance IN ('organizacion', 'empresas'), FALSE)
         ELSE alcance IS NULL
    END
  );
