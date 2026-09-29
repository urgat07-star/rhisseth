-- Economy v0.4.0: editable catalogue classification and annual resource income.
ALTER TABLE extractable_resources ADD COLUMN is_food boolean NOT NULL DEFAULT false;
ALTER TABLE produced_resources ADD COLUMN is_food boolean NOT NULL DEFAULT false;
ALTER TABLE game_resources ADD COLUMN is_food boolean NOT NULL DEFAULT false;

UPDATE extractable_resources SET is_food=(purpose ILIKE '%еда%');
UPDATE produced_resources SET is_food=(purpose ILIKE '%еда%');
UPDATE game_resources SET is_food=true WHERE name IN
 ('Еда','Пшеница','Рожь','Ячмень','Рис','Дичь','Рыба','Моллюски','Морской зверь',
  'Водоросли','Мёд','Пряности','Ягоды','Скот','Овцы');

INSERT INTO game_resources(code,name,starting_quantity,is_food)
SELECT CASE WHEN code='horses' THEN 'horse' ELSE code END,name,0,is_food
FROM extractable_resources
ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name,is_food=EXCLUDED.is_food;

INSERT INTO game_resources(code,name,starting_quantity,is_food)
SELECT code,name,0,is_food FROM produced_resources
ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name,is_food=EXCLUDED.is_food;

INSERT INTO game_inventory(user_id,resource_code,quantity)
SELECT w.user_id,r.code,0 FROM game_wallets w CROSS JOIN game_resources r
ON CONFLICT(user_id,resource_code) DO NOTHING;

ALTER TABLE game_resource_ledger DROP CONSTRAINT game_resource_ledger_reason_check;
ALTER TABLE game_resource_ledger ADD CONSTRAINT game_resource_ledger_reason_check
 CHECK (reason IN ('starting_grant','hire_unit','raid','test_reset','encounter','annual_economy'));

CREATE TABLE game_economy_years (
    year integer PRIMARY KEY CHECK (year >= 0),
    processed_at timestamptz NOT NULL DEFAULT now()
);
