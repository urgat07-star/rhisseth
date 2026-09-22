CREATE TABLE crests (
    filename text PRIMARY KEY,
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    file_size bigint NOT NULL CHECK (file_size > 0),
    active boolean NOT NULL DEFAULT true,
    discovered_at timestamptz NOT NULL DEFAULT now(),
    checked_at timestamptz NOT NULL DEFAULT now(),
    CHECK (filename ~ '^gerb_[0-9]+[.]webp$')
);

CREATE INDEX crests_active_idx ON crests(active) WHERE active;
