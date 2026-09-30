ALTER TABLE unit_catalog ADD COLUMN counterattack integer NOT NULL DEFAULT 1 CHECK (counterattack BETWEEN 0 AND 100);
ALTER TABLE game_battle_units ADD COLUMN counterattack integer NOT NULL DEFAULT 0 CHECK (counterattack BETWEEN 0 AND 100);
ALTER TABLE game_battle_units ADD COLUMN movement_spent integer NOT NULL DEFAULT 0 CHECK (movement_spent BETWEEN 0 AND 100);
