ALTER TABLE raid_balance ADD COLUMN peasant_nominal integer NOT NULL DEFAULT 10
    CHECK (peasant_nominal>=0);
UPDATE raid_balance SET peasant_nominal=CASE building_level
    WHEN 0 THEN 10 WHEN 1 THEN 20 WHEN 2 THEN 40 WHEN 3 THEN 60
    WHEN 4 THEN 100 WHEN 5 THEN 150 WHEN 6 THEN 250 ELSE 400 END;

CREATE TABLE game_hex_raids (
    q integer NOT NULL,
    r integer NOT NULL,
    last_turn bigint NOT NULL,
    PRIMARY KEY(q,r)
);
CREATE TABLE game_hex_morale (
    q integer NOT NULL,
    r integer NOT NULL,
    morale numeric(6,2) NOT NULL DEFAULT 100 CHECK (morale BETWEEN 0 AND 100),
    PRIMARY KEY(q,r)
);
CREATE TABLE barony_peasant_reserve (
    user_id integer PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    quantity integer NOT NULL DEFAULT 0 CHECK (quantity>=0)
);
