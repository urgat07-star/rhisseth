CREATE TABLE hexes (
    q integer NOT NULL,
    r integer NOT NULL,
    data jsonb NOT NULL CHECK (jsonb_typeof(data) = 'object'),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (q, r),
    CHECK (data ? 'Q' AND data ? 'R'),
    CHECK (data->>'Q' IS NOT NULL AND data->>'R' IS NOT NULL),
    CHECK (data->>'Q' = q::text AND data->>'R' = r::text)
);
