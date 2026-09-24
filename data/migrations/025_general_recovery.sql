ALTER TABLE player_generals ADD COLUMN recover_turn bigint;
CREATE INDEX player_generals_recovery_idx ON player_generals(recover_turn)
    WHERE status='recovering';
