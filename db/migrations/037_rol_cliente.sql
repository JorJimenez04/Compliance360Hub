-- ============================================================
-- Compliance360 Hub -- Migración 037
-- Rol externo «cliente»: ve solo Monitoreo Transaccional de SUS empresas.
-- Idempotente: DROP CONSTRAINT IF EXISTS / CREATE TABLE IF NOT EXISTS
--
-- usuario_empresas: qué filas de tx_empresas puede consultar cada usuario con
-- rol «cliente». Una persona puede tener varias empresas y una empresa varias personas.
-- Los roles internos no usan esta tabla: ven todas las empresas.
-- ============================================================

ALTER TABLE usuarios
  DROP CONSTRAINT IF EXISTS usuarios_rol_check;

ALTER TABLE usuarios
  ADD CONSTRAINT usuarios_rol_check
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
    'cliente'
  ));

CREATE TABLE IF NOT EXISTS usuario_empresas (
    usuario_id  INTEGER   NOT NULL REFERENCES usuarios(id)    ON DELETE CASCADE,
    empresa_id  INTEGER   NOT NULL REFERENCES tx_empresas(id) ON DELETE CASCADE,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (usuario_id, empresa_id)
);

CREATE INDEX IF NOT EXISTS idx_usuario_empresas_empresa
    ON usuario_empresas (empresa_id);
