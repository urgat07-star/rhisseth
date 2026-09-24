ALTER TABLE game_battles ADD COLUMN deployment_locked boolean NOT NULL DEFAULT false;
CREATE TABLE game_deployment_template (
    user_id integer NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    slot smallint NOT NULL CHECK (slot BETWEEN 0 AND 5),
    x smallint NOT NULL CHECK (x BETWEEN 0 AND 3),
    y smallint NOT NULL CHECK (y BETWEEN 0 AND 9),
    PRIMARY KEY(user_id,slot),
    UNIQUE(user_id,x,y)
);
