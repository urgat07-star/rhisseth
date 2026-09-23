CREATE TABLE unit_catalog (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL UNIQUE CHECK (length(name) BETWEEN 1 AND 120),
    troop_type text NOT NULL CHECK (length(troop_type) BETWEEN 1 AND 120),
    defense integer NOT NULL CHECK (defense BETWEEN 0 AND 100),
    attack integer NOT NULL CHECK (attack BETWEEN 0 AND 100),
    attack_range integer NOT NULL CHECK (attack_range BETWEEN 0 AND 100),
    speed integer NOT NULL CHECK (speed BETWEEN 0 AND 100),
    description text NOT NULL DEFAULT '',
    image_path text NOT NULL CHECK (image_path ~ '^(units/(unit|barbarians)-[0-9]{3}\.webp)$'),
    price text NOT NULL DEFAULT '',
    building text NOT NULL DEFAULT '',
    note text NOT NULL DEFAULT '',
    active boolean NOT NULL DEFAULT true,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE player_generals (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id integer NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
    icon text NOT NULL CHECK (icon IN ('general/gen-01.webp','general/gen-02.webp')),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX player_generals_user_idx ON player_generals(user_id);

CREATE TABLE player_general_units (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    general_id bigint NOT NULL REFERENCES player_generals(id) ON DELETE CASCADE,
    unit_id integer NOT NULL REFERENCES unit_catalog(id) ON DELETE RESTRICT,
    slot smallint NOT NULL CHECK (slot BETWEEN 1 AND 5),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (general_id, slot)
);

INSERT INTO unit_catalog(name,troop_type,defense,attack,attack_range,speed,description,image_path,price,building,note) VALUES
('Разведчик','Пехота',2,0,0,2,'Шустрый разведчик: быстро передвигается, скрытно проходит леса и запоминает увиденное.','units/unit-019.webp','1 ткань, 1 золото','???',''),
('Ополченец','Пехота / Ближний бой',1,1,1,1,'Мобилизованный крестьянин с деревянными вилами и тканевой одеждой.','units/unit-001.webp','1 дерево, 1 ткань, 1 золото','???',''),
('Копейщик','Пехота / Ближний бой',1,2,2,1,'Воин с копьём с бронзовым наконечником, грубой одеждой и кожаным колетом.','units/unit-002.webp','1 дерево, 1 бронза, 1 ткань, 1 кожа, 1 золото','',''),
('Охотник','Пехота / Дальний бой',1,1,3,1,'Крестьянин-охотник с охотничьим луком.','units/unit-007.webp','1 дерево, 1 ткань, 1 золото','???','Улучшение из ополченца'),
('Лучник','Пехота / Дальний бой',1,1,5,1,'Опытный охотник с мощным луком, грубой одеждой и кожаным колетом.','units/unit-008.webp','1 дерево, 1 ткань, 1 кожа, 1 Охотник','???','Улучшение из охотника'),
('Мечник','Пехота / Ближний бой',2,1,1,1,'Воин с коротким мечом и лёгкой защитной одеждой.','units/unit-009.webp','1 бронза, 1 ткань, 1 кожа, 2 золото','???',''),
('Стражник','Пехота / Ближний бой',2,2,1,1,'Опытный мечник в лёгкой кожаной броне с бронзовыми пластинами.','units/unit-010.webp','2 бронза, 1 ткань, 2 кожа, 3 золото','',''),
('Фалангист','Пехота / Ближний бой',3,2,2,1,'Опытный строевой боец с копьём, большим щитом и усиленным доспехом.','units/unit-011.webp','3 бронза, 1 ткань, 2 кожа, 3 золото','',''),
('Конный дружинник','Конники / Ближний бой',1,2,2,3,'Опытный всадник с саблей, щитом и коротким копьём.','units/unit-012.webp','3 бронза, 1 ткань, 2 кожа, 1 лошадь, 5 золото','',''),
('Конный лучник','Конники / Дальний бой',1,2,2,3,'Опытный всадник с луком и запасным коротким копьём.','units/unit-020.webp','2 бронза, 1 ткань, 2 кожа, 1 лошадь, 5 золото','',''),
('Пеший рыцарь','Пехота / Ближний бой',3,3,1,1,'Подготовленный воин в железных доспехах со щитом и железным мечом.','units/unit-013.webp','3 железа, 2 ткань, 1 кожа, 4 золота','',''),
('Конный рыцарь','Конники / Ближний бой',3,4,2,2,'Подготовленный конный воин в железных доспехах со щитом и мечом.','units/unit-014.webp','3 железа, 2 ткань, 1 кожа, 1 лошадь, 10 золота','',''),
('Барон 1','Конники / Ближний бой',3,5,2,2,'Барон в доспехах на боевом коне.','units/unit-015.webp','','',''),
('Барон 2','Конники / Ближний бой',3,5,2,2,'Барон в доспехах на боевом коне.','units/unit-016.webp','','',''),
('Барон 3','Конники / Ближний бой',3,5,2,2,'Барон в доспехах на боевом коне.','units/unit-017.webp','','',''),
('Ландскнехты','Пехота / Ближний бой',4,3,2,1,'Хорошо экипированные наёмники с длинными копьями для борьбы с конницей.','units/unit-018.webp','3 железа, 1 дерево, 2 ткань, 1 кожа, 4 золота','',''),
('Лесные дикари','Пехота / Ближний бой',1,2,1,1,'Независимые жители лесов и холмов, нападающие на отряды и караваны.','units/barbarians-001.webp','','',''),
('Кочевники','Конники / Ближний бой',1,3,1,3,'Независимые жители равнин, совершающие быстрые набеги.','units/barbarians-002.webp','','',''),
('Горцы','Пехота / Ближний бой',2,2,1,1,'Независимые жители гор, нападающие на проходящие отряды.','units/barbarians-003.webp','','',''),
('Дикари','Пехота / Ближний бой',1,2,1,1,'Независимые жители южных регионов, совершающие набеги.','units/barbarians-004.webp','','','');
