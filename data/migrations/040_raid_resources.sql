-- Economy v0.4.0: make every active extractable hex resource creditable to
-- the federal inventory after a successful raid.
INSERT INTO game_resources(code,name,starting_quantity)
SELECT CASE WHEN code='horses' THEN 'horse' ELSE code END,name,0
FROM extractable_resources
WHERE active
ON CONFLICT DO NOTHING;

INSERT INTO game_inventory(user_id,resource_code,quantity)
SELECT w.user_id,r.code,0
FROM game_wallets w
CROSS JOIN game_resources r
ON CONFLICT(user_id,resource_code) DO NOTHING;
