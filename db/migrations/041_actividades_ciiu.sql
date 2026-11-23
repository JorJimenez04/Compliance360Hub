-- ============================================================
-- Compliance360 Hub -- Migración 041
-- Actividades económicas CIIU Rev. 4 A.C. (las cuatro del RUT) en la
-- ficha del cliente y en la de la organización.
--
--   actividades_ciiu[1]  actividad principal
--   actividades_ciiu[2]  actividad secundaria
--   actividades_ciiu[3]  otra actividad 1
--   actividades_ciiu[4]  otra actividad 2
--
-- La lista oficial vive en core/cumplimiento/datos (DANE 2022 + códigos DIAN);
-- la API valida que cada código exista y deduce de ellos los modelos de negocio.
-- clientes.sector_ciiu (texto libre de la 027) se conserva para la app anterior:
-- la API lo rellena con la actividad principal.
--
-- Idempotente.
-- ============================================================

ALTER TABLE clientes ADD COLUMN IF NOT EXISTS actividades_ciiu TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE clientes DROP CONSTRAINT IF EXISTS clientes_actividades_ciiu_check;
ALTER TABLE clientes ADD CONSTRAINT clientes_actividades_ciiu_check CHECK (
    cardinality(actividades_ciiu) <= 4
    AND array_to_string(actividades_ciiu, ',') ~ '^([0-9]{4}(,[0-9]{4})*)?$');

ALTER TABLE organizaciones ADD COLUMN IF NOT EXISTS actividades_ciiu TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE organizaciones DROP CONSTRAINT IF EXISTS organizaciones_actividades_ciiu_check;
ALTER TABLE organizaciones ADD CONSTRAINT organizaciones_actividades_ciiu_check CHECK (
    cardinality(actividades_ciiu) <= 4
    AND array_to_string(actividades_ciiu, ',') ~ '^([0-9]{4}(,[0-9]{4})*)?$');

-- Rescata el código de 4 dígitos que se hubiera escrito a mano en sector_ciiu
UPDATE clientes
   SET actividades_ciiu = ARRAY[substring(sector_ciiu FROM '^\s*([0-9]{4})')]
 WHERE cardinality(actividades_ciiu) = 0
   AND sector_ciiu ~ '^\s*[0-9]{4}';
