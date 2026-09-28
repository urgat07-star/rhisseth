-- Original 2–3 hexes recovered from the earliest verified VDS dumps per barony.
-- Backup evidence: 20260922-101654-after-hosting.dump (IDs 1 and 3),
-- 20260922-112911-before-map-v5.dump (IDs 4 and 5).
-- The first available dump for barony 6 already included one captured hex.
-- Its original three cells were confirmed by the owner on 2026-09-24.
WITH original(barony_id,user_id,position,q,r) AS (VALUES
    (1,20,1,13,6),(1,20,2,13,7),(1,20,3,14,6),
    (3,5,1,16,7),(3,5,2,16,8),(3,5,3,17,7),
    (4,21,1,11,11),(4,21,2,12,10),(4,21,3,13,10),
    (5,24,1,6,17),(5,24,2,6,18),(5,24,3,7,17),
    (6,6,1,6,14),(6,6,2,7,13),(6,6,3,7,14)
)
INSERT INTO barony_start_hexes(barony_id,position,q,r)
SELECT b.id,o.position,o.q,o.r FROM original o
JOIN player_baronies b ON b.id=o.barony_id AND b.user_id=o.user_id
WHERE NOT EXISTS (SELECT 1 FROM barony_start_hexes s WHERE s.barony_id=b.id);
