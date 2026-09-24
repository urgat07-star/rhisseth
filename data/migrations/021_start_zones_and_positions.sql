CREATE TABLE barony_start_hexes (
    barony_id integer NOT NULL REFERENCES player_baronies(id) ON DELETE CASCADE,
    position smallint NOT NULL CHECK (position BETWEEN 1 AND 3),
    q integer NOT NULL,
    r integer NOT NULL,
    PRIMARY KEY(barony_id,position),
    UNIQUE(barony_id,q,r),
    UNIQUE(q,r)
);

ALTER TABLE player_generals
    ADD COLUMN q integer,
    ADD COLUMN r integer,
    ADD COLUMN previous_q integer,
    ADD COLUMN previous_r integer,
    ADD COLUMN logistics_left integer NOT NULL DEFAULT 10 CHECK (logistics_left >= 0),
    ADD CONSTRAINT general_location_consistency CHECK ((q IS NULL) = (r IS NULL)),
    ADD CONSTRAINT general_previous_consistency CHECK ((previous_q IS NULL) = (previous_r IS NULL));

-- Older baronies need their original zones restored explicitly from reviewed evidence.
-- Existing generals receive a temporary location in a currently owned hex;
-- reset to a recorded starting zone will place them correctly.
UPDATE player_generals pg SET (q,r)=(
    SELECT h.q,h.r FROM hexes h
    WHERE h.data->>'Тип владельца'='Игрок' AND h.data->>'Владелец'=pg.user_id::text
    ORDER BY h.q,h.r LIMIT 1
) WHERE pg.q IS NULL;

CREATE TABLE barony_reset_audit (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_user_id integer REFERENCES users(user_id) ON DELETE SET NULL,
    baronies_count integer NOT NULL,
    released_hexes integer NOT NULL,
    restored_hexes integer NOT NULL,
    previous_turn bigint NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE barony_start_zone_audit (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_user_id integer REFERENCES users(user_id) ON DELETE SET NULL,
    barony_id integer NOT NULL REFERENCES player_baronies(id) ON DELETE CASCADE,
    old_cells jsonb NOT NULL,
    new_cells jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
