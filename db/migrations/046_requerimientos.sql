-- ============================================================
-- Compliance360 Hub -- Migración 046
-- Requerimientos de compliance (fase 2, parte B; decisión 2026-11-27).
--
-- Lo que se le pide a una organización (Adamo) o a uno de sus clientes
-- (Paxum, CM Grupo Tecno…), venga de un aliado bancario, un regulador,
-- una auditoría o del propio oficial de cumplimiento.
--
--   requerimientos         el requerimiento, con su consecutivo REQ-AAAA-NNN por organización
--   requerimiento_eventos  bitácora: alta, cambios de estado, notas y ediciones
--
-- Uso interno (Jorge y el director); los clientes no responden desde la app.
-- Idempotente.
-- ============================================================

CREATE TABLE IF NOT EXISTS requerimientos (
    id                  SERIAL     PRIMARY KEY,
    organizacion_id     INTEGER    NOT NULL REFERENCES organizaciones(id),
    consecutivo         TEXT       NOT NULL,                         -- REQ-2026-001
    dirigido_a          TEXT       NOT NULL CHECK (dirigido_a IN ('organizacion', 'cliente')),
    cliente_id          INTEGER    REFERENCES clientes(id),
    origen              TEXT       NOT NULL
        CHECK (origen IN ('aliado', 'regulador', 'auditoria', 'oficial', 'otro')),
    relacion_aliado_id  INTEGER    REFERENCES org_aliados(id),       -- si lo pidió un aliado bancario
    origen_detalle      TEXT,                                        -- UIAF, Supersociedades, firma auditora…
    solicitante         TEXT,                                        -- quién lo pidió (persona)
    canal               TEXT       CHECK (canal IN ('correo', 'portal', 'reunion', 'oficio', 'otro')),
    tipo                TEXT       NOT NULL
        CHECK (tipo IN ('kyc_kyb', 'rfi_transacciones', 'recertificacion_aml', 'reporte_periodico',
                        'actualizacion_documental', 'otro')),
    asunto              TEXT       NOT NULL,
    descripcion         TEXT,
    referencias_tx      TEXT[]     NOT NULL DEFAULT '{}',            -- ids o referencias de transacciones
    fecha_recibido      DATE       NOT NULL,
    fecha_limite        DATE,
    prioridad           TEXT       NOT NULL DEFAULT 'media' CHECK (prioridad IN ('alta', 'media', 'baja')),
    responsable         TEXT,
    estado              TEXT       NOT NULL DEFAULT 'recibido'
        CHECK (estado IN ('recibido', 'en_preparacion', 'en_revision', 'enviado', 'cerrado', 'seguimiento')),
    fecha_envio         DATE,
    resumen_respuesta   TEXT,
    carpeta_evidencias  TEXT,                                        -- enlace a la carpeta en OneDrive
    creado_por          TEXT       NOT NULL,
    creado_en           TIMESTAMP  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en      TIMESTAMP  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_requerimiento_consecutivo UNIQUE (organizacion_id, consecutivo),
    CONSTRAINT ck_requerimiento_cliente CHECK ((dirigido_a = 'cliente') = (cliente_id IS NOT NULL)),
    CONSTRAINT ck_requerimiento_aliado CHECK (origen = 'aliado' OR relacion_aliado_id IS NULL)
);
CREATE INDEX IF NOT EXISTS idx_requerimientos_org_estado ON requerimientos (organizacion_id, estado);
CREATE INDEX IF NOT EXISTS idx_requerimientos_cliente ON requerimientos (cliente_id) WHERE cliente_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_requerimientos_aliado ON requerimientos (relacion_aliado_id) WHERE relacion_aliado_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS requerimiento_eventos (
    id               SERIAL     PRIMARY KEY,
    requerimiento_id INTEGER    NOT NULL REFERENCES requerimientos(id) ON DELETE CASCADE,
    tipo             TEXT       NOT NULL CHECK (tipo IN ('alta', 'estado', 'nota', 'edicion')),
    valor_anterior   TEXT,
    valor_nuevo      TEXT,
    comentario       TEXT,
    usuario          TEXT       NOT NULL,
    fecha            TIMESTAMP  NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_requerimiento_eventos ON requerimiento_eventos (requerimiento_id, fecha DESC);
