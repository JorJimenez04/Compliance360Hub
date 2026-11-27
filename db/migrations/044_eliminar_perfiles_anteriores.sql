-- ============================================================
-- Compliance360 Hub -- Migración 044
-- Eliminar las cuentas con perfiles de la app anterior (Streamlit)
-- y dejar en la base solo los perfiles de la plataforma actual
-- (decisión 2026-11-27).
--
-- Trazabilidad: log_auditoria guarda el username como texto, así
-- que sus registros se conservan íntegros; solo se suelta el enlace
-- (usuario_id = NULL) a la cuenta eliminada. La eliminación misma
-- queda registrada en log_auditoria con usuario, correo y perfil.
--
-- Protección: si una cuenta firmó revisiones SARLAFT o cambios de
-- estado (evidencia que no se puede desvincular), la migración se
-- detiene sin tocar nada. Cualquier otra referencia desconocida
-- también la detiene (la base rechaza el DELETE y todo se revierte).
-- Idempotente: si ya no hay perfiles anteriores, solo fija la regla.
-- ============================================================

DO $$
DECLARE
    actuales  CONSTANT TEXT[] := ARRAY['super_admin', 'admin', 'compliance', 'director_cumplimiento', 'cliente', 'junta'];
    viejos    INTEGER[];
    detalle   TEXT;
    nombres   TEXT;
    bloqueo   INTEGER := 0;
    n         INTEGER;
BEGIN
    SELECT array_agg(id ORDER BY id),
           string_agg(username, ', ' ORDER BY username),
           json_agg(json_build_object('username', username, 'email', email, 'rol', rol) ORDER BY username)::text
      INTO viejos, nombres, detalle
      FROM usuarios WHERE NOT (rol = ANY(actuales));

    IF viejos IS NULL THEN
        RAISE NOTICE 'Migración 044: no hay cuentas con perfiles anteriores.';
        RETURN;
    END IF;

    -- Evidencia SARLAFT firmada por estas cuentas: no se desvincula
    IF to_regclass('revisiones_sarlaft') IS NOT NULL THEN
        EXECUTE 'SELECT count(*) FROM revisiones_sarlaft WHERE oficial_id = ANY($1) OR aprobado_por = ANY($1)'
           INTO n USING viejos;
        bloqueo := bloqueo + n;
    END IF;
    IF to_regclass('historial_estados') IS NOT NULL THEN
        EXECUTE 'SELECT count(*) FROM historial_estados WHERE cambiado_por = ANY($1)' INTO n USING viejos;
        bloqueo := bloqueo + n;
    END IF;
    IF bloqueo > 0 THEN
        RAISE EXCEPTION 'Migración 044 detenida: % registro(s) SARLAFT o de historial firmados por cuentas anteriores. Revíselos antes de eliminar.', bloqueo;
    END IF;

    -- Soltar enlaces (los registros se conservan)
    IF to_regclass('log_auditoria') IS NOT NULL THEN
        UPDATE log_auditoria SET usuario_id = NULL WHERE usuario_id = ANY(viejos);
    END IF;
    IF to_regclass('aliados') IS NOT NULL THEN
        UPDATE aliados SET ejecutivo_cuenta_id   = NULL WHERE ejecutivo_cuenta_id   = ANY(viejos);
        UPDATE aliados SET oficial_compliance_id = NULL WHERE oficial_compliance_id = ANY(viejos);
        UPDATE aliados SET creado_por            = NULL WHERE creado_por            = ANY(viejos);
        UPDATE aliados SET actualizado_por       = NULL WHERE actualizado_por       = ANY(viejos);
    END IF;

    DELETE FROM usuarios WHERE id = ANY(viejos);
    GET DIAGNOSTICS n = ROW_COUNT;

    IF to_regclass('log_auditoria') IS NOT NULL THEN
        INSERT INTO log_auditoria (usuario_id, username, accion, entidad, descripcion, valores_anteriores, resultado)
        VALUES (NULL, 'migracion_044', 'DELETE', 'usuarios',
                format('Eliminadas %s cuentas con perfiles de la app anterior: %s', n, nombres),
                detalle, 'exitoso');
    END IF;
    RAISE NOTICE 'Migración 044: % cuentas eliminadas (%).', n, nombres;
END $$;

-- Solo los perfiles de la plataforma actual
ALTER TABLE usuarios DROP CONSTRAINT IF EXISTS usuarios_rol_check;
ALTER TABLE usuarios ADD CONSTRAINT usuarios_rol_check
  CHECK (rol IN (
    'super_admin',
    'admin',
    'compliance',
    'director_cumplimiento',
    'cliente',
    'junta'
  ));
