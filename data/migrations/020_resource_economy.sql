CREATE TABLE game_resources (
    code text PRIMARY KEY,
    name text NOT NULL UNIQUE,
    starting_quantity integer NOT NULL DEFAULT 100 CHECK (starting_quantity >= 0)
);
INSERT INTO game_resources(code,name) VALUES
    ('wood','Дерево'),('cloth','Ткань'),('bronze','Бронза'),
    ('leather','Кожа'),('iron','Железо'),('horse','Лошади');

CREATE TABLE game_inventory (
    user_id integer NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    resource_code text NOT NULL REFERENCES game_resources(code),
    quantity integer NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    PRIMARY KEY(user_id,resource_code)
);
INSERT INTO game_inventory(user_id,resource_code,quantity)
SELECT w.user_id,r.code,r.starting_quantity FROM game_wallets w CROSS JOIN game_resources r;

CREATE TABLE game_resource_ledger (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id integer NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    resource_code text NOT NULL REFERENCES game_resources(code),
    amount integer NOT NULL CHECK (amount <> 0),
    reason text NOT NULL CHECK (reason IN ('starting_grant','hire_unit','raid')),
    related_general_id bigint,
    created_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO game_resource_ledger(user_id,resource_code,amount,reason)
SELECT user_id,resource_code,quantity,'starting_grant' FROM game_inventory WHERE quantity>0;

ALTER TABLE game_gold_ledger DROP CONSTRAINT game_gold_ledger_reason_check;
ALTER TABLE game_gold_ledger ADD CONSTRAINT game_gold_ledger_reason_check
    CHECK (reason IN ('starting_grant','hire_general','hire_unit','ransom_paid','ransom_received','raid'));

CREATE TABLE unit_resource_costs (
    unit_id integer NOT NULL REFERENCES unit_catalog(id) ON DELETE CASCADE,
    resource_code text NOT NULL CHECK (resource_code IN ('gold','wood','cloth','bronze','leather','iron','horse')),
    quantity integer NOT NULL CHECK (quantity > 0),
    PRIMARY KEY(unit_id,resource_code)
);
ALTER TABLE unit_catalog ADD COLUMN purchasable boolean NOT NULL DEFAULT false;

WITH costs(image,resource,quantity) AS (VALUES
('unit-019.webp','cloth',1),('unit-019.webp','gold',1),
('unit-001.webp','wood',1),('unit-001.webp','cloth',1),('unit-001.webp','gold',1),
('unit-002.webp','wood',1),('unit-002.webp','bronze',1),('unit-002.webp','cloth',1),('unit-002.webp','leather',1),('unit-002.webp','gold',1),
('unit-007.webp','wood',1),('unit-007.webp','cloth',1),('unit-007.webp','gold',1),
('unit-008.webp','wood',1),('unit-008.webp','cloth',1),('unit-008.webp','leather',1),('unit-008.webp','gold',1),
('unit-009.webp','bronze',1),('unit-009.webp','cloth',1),('unit-009.webp','leather',1),('unit-009.webp','gold',2),
('unit-010.webp','bronze',2),('unit-010.webp','cloth',1),('unit-010.webp','leather',2),('unit-010.webp','gold',3),
('unit-011.webp','bronze',3),('unit-011.webp','cloth',1),('unit-011.webp','leather',2),('unit-011.webp','gold',3),
('unit-012.webp','bronze',3),('unit-012.webp','cloth',1),('unit-012.webp','leather',2),('unit-012.webp','horse',1),('unit-012.webp','gold',5),
('unit-020.webp','bronze',2),('unit-020.webp','cloth',1),('unit-020.webp','leather',2),('unit-020.webp','horse',1),('unit-020.webp','gold',5),
('unit-013.webp','iron',3),('unit-013.webp','cloth',2),('unit-013.webp','leather',1),('unit-013.webp','gold',4),
('unit-014.webp','iron',3),('unit-014.webp','cloth',2),('unit-014.webp','leather',1),('unit-014.webp','horse',1),('unit-014.webp','gold',10),
('unit-018.webp','iron',3),('unit-018.webp','wood',1),('unit-018.webp','cloth',2),('unit-018.webp','leather',1),('unit-018.webp','gold',4))
INSERT INTO unit_resource_costs(unit_id,resource_code,quantity)
SELECT u.id,c.resource,c.quantity FROM costs c JOIN unit_catalog u ON u.image_path='units/'||c.image;

UPDATE unit_catalog SET purchasable=true WHERE id IN (SELECT unit_id FROM unit_resource_costs);
UPDATE unit_catalog SET price='1 дерево, 1 ткань, 1 кожа, 1 золото'
WHERE image_path='units/unit-008.webp';
