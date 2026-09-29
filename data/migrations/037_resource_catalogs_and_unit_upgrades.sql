-- Economy v0.4.0: editable resource catalogues and normalized unit upgrades.
CREATE TABLE extractable_resources (
    code text PRIMARY KEY CHECK (code ~ '^[a-z][a-z0-9_]{1,63}$'),
    name text NOT NULL UNIQUE CHECK (length(name) BETWEEN 1 AND 120),
    typical_locations text NOT NULL DEFAULT '' CHECK (length(typical_locations) <= 2000),
    purpose text NOT NULL DEFAULT '' CHECK (length(purpose) <= 2000),
    active boolean NOT NULL DEFAULT true,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE produced_resources (
    code text PRIMARY KEY CHECK (code ~ '^[a-z][a-z0-9_]{1,63}$'),
    name text NOT NULL UNIQUE CHECK (length(name) BETWEEN 1 AND 120),
    ingredients text NOT NULL DEFAULT '' CHECK (length(ingredients) <= 2000),
    required_building text NOT NULL DEFAULT '' CHECK (length(required_building) <= 200),
    purpose text NOT NULL DEFAULT '' CHECK (length(purpose) <= 2000),
    active boolean NOT NULL DEFAULT true,
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO extractable_resources(code,name,typical_locations,purpose) VALUES
('wheat','Пшеница','Равнина, плодородное поле','Еда'),
('rye','Рожь','Равнина, плодородное поле','Еда'),
('barley','Ячмень','Равнина, плодородное поле','Еда'),
('rice','Рис','Речная долина','Еда'),
('game','Дичь','Редколесье, густой лес, тайга','Еда, кожа'),
('fish','Рыба','Море и побережье','Еда'),
('mollusks','Моллюски','Побережье и мелководье','Еда, торговля'),
('sea_beast','Морской зверь','Шельф, открытое море, глубоководье, рифы, промысловая зона','Еда, торговля'),
('algae','Водоросли','Побережье и мелководье','Еда, производство'),
('honey','Мёд','Редколесье, густой лес, тайга','Еда, торговля'),
('medicinal_herbs','Лекарственные травы','Специально назначенные гексы','Медицина, торговля'),
('salt','Соль','Побережье','Еда, торговля'),
('spices','Пряности','Редколесье, речная долина','Еда, торговля'),
('berries','Ягоды','Тундра, тайга','Еда'),
('wood','Дерево','Редколесье, густой лес, тайга','Строительство, найм'),
('stone','Камень','Холмы, горы, высокогорье','Строительство'),
('marble','Мрамор','Горы, высокогорье','Строительство, торговля'),
('ship_timber','Корабельный лес','Редколесье, густой лес','Найм, флот, торговля'),
('iron','Железо','Холмы, горы, болото','Найм, производство'),
('coal','Уголь','Холмы, горы','Производство'),
('flax','Лён','Равнина, луг, степь','Производство ткани'),
('horses','Лошади','Равнина, луг, степь','Найм конницы'),
('redwood','Красное дерево','Редколесье, густой лес','Торговля'),
('pearls','Жемчуг','Побережье, шельф, рифы','Торговля'),
('corals','Кораллы','Галечный берег, рифы','Торговля'),
('resin','Смола','Густой лес','Торговля, производство'),
('gold_ore','Золотая руда','Высокогорье','Торговля'),
('silver','Серебро','Высокогорье','Торговля'),
('gems','Самоцветы','Высокогорье, вулканическая земля','Торговля'),
('sand','Песок','Песчаный берег, дюны, пустыня, полупустыня','Производство стекла'),
('copper','Медь','Горы','Производство бронзы'),
('peat','Торф','Болото, тундра','Топливо'),
('clay','Глина','Речная долина','Строительство'),
('sulfur','Сера','Вулканическая земля','Производство'),
('obsidian','Обсидиан','Вулканическая земля','Торговля');

INSERT INTO produced_resources(code,name,ingredients,required_building,purpose) VALUES
('livestock','Скот','Корм, пастбище','','Еда, кожа, шерсть'),
('wine','Вино','Виноград','','Еда, торговля'),
('sauces','Соусы','Водоросли + рыба/моллюски/морской зверь','','Еда, торговля'),
('glass','Стекло','Песок + уголь','','Строительство, торговля'),
('bronze','Бронза','Медь + олово','','Найм'),
('steel','Сталь','Железо + уголь','','Найм'),
('cloth','Ткань','Лён/другое волокно','','Найм'),
('leather','Кожа/мех','Скот или дичь','','Найм, торговля'),
('wool','Шерсть','Скот','','Производство ткани');

CREATE TABLE unit_upgrade_requirements (
    unit_id integer PRIMARY KEY REFERENCES unit_catalog(id) ON DELETE CASCADE,
    predecessor_unit_id integer NOT NULL REFERENCES unit_catalog(id) ON DELETE RESTRICT,
    CHECK (unit_id <> predecessor_unit_id)
);

INSERT INTO unit_upgrade_requirements(unit_id,predecessor_unit_id)
SELECT target.id,source.id FROM unit_catalog target CROSS JOIN unit_catalog source
WHERE (target.name='Охотник' AND source.name='Ополченец')
   OR (target.name='Лучник' AND source.name='Охотник');

DELETE FROM unit_resource_costs WHERE resource_code='gold' AND unit_id IN
    (SELECT id FROM unit_catalog WHERE name IN ('Охотник','Лучник'));
UPDATE unit_catalog SET price='1 дерево, 1 ткань, 1 Ополченца',note='Апгрейд из ополченца' WHERE name='Охотник';
UPDATE unit_catalog SET price='1 дерево, 1 ткань, 1 кожа, 1 Охотник',note='Апгрейд из охотника' WHERE name='Лучник';
