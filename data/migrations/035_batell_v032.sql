-- The new tactical board has eight rows. Existing active battles outside it
-- must be resolved before deployment; silently moving units could change combat.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM game_battle_units u JOIN game_battles b ON b.id=u.battle_id
        WHERE b.status='active' AND (u.x>=8 OR u.y>=8)
    ) THEN
        RAISE EXCEPTION 'Finish active 10x10 battles before applying batell v0.3.2';
    END IF;
END $$;

DELETE FROM game_deployment_template WHERE y>=8;
UPDATE raid_balance SET cooldown_turns=4 WHERE cooldown_turns=5;
ALTER TABLE player_generals ADD COLUMN last_moved_turn bigint;
UPDATE player_generals pg SET last_moved_turn=(SELECT turn_number FROM game_clock WHERE id=true)
FROM general_catalog gc WHERE pg.catalog_id=gc.id AND pg.logistics_left<gc.logistics;
