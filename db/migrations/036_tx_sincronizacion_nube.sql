-- ============================================================
-- Compliance360 Hub -- Migración 036
-- Monitoreo Transaccional: carga automática desde OneDrive
-- Idempotente : CREATE TABLE / INDEX IF NOT EXISTS
--
-- tx_revisiones_nube : cada revisión de la carpeta (programada o manual),
--                      aunque no encuentre archivos nuevos.
-- tx_archivos_nube   : cada versión de archivo procesada. Un archivo ya
--                      procesado en esa misma versión no se vuelve a descargar.
-- ============================================================

CREATE TABLE IF NOT EXISTS tx_revisiones_nube (
    id               SERIAL      PRIMARY KEY,
    origen           TEXT        NOT NULL,             -- 'onedrive' | 'carpeta'
    iniciado_en      TIMESTAMP   NOT NULL,
    finalizado_en    TIMESTAMP,
    resultado        VARCHAR(12) NOT NULL CHECK (resultado IN ('OK','CON_ERRORES','ERROR','EN_CURSO')),
    usuario          TEXT,                             -- 'programada' o quien pulsó «Sincronizar ahora»
    archivos_vistos  INTEGER     NOT NULL DEFAULT 0,
    archivos_nuevos  INTEGER     NOT NULL DEFAULT 0,
    cargados         INTEGER     NOT NULL DEFAULT 0,
    errores          INTEGER     NOT NULL DEFAULT 0,
    mensaje          TEXT
);

CREATE INDEX IF NOT EXISTS idx_tx_revisiones_nube_id
    ON tx_revisiones_nube (id DESC);

CREATE TABLE IF NOT EXISTS tx_archivos_nube (
    id                 SERIAL      PRIMARY KEY,
    origen             TEXT        NOT NULL,
    item_id            TEXT        NOT NULL,           -- identificador del archivo en OneDrive
    version            TEXT        NOT NULL,           -- cTag de OneDrive: cambia si cambia el contenido
    empresa            TEXT        NOT NULL,           -- nombre de la subcarpeta
    nombre             TEXT        NOT NULL,
    tamano             BIGINT,
    modificado_en      TIMESTAMP,
    procesado_en       TIMESTAMP   NOT NULL,
    resultado          VARCHAR(10) NOT NULL CHECK (resultado IN ('OK','OMITIDA','ERROR')),
    revision_id        INTEGER     REFERENCES tx_revisiones_nube(id) ON DELETE SET NULL,
    mensaje            TEXT,
    CONSTRAINT uq_tx_archivo_version UNIQUE (origen, item_id, version)
);

CREATE INDEX IF NOT EXISTS idx_tx_archivos_nube_empresa
    ON tx_archivos_nube (empresa, procesado_en DESC);

-- Conexión delegada con OneDrive (inicio de sesión con código, sin administrador).
-- Una sola fila: el refresh token del usuario conectado, CIFRADO con la clave del
-- servidor (SECRET_KEY). Sin la clave no sirve; al cambiarla hay que reconectar.
CREATE TABLE IF NOT EXISTS tx_credenciales_nube (
    origen          TEXT        PRIMARY KEY,           -- 'onedrive'
    cuenta          TEXT,                              -- correo de quien se conectó
    token_cifrado   TEXT        NOT NULL,
    conectado_por   TEXT        NOT NULL,              -- usuario de Compliance360 Hub
    conectado_en    TIMESTAMP   NOT NULL,
    renovado_en     TIMESTAMP   NOT NULL
);
