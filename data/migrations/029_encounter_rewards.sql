INSERT INTO game_resources(code,name,starting_quantity) VALUES
    ('hide','Шкуры',0),('food','Еда',0);
INSERT INTO game_inventory(user_id,resource_code,quantity)
SELECT w.user_id,r.code,0 FROM game_wallets w JOIN game_resources r ON r.code IN ('hide','food')
ON CONFLICT DO NOTHING;

ALTER TABLE game_gold_ledger DROP CONSTRAINT game_gold_ledger_reason_check;
ALTER TABLE game_gold_ledger ADD CONSTRAINT game_gold_ledger_reason_check
    CHECK (reason IN ('starting_grant','hire_general','hire_unit','ransom_paid','ransom_received','raid','test_reset','encounter'));
ALTER TABLE game_resource_ledger DROP CONSTRAINT game_resource_ledger_reason_check;
ALTER TABLE game_resource_ledger ADD CONSTRAINT game_resource_ledger_reason_check
    CHECK (reason IN ('starting_grant','hire_unit','raid','test_reset','encounter'));
