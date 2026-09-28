ALTER TABLE game_gold_ledger DROP CONSTRAINT game_gold_ledger_reason_check;
ALTER TABLE game_gold_ledger ADD CONSTRAINT game_gold_ledger_reason_check
    CHECK (reason IN ('starting_grant','hire_general','hire_unit','ransom_paid','ransom_received','raid','test_reset'));
ALTER TABLE game_resource_ledger DROP CONSTRAINT game_resource_ledger_reason_check;
ALTER TABLE game_resource_ledger ADD CONSTRAINT game_resource_ledger_reason_check
    CHECK (reason IN ('starting_grant','hire_unit','raid','test_reset'));
ALTER TABLE barony_reset_audit
    ADD COLUMN removed_generals integer NOT NULL DEFAULT 0,
    ADD COLUMN reset_gold integer NOT NULL DEFAULT 0,
    ADD COLUMN reset_resources integer NOT NULL DEFAULT 0;
