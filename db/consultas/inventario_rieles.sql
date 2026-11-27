-- Inventario de SOLO LECTURA para planear la fase 2 (Banking Partners / Rieles). No modifica nada.
\echo '== Aliados / rieles registrados en la app anterior'
SELECT a.id, a.nombre_razon_social AS nombre, a.tipo_aliado, a.tipo_riel, a.estado_pipeline AS estado,
       a.nivel_riesgo, a.estado_sarlaft, a.estado_due_diligence AS dd,
       a.estado_hbpocorp AS hbpo, a.estado_adamo AS adamo, a.estado_paycop AS paycop,
       o.nombre AS organizacion
FROM aliados a LEFT JOIN organizaciones o ON o.id = a.organizacion_id
ORDER BY a.estado_pipeline, a.nombre_razon_social;

\echo '== Bancos que aparecen en las transacciones (top 20 por número de movimientos)'
SELECT COALESCE(NULLIF(trim(banco), ''), '(vacío)') AS banco, count(*) AS movimientos
FROM tx_transacciones GROUP BY 1 ORDER BY 2 DESC LIMIT 20;
