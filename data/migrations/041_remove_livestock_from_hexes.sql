-- Economy v0.4.0: livestock is produced by a building and must never be a
-- natural hex resource. Preserve field-resource variety with horses/sheep.
UPDATE hexes
SET data=data || jsonb_build_object(
    'Основной ресурс',
    CASE WHEN lower(COALESCE(data->>'Тип местности','')) LIKE '%луг%'
              OR lower(COALESCE(data->>'Тип местности','')) LIKE '%холм%'
         THEN 'Овцы' ELSE 'Лошади' END)
WHERE data->>'Основной ресурс'='Скот';

DELETE FROM extractable_resources WHERE code='livestock' OR name='Скот';

INSERT INTO extractable_resources(code,name,typical_locations,purpose)
VALUES ('sheep','Овцы','Равнина, луг, степь, холмы','Еда, шерсть')
ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name,
    typical_locations=EXCLUDED.typical_locations,purpose=EXCLUDED.purpose;

INSERT INTO produced_resources(code,name,ingredients,required_building,purpose)
VALUES ('livestock','Скот','','Пастбище или Ферма','Еда, кожа, шерсть')
ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name,ingredients=EXCLUDED.ingredients,
    required_building=EXCLUDED.required_building,purpose=EXCLUDED.purpose;

INSERT INTO game_resources(code,name,starting_quantity)
VALUES ('sheep','Овцы',0)
ON CONFLICT DO NOTHING;

INSERT INTO game_inventory(user_id,resource_code,quantity)
SELECT user_id,'sheep',0 FROM game_wallets
ON CONFLICT(user_id,resource_code) DO NOTHING;
