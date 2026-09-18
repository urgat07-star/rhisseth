CREATE TABLE player_barony_audit (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id integer REFERENCES users(user_id) ON DELETE SET NULL,
    barony_id integer NOT NULL,
    action text NOT NULL CHECK (action IN ('crest','abandon')),
    details jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);
