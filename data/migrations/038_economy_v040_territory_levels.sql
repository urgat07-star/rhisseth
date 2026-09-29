-- Economy v0.4.0: normative values from Google sheet «Уровень гексов».
-- All playable and neutral hexes use levels 1..8; the level participates in formulas.
UPDATE hexes SET data=data || jsonb_build_object('Уровень гекса','1','Постройка','нет построек')
WHERE COALESCE(data->>'Уровень гекса','0')='0';
UPDATE hexes SET data=data || jsonb_build_object('Население','1');
DELETE FROM raid_balance WHERE building_level=0;
DELETE FROM hex_building_levels WHERE level=0;
ALTER TABLE hex_building_levels DROP CONSTRAINT IF EXISTS hex_building_levels_level_check;
ALTER TABLE hex_building_levels ADD CONSTRAINT hex_building_levels_level_check CHECK (level BETWEEN 1 AND 8);

-- Preserve existing building meaning before changing the numeric catalogue.
UPDATE hexes SET data = data || jsonb_build_object(
 'Уровень гекса', CASE data->>'Постройка'
  WHEN 'Лагерь' THEN '2' WHEN 'Поселение' THEN '3' WHEN 'Деревня' THEN '4'
  WHEN 'Крепость' THEN '5' WHEN 'Форпост' THEN '5' WHEN 'Город' THEN '7'
  WHEN 'Столица' THEN '8' ELSE data->>'Уровень гекса' END,
 'Постройка', CASE data->>'Постройка' WHEN 'Форпост' THEN 'Крепость' ELSE data->>'Постройка' END
) WHERE data->>'Постройка' IN ('Лагерь','Поселение','Деревня','Форпост','Крепость','Город','Столица');

UPDATE hex_building_levels SET name='legacy-' || level || '-' || name;
INSERT INTO hex_building_levels
 (level,name,upkeep,population_limit,structure,defense,feature,resource_multiplier)
VALUES
 (1,'нет построек',NULL,3,'нет построек',NULL,'Первый экономический уровень',0),
 (2,'Лагерь',NULL,15,'Лагерь',NULL,'Экономические параметры economy v0.4.0',0),
 (3,'Поселение',1,40,'Поселение',NULL,'Экономические параметры economy v0.4.0',2),
 (4,'Деревня',2,80,'Деревня',2,'Защитники получают +1 защиты',3),
 (5,'Крепость',6,120,'Крепость',3,'Для захвата нужны осадные орудия',0),
 (6,'Замок',4,170,'Замок',2,'Военные параметры требуют отдельной балансировки',0),
 (7,'Город',8,250,'Город',3,'Для захвата нужны осадные орудия; +2 защиты',4),
 (8,'Столица',10,500,'Столица',4,'Особые правила столицы уточняются',5)
ON CONFLICT (level) DO UPDATE SET name=EXCLUDED.name,upkeep=EXCLUDED.upkeep,
 population_limit=EXCLUDED.population_limit,structure=EXCLUDED.structure,
 defense=EXCLUDED.defense,feature=EXCLUDED.feature,resource_multiplier=EXCLUDED.resource_multiplier;

CREATE TABLE territory_level_economy (
 level smallint PRIMARY KEY REFERENCES hex_building_levels(level),
 population_limit integer NOT NULL CHECK (population_limit >= 0),
 population_growth_min integer NOT NULL CHECK (population_growth_min >= 0),
 population_growth_max integer NOT NULL CHECK (population_growth_max >= population_growth_min),
 tax_min integer NOT NULL CHECK (tax_min >= 0),
 tax_max integer NOT NULL CHECK (tax_max >= tax_min),
 wood_cost integer NOT NULL DEFAULT 0 CHECK (wood_cost >= 0),
 stone_cost integer NOT NULL DEFAULT 0 CHECK (stone_cost >= 0),
 marble_cost integer NOT NULL DEFAULT 0 CHECK (marble_cost >= 0),
 source_note text NOT NULL DEFAULT ''
);
INSERT INTO territory_level_economy
 (level,population_limit,population_growth_min,population_growth_max,tax_min,tax_max,wood_cost,stone_cost,marble_cost,source_note)
VALUES
 (1,3,1,1,0,0,0,0,0,'нет построек'),
 (2,15,1,3,1,5,50,15,0,'Лагерь'),
 (3,40,1,6,6,10,120,40,0,'Поселение'),
 (4,80,1,12,11,25,150,100,0,'Деревня'),
 (5,120,3,15,26,50,300,150,0,'Крепость'),
 (6,170,3,20,51,80,300,300,0,'Замок'),
 (7,250,5,40,81,110,500,400,30,'Город'),
 (8,500,5,50,111,150,1000,500,100,'Столица');

INSERT INTO raid_balance (building_level,gold,peasant_percent,morale_penalty,cooldown_turns,peasant_nominal)
SELECT 8,gold,peasant_percent,morale_penalty,cooldown_turns,peasant_nominal
FROM raid_balance WHERE building_level=7 ON CONFLICT (building_level) DO NOTHING;

COMMENT ON TABLE territory_level_economy IS
 'Economy v0.4.0, Google sheet «Уровень гексов», fetched 2026-09-28';

CREATE FUNCTION economy_generated_food(fertility integer, current_population integer,
    is_mountain boolean, is_neutral boolean)
RETURNS integer LANGUAGE sql IMMUTABLE STRICT AS $$
    SELECT CASE
        WHEN is_mountain AND is_neutral THEN 3
        ELSE GREATEST(fertility,0) * GREATEST(current_population,0)
             - GREATEST(current_population,0)
    END
$$;
COMMENT ON FUNCTION economy_generated_food(integer,integer,boolean,boolean) IS
 'v0.4.0 annual food delta: fertility * current population - current population; neutral mountains receive 3';
