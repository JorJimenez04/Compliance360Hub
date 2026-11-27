-- Inventario de SOLO LECTURA: cuentas con perfiles de la app anterior (Streamlit)
-- y cuánta historia dejaron en la base. No modifica nada.
-- Las que tienen 0 en todas las columnas de historia se pueden eliminar sin perder trazabilidad.
WITH viejos AS (
    SELECT id, username, email, rol, activo, ultimo_acceso
    FROM usuarios
    WHERE rol NOT IN ('super_admin', 'admin', 'compliance', 'director_cumplimiento', 'cliente', 'junta')
)
SELECT v.username,
       v.email,
       v.rol,
       CASE WHEN v.activo = 1 THEN 'activa' ELSE 'inactiva' END                       AS estado,
       COALESCE(to_char(v.ultimo_acceso, 'YYYY-MM-DD'), 'nunca')                       AS ultimo_ingreso,
       (SELECT count(*) FROM log_auditoria a WHERE a.usuario_id = v.id)                 AS auditoria,
       (SELECT count(*) FROM revisiones_sarlaft r WHERE v.id IN (r.oficial_id, r.aprobado_por)) AS revisiones_sarlaft,
       (SELECT count(*) FROM historial_estados h WHERE h.cambiado_por = v.id)           AS historial_estados,
       (SELECT count(*) FROM aliados x
         WHERE v.id IN (x.ejecutivo_cuenta_id, x.oficial_compliance_id, x.creado_por, x.actualizado_por)) AS aliados
FROM viejos v
ORDER BY v.rol, v.username;
