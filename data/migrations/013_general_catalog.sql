CREATE TABLE general_catalog (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL UNIQUE CHECK (length(name) BETWEEN 1 AND 120),
    description text NOT NULL DEFAULT '',
    image_path text NOT NULL CHECK (image_path ~ '^general/gen-[0-9]{2}\.webp$'),
    health integer NOT NULL DEFAULT 10 CHECK (health BETWEEN 1 AND 10000),
    attack integer NOT NULL DEFAULT 1 CHECK (attack BETWEEN 0 AND 100),
    defense integer NOT NULL DEFAULT 1 CHECK (defense BETWEEN 0 AND 100),
    initiative integer NOT NULL DEFAULT 1 CHECK (initiative BETWEEN 0 AND 100),
    speed integer NOT NULL DEFAULT 1 CHECK (speed BETWEEN 0 AND 100),
    logistics integer NOT NULL DEFAULT 10 CHECK (logistics BETWEEN 0 AND 10000),
    skills text NOT NULL DEFAULT '',
    active boolean NOT NULL DEFAULT true,
    updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO general_catalog(name,description,image_path) VALUES
('Генерал 1','Базовый генерал','general/gen-01.webp'),
('Генерал 2','Базовый генерал','general/gen-02.webp'),
('Генерал 3','Новый генерал','general/gen-03.webp');
ALTER TABLE player_generals ADD COLUMN catalog_id integer REFERENCES general_catalog(id) ON DELETE RESTRICT;
UPDATE player_generals pg SET catalog_id=gc.id FROM general_catalog gc WHERE pg.icon=gc.image_path;
