ALTER TABLE game_clock_audit DROP CONSTRAINT game_clock_audit_action_check;
ALTER TABLE game_clock_audit ADD CONSTRAINT game_clock_audit_action_check
    CHECK (action IN ('deadline','votes','admin_set','admin_reset','test_skip'));
