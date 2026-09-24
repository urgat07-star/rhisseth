ALTER TABLE unit_catalog DROP CONSTRAINT IF EXISTS unit_catalog_image_path_check;
ALTER TABLE unit_catalog ADD CONSTRAINT unit_catalog_image_path_check
    CHECK (image_path ~ '^units/(unit|barbarians|animal)-[0-9]{3}\.webp$');
ALTER TABLE unit_catalog ADD COLUMN combat_level smallint NOT NULL DEFAULT 1 CHECK (combat_level BETWEEN 1 AND 5);

INSERT INTO unit_catalog(name,troop_type,health,armor,defense,attack,attack_range,speed,initiative,morale,description,image_path,active,combat_level)
VALUES ('Дикое животное','Животное / Ближний бой',5,0,1,1,1,1,1,100,
    'Начальные характеристики уровня крестьянина; доступны для изменения в каталоге.',
    'units/animal-001.webp',true,1);

CREATE TABLE raid_balance (
    building_level smallint PRIMARY KEY REFERENCES hex_building_levels(level),
    gold integer NOT NULL CHECK (gold >= 0),
    peasant_percent integer NOT NULL CHECK (peasant_percent BETWEEN 0 AND 100),
    morale_penalty integer NOT NULL CHECK (morale_penalty BETWEEN 0 AND 100),
    cooldown_turns integer NOT NULL CHECK (cooldown_turns BETWEEN 0 AND 100)
);
INSERT INTO raid_balance(building_level,gold,peasant_percent,morale_penalty,cooldown_turns) VALUES
    (0,1,10,10,5),(1,2,10,10,5),(2,3,10,10,5),(3,5,10,10,5),
    (4,8,10,10,5),(5,12,10,10,5),(6,20,10,10,5),(7,30,10,10,5);

UPDATE hex_building_levels SET feature='Захват после победы в бою при соседстве с собственной территорией; случайное событие при входе армии' WHERE level=0;
UPDATE hex_building_levels SET feature='Захват после победы в обычном бою; механика осады будет добавлена позднее' WHERE level IN (5,6);
