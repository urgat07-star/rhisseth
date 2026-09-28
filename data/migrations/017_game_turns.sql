CREATE TABLE game_clock (
    id boolean PRIMARY KEY DEFAULT true CHECK (id),
    turn_number bigint NOT NULL DEFAULT 0 CHECK (turn_number >= 0),
    started_at timestamptz NOT NULL DEFAULT now(),
    ends_at timestamptz NOT NULL DEFAULT (now() + interval '12 hours')
);
INSERT INTO game_clock(id) VALUES (true);

CREATE TABLE game_presence (
    user_id integer PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    seen_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX game_presence_seen_idx ON game_presence(seen_at);

CREATE TABLE game_turn_votes (
    turn_number bigint NOT NULL,
    user_id integer NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    voted_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(turn_number, user_id)
);

CREATE TABLE game_clock_audit (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_user_id integer REFERENCES users(user_id) ON DELETE SET NULL,
    old_turn_number bigint NOT NULL,
    new_turn_number bigint NOT NULL,
    action text NOT NULL CHECK (action IN ('deadline','votes','admin_set','admin_reset')),
    created_at timestamptz NOT NULL DEFAULT now()
);
