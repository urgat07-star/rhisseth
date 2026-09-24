ALTER TABLE game_battles ADD COLUMN last_side text NOT NULL DEFAULT ''
    CHECK (last_side IN ('','attacker','defender'));
