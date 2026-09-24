CREATE TABLE hex_building_levels (
    level smallint PRIMARY KEY CHECK (level BETWEEN 0 AND 7),
    name text NOT NULL UNIQUE,
    upkeep integer,
    population_limit integer,
    structure text NOT NULL,
    defense integer,
    feature text NOT NULL,
    resource_multiplier integer NOT NULL CHECK (resource_multiplier BETWEEN 0 AND 5)
);

INSERT INTO hex_building_levels
    (level,name,upkeep,population_limit,structure,defense,feature,resource_multiplier)
VALUES
 (0,'- нет -',NULL,NULL,'- нет -',NULL,'Захватывается при соприкосновении с тремя захваченными гексами; случайное событие при входе армии',0),
 (1,'Лагерь',NULL,4,'Костёр со спальным мешком',NULL,'Захватывается в процессе битвы',0),
 (2,'Поселение',1,12,'Дома с костром',NULL,'Захватывается в процессе битвы',2),
 (3,'Деревня',2,20,'Дома за частоколом',2,'Захватывается в процессе битвы; защитники получают +1 защиты',3),
 (4,'Форпост',4,NULL,'Деревянный замок за частоколом',2,'Захватывается в процессе битвы; +1 защиты; экспедиционные войска возвращаются сюда',0),
 (5,'Крепость',6,NULL,'Каменная крепость',3,'Для захвата нужны осадные орудия; экспедиционные войска возвращаются сюда',0),
 (6,'Город',8,50,'Несколько домов и каменная башня',3,'Для захвата нужны осадные орудия; +2 защиты; экспедиционные войска возвращаются сюда',4),
 (7,'Столица',10,80,'Столица',4,'Особые правила столицы уточняются',5);

COMMENT ON TABLE hex_building_levels IS 'Справочник листа «Уровень гекса» игровой Google-таблицы';
