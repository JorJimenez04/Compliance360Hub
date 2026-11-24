-- ============================================================
-- Compliance360 Hub -- Migración 042
-- Documentación del cliente y de sus beneficiarios, leída de la
-- carpeta del cliente en OneDrive (solo lectura).
--
--   clientes.carpeta_onedrive*    enlace a la carpeta del cliente y su
--                                 identificación resuelta en Microsoft Graph
--   cmp_beneficiarios_expediente  beneficiarios con expediente documental
--                                 (top 10 por monto, agregados a mano o con
--                                 carpeta propia); una vez abierto se conserva
--   cmp_documentos                archivos encontrados y el documento que son
--                                 (reconocido por el nombre o asignado a mano)
--
-- Uso interno del equipo de cumplimiento (lo impone la API).
-- Idempotente.
-- ============================================================

ALTER TABLE clientes
    ADD COLUMN IF NOT EXISTS carpeta_onedrive     TEXT,
    ADD COLUMN IF NOT EXISTS carpeta_drive_id     TEXT,
    ADD COLUMN IF NOT EXISTS carpeta_item_id      TEXT,
    ADD COLUMN IF NOT EXISTS carpeta_nombre       TEXT,
    ADD COLUMN IF NOT EXISTS carpeta_revisada_en  TIMESTAMP,
    ADD COLUMN IF NOT EXISTS carpeta_error        TEXT;

CREATE TABLE IF NOT EXISTS cmp_beneficiarios_expediente (
    id               SERIAL      PRIMARY KEY,
    cliente_id       INTEGER     NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    id_beneficiario  TEXT        NOT NULL,
    nombre           TEXT,
    tipo_persona     TEXT        NOT NULL DEFAULT 'natural' CHECK (tipo_persona IN ('juridica', 'natural')),
    origen           TEXT        NOT NULL CHECK (origen IN ('top10', 'manual', 'carpeta')),
    activo           BOOLEAN     NOT NULL DEFAULT TRUE,
    abierto_por      TEXT        NOT NULL DEFAULT 'sistema',
    abierto_en       TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    carpeta_item_id  TEXT,
    carpeta_nombre   TEXT,
    UNIQUE (cliente_id, id_beneficiario)
);

CREATE TABLE IF NOT EXISTS cmp_documentos (
    id               BIGSERIAL   PRIMARY KEY,
    cliente_id       INTEGER     NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    id_beneficiario  TEXT,                       -- NULL: documento propio del cliente
    codigo           TEXT,                       -- NULL: archivo no reconocido
    item_id          TEXT        NOT NULL,       -- identificador del archivo en OneDrive
    nombre_archivo   TEXT        NOT NULL,
    ruta             TEXT,
    web_url          TEXT,
    tamano           BIGINT,
    modificado_en    TIMESTAMP,
    detectado_en     TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    asignacion       TEXT        NOT NULL DEFAULT 'auto' CHECK (asignacion IN ('auto', 'manual')),
    asignado_por     TEXT,
    UNIQUE (cliente_id, item_id)
);
CREATE INDEX IF NOT EXISTS idx_cmp_documentos_cliente ON cmp_documentos (cliente_id, id_beneficiario);
