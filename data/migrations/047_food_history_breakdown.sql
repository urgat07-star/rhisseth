-- Expose the components of the annual food balance in the player history.
ALTER TABLE hex_economy_history
    ADD COLUMN food_production integer NOT NULL DEFAULT 0,
    ADD COLUMN reserve_food_used integer NOT NULL DEFAULT 0 CHECK (reserve_food_used >= 0);

-- Preserve every historical balance first. For player capitals the production
-- can be reconstructed from the stored population and the hex fertility.
UPDATE hex_economy_history SET food_production=food_delta;

WITH capitals AS (
    SELECT b.id AS barony_id,s.q,s.r
    FROM player_baronies b
    JOIN barony_start_hexes s ON s.barony_id=b.id
    WHERE s.position=1
), reconstructed AS (
    SELECT h.year,h.q,h.r,
           GREATEST(0,h.population_before *
             (GREATEST(0,CASE WHEN x.data->>'Плодородие' ~ '^[0-9]+$'
                THEN (x.data->>'Плодородие')::integer ELSE 0 END)-1)) AS production
    FROM hex_economy_history h
    JOIN capitals c ON c.barony_id=h.barony_id AND c.q=h.q AND c.r=h.r
    JOIN hexes x ON x.q=h.q AND x.r=h.r
    WHERE h.owner_type='Игрок'
)
UPDATE hex_economy_history h
SET food_production=r.production,
    reserve_food_used=GREATEST(0,r.production-h.food_delta)
FROM reconstructed r
WHERE h.year=r.year AND h.q=r.q AND h.r=r.r;
