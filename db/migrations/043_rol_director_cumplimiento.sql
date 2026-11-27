-- ============================================================
-- Compliance360 Hub -- Migración 043
-- Perfil «director_cumplimiento»: responsable de la operación de
-- compliance de todo el grupo empresarial. Equipo interno (sin
-- organización), ve todas las organizaciones en SOLO LECTURA
-- (decisión 2026-11-24; las aprobaciones llegarán después).
-- La lectura/escritura la impone la API (ROLES_MONITOREO vs ROLES_CARGA).
-- Idempotente.
-- ============================================================

ALTER TABLE usuarios DROP CONSTRAINT IF EXISTS usuarios_rol_check;
ALTER TABLE usuarios ADD CONSTRAINT usuarios_rol_check
  CHECK (rol IN (
    'super_admin',
    'compliance',
    'director_cumplimiento',
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
