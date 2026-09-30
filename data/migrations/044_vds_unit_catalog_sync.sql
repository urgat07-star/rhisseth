-- Snapshot of the administrator-edited military catalogue exported read-only
-- from the Rhisseth VDS on 2026-09-30. Names/IDs identify the existing rows;
-- numeric combat parameters, display price, availability and upgrade links are
-- intentionally versioned here so a rebuilt database reproduces production.
WITH values_from_vds(id,armor,defense,attack,attack_range,speed,initiative,morale,price,building,note,active,combat_level,purchasable) AS (VALUES
 (1,0,1,1,1,2,3,100,'1 ткань, 1 золото','нет','',true,1,true),
 (2,0,1,1,1,1,1,100,'1 дерево, 1 ткань, 1 золото','???','',true,1,true),
 (3,1,1,2,2,1,2,100,'1 дерево, 1 бронза, 1 ткань, 1 кожа, 1 золото','','',true,2,true),
 (4,0,1,1,3,1,2,100,'1 дерево, 1 ткань, 1 Ополченца','???','Апгрейд из ополченца',true,1,true),
 (5,1,1,1,4,1,3,100,'1 дерево, 1 ткань, 1 кожа, 1 Охотник','???','Апгрейд из охотника',true,2,true),
 (6,1,2,1,1,1,2,100,'1 бронза, 1 ткань, 1 кожа, 2 золото','???','',true,2,true),
 (7,2,2,2,1,1,3,100,'2 бронза, 1 ткань, 2 кожа, 3 золото','','',true,2,true),
 (8,2,3,2,2,1,2,100,'3 бронза, 1 ткань, 2 кожа, 3 золото','','',true,3,true),
 (9,2,1,2,2,3,4,100,'3 бронза, 1 ткань, 2 кожа, 1 лошадь, 5 золото','','',true,3,true),
 (10,2,1,2,3,3,5,100,'2 бронза, 1 ткань, 2 кожа, 1 лошадь, 5 золото','','',true,3,true),
 (11,4,3,3,1,1,3,100,'3 железа, 2 ткань, 1 кожа, 4 золота','','',true,4,true),
 (12,4,3,4,1,2,3,100,'3 железа, 2 ткань, 1 кожа, 1 лошадь, 10 золота','','',true,4,true),
 (13,4,3,5,2,2,4,100,'4 железа, 2 ткань, 1 кожа, 1 лошадь, 20 золота','','',true,5,false),
 (14,4,3,5,2,2,4,100,'4 железа, 2 ткань, 1 кожа, 1 лошадь, 20 золота','','',true,5,false),
 (15,4,3,5,2,2,4,100,'4 железа, 2 ткань, 1 кожа, 1 лошадь, 20 золота','','',true,5,false),
 (16,4,3,3,2,1,3,100,'3 железа, 1 дерево, 2 ткань, 1 кожа, 4 золота','','',true,4,true),
 (17,0,1,2,1,1,4,100,'','','',true,1,false),
 (18,0,1,3,3,3,3,100,'','','',true,2,false),
 (19,1,2,2,1,1,3,100,'','','',true,3,false),
 (20,0,1,2,1,2,3,100,'','','',true,4,false),
 (21,0,1,1,1,2,4,100,'','','',true,1,false)
)
UPDATE unit_catalog u SET armor=v.armor,defense=v.defense,attack=v.attack,
 attack_range=v.attack_range,speed=v.speed,initiative=v.initiative,morale=v.morale,
 price=v.price,building=v.building,note=v.note,active=v.active,
 combat_level=v.combat_level,purchasable=v.purchasable,updated_at=now()
FROM values_from_vds v WHERE u.id=v.id;

DELETE FROM unit_resource_costs WHERE unit_id BETWEEN 1 AND 21;
INSERT INTO unit_resource_costs(unit_id,resource_code,quantity) VALUES
 (1,'gold',1),(1,'cloth',1),
 (2,'gold',1),(2,'wood',1),(2,'cloth',1),
 (3,'gold',1),(3,'wood',1),(3,'cloth',1),(3,'bronze',1),(3,'leather',1),
 (4,'wood',1),(4,'cloth',1),
 (5,'wood',1),(5,'cloth',1),(5,'leather',1),
 (6,'gold',2),(6,'cloth',1),(6,'bronze',1),(6,'leather',1),
 (7,'gold',3),(7,'cloth',1),(7,'bronze',2),(7,'leather',2),
 (8,'gold',3),(8,'cloth',1),(8,'bronze',3),(8,'leather',2),
 (9,'gold',5),(9,'cloth',1),(9,'horse',1),(9,'bronze',3),(9,'leather',2),
 (10,'gold',5),(10,'cloth',1),(10,'horse',1),(10,'bronze',2),(10,'leather',2),
 (11,'gold',4),(11,'iron',3),(11,'cloth',2),(11,'leather',1),
 (12,'gold',10),(12,'iron',3),(12,'cloth',2),(12,'horse',1),(12,'leather',1),
 (16,'gold',4),(16,'iron',3),(16,'wood',1),(16,'cloth',2),(16,'leather',1);

DELETE FROM unit_upgrade_requirements;
INSERT INTO unit_upgrade_requirements(unit_id,predecessor_unit_id) VALUES
 (4,2),(5,4),(8,3),(13,12),(14,12),(15,12),(16,8);
