-- Economy v0.4.0: remove legacy resource names and do not persist "Нет".
UPDATE hexes
SET data = jsonb_set(data, '{Основной ресурс}', '"Дерево"'::jsonb, true)
WHERE data->>'Основной ресурс' = 'Древесина';

UPDATE hexes
SET data = jsonb_set(data, '{Основной ресурс}', '"Дерево"'::jsonb, true)
WHERE data->>'Основной ресурс' = 'Дичь'
  AND lower(COALESCE(data->>'Тип местности', '')) ~ 'лес|тайга';

UPDATE hexes
SET data = data - 'Основной ресурс' - 'Богатство ресурса'
WHERE data->>'Основной ресурс' IN ('Нет', 'Нет ресурса', 'Отсутствует', '-', '- нет -', 'Дичь');

DELETE FROM extractable_resources
WHERE name IN ('Дичь', 'Древесина') OR code = 'game';

-- Remove an unused legacy warehouse entry, but preserve it if historical
-- transactions or a non-zero balance make deletion unsafe.
DELETE FROM game_inventory
WHERE resource_code = 'game' AND quantity = 0
  AND NOT EXISTS (SELECT 1 FROM game_resource_ledger WHERE resource_code = 'game');

DELETE FROM game_resources
WHERE code = 'game' AND name = 'Дичь'
  AND NOT EXISTS (SELECT 1 FROM game_inventory WHERE resource_code = 'game')
  AND NOT EXISTS (SELECT 1 FROM game_resource_ledger WHERE resource_code = 'game');

