-- Economy v0.4.0: «Дополнительные постройки» from the Google workbook.
CREATE TABLE additional_building_catalog (
    code text PRIMARY KEY CHECK (code ~ '^[a-z][a-z0-9_]{1,63}$'),
    name text NOT NULL UNIQUE CHECK (length(name) BETWEEN 1 AND 120),
    level_1_effect text NOT NULL DEFAULT '' CHECK (length(level_1_effect) <= 2000),
    level_2_effect text NOT NULL DEFAULT '' CHECK (length(level_2_effect) <= 2000),
    level_3_effect text NOT NULL DEFAULT '' CHECK (length(level_3_effect) <= 2000),
    image_path text NOT NULL DEFAULT '' CHECK (length(image_path) <= 500),
    note text NOT NULL DEFAULT '' CHECK (length(note) <= 4000),
    active boolean NOT NULL DEFAULT true,
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO additional_building_catalog
    (code,name,level_1_effect,level_2_effect,level_3_effect,image_path,note,active)
VALUES
('port','Порт','Плодородие +1; Торговля +1','Плодородие +2; Торговля +2','Плодородие +3; Торговля +3; Постройка Верфи','','Только прибрежные и островные гексы; доступен с уровня территории 1',true),
('shipyard','Верфь','Торговля +1; Торговая лодья','Торговля +2; Боевые корабли','Торговля +3; Торговый Галеон','','Только прибрежные и островные гексы; требует Порт 3 уровня',true),
('lighthouse','Маяк','','','','','Эффекты и условия в источнике не заполнены',false),
('water_farm','Ферма на воде','Плодородие +1; Ресурсы +1','Плодородие +2; Ресурсы +2','Плодородие +3; Ресурсы +3','','Прибрежные/островные гексы либо гексы с рекой; доступна с уровня территории 1',true),
('vineyard','Виноградник','Плодородие +1; Ресурсы +1','Плодородие +2; Ресурсы +2','Плодородие +3; Ресурсы +3','','Только гексы с рекой; доступен с уровня территории 1',true),
('pasture','Пастбище','Плодородие +1; Ресурсы +1','Плодородие +2; Ресурсы +2','Плодородие +3; Ресурсы +3','','Равнины и холмы; доступно с уровня территории 3; даёт ресурс Скот',true),
('farm','Ферма','Плодородие +1; Ресурсы +1','Плодородие +2; Ресурсы +2','Плодородие +3; Ресурсы +3','','Равнины и холмы; доступна с уровня территории 3; даёт ресурс Скот',true),
('sawmill','Лесопилка','Ресурсы +1; Население +5','Ресурсы +2; Население +10','Ресурсы +3; Население +15','','Только лесные гексы; доступна с уровня территории 1',true),
('apiary','Пасека','Плодородие +1; Ресурсы +1','Плодородие +2; Ресурсы +2','Плодородие +3; Ресурсы +3','','Только лесные гексы; доступна с уровня территории 1',true),
('mine','Шахта','Ресурсы +1; Население +5','Ресурсы +2; Население +10','Ресурсы +3; Население +15','','Только гексы с холмами; доступна с уровня территории 1',true),
('ore_mine','Рудник','Ресурсы +1; Население +5','Ресурсы +2; Население +10','Ресурсы +3; Население +15','','Только горные гексы; доступен с уровня территории 1',true),
('fort','Форт','Защита +1; Население +5; Стражники 1','Защита +2; Население +10; Стражники 2; Лучник 1','Защита +3; Население +15; Пеший Рыцарь 1; Стражники 2; Лучник 2','','Колониальная постройка на гексе вне владения игрока; использует федеральную еду при дефиците',true);

CREATE TABLE hex_additional_buildings (
    q integer NOT NULL,
    r integer NOT NULL,
    building_code text NOT NULL REFERENCES additional_building_catalog(code),
    building_level smallint NOT NULL CHECK (building_level BETWEEN 1 AND 3),
    built_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (q,r,building_code),
    FOREIGN KEY (q,r) REFERENCES hexes(q,r) ON DELETE CASCADE
);

COMMENT ON COLUMN additional_building_catalog.image_path IS
    'Reserved optional image address; stored but not used by v0.4.0 UI or game rules';
