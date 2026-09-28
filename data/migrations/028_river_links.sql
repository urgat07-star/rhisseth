CREATE TABLE game_river_links (
    q1 integer NOT NULL,
    r1 integer NOT NULL,
    q2 integer NOT NULL,
    r2 integer NOT NULL,
    PRIMARY KEY(q1,r1,q2,r2),
    CHECK ((q1,r1)<(q2,r2))
);
