CREATE TABLE game_hex_peasants (
    q integer NOT NULL,
    r integer NOT NULL,
    quantity integer NOT NULL DEFAULT 0 CHECK (quantity>=0),
    PRIMARY KEY(q,r)
);
