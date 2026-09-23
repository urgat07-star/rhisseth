ALTER TABLE general_catalog
    ADD COLUMN experience_per_level integer NOT NULL DEFAULT 100 CHECK (experience_per_level BETWEEN 1 AND 1000000),
    ADD COLUMN max_level integer NOT NULL DEFAULT 10 CHECK (max_level BETWEEN 1 AND 100),
    ADD COLUMN max_attack_bonus integer NOT NULL DEFAULT 5 CHECK (max_attack_bonus BETWEEN 0 AND 100),
    ADD COLUMN max_defense_bonus integer NOT NULL DEFAULT 5 CHECK (max_defense_bonus BETWEEN 0 AND 100);

ALTER TABLE player_generals
    ADD COLUMN experience integer NOT NULL DEFAULT 0 CHECK (experience >= 0),
    ADD COLUMN level integer NOT NULL DEFAULT 1 CHECK (level BETWEEN 1 AND 100),
    ADD COLUMN attack_bonus integer NOT NULL DEFAULT 0 CHECK (attack_bonus BETWEEN 0 AND 100),
    ADD COLUMN defense_bonus integer NOT NULL DEFAULT 0 CHECK (defense_bonus BETWEEN 0 AND 100);

CREATE TABLE general_skill_catalog (id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY, code text NOT NULL UNIQUE, name text NOT NULL UNIQUE, description text NOT NULL DEFAULT '', is_positive boolean NOT NULL, active boolean NOT NULL DEFAULT true);
CREATE TABLE player_general_skills (general_id bigint NOT NULL REFERENCES player_generals(id) ON DELETE CASCADE, skill_id integer NOT NULL REFERENCES general_skill_catalog(id) ON DELETE RESTRICT, acquired_level integer NOT NULL CHECK (acquired_level BETWEEN 2 AND 100), acquired_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (general_id,skill_id));
INSERT INTO general_skill_catalog(code,name,description,is_positive) VALUES
('inspiring','Воодушевляющий','Повышает мораль армии.',true),('tactician','Тактик','Даёт тактическое преимущество.',true),
('reckless','Безрассудный','Повышает риск необдуманной атаки.',false),('slow','Медлительный','Снижает мобильность армии.',false);
