ALTER TABLE general_catalog
    DROP CONSTRAINT IF EXISTS general_catalog_image_path_check;

ALTER TABLE general_catalog
    ADD COLUMN IF NOT EXISTS crest text,
    ADD COLUMN IF NOT EXISTS pose text;

ALTER TABLE general_catalog
    ADD CONSTRAINT general_catalog_image_path_check
    CHECK (image_path ~ '^general/[a-zA-Z0-9_-]+\.(webp|png|svg)$'),
    ADD CONSTRAINT general_catalog_crest_check
    CHECK (crest IS NULL OR crest ~ '^gerb_[0-9]+\.webp$'),
    ADD CONSTRAINT general_catalog_pose_check
    CHECK (pose IS NULL OR pose IN ('foot','mounted'));

-- Миграция 011 разрешала только два старых WEBP-файла. Ограничение необходимо
-- расширить до замены icon у уже нанятых генералов, иначе UPDATE ниже отклоняется.
ALTER TABLE player_generals
    DROP CONSTRAINT IF EXISTS player_generals_icon_check;

ALTER TABLE player_generals
    ADD CONSTRAINT player_generals_icon_check
    CHECK (icon ~ '^general/[a-zA-Z0-9_-]+\.(webp|png|svg)$');

UPDATE general_catalog SET active=false WHERE crest IS NULL;
UPDATE general_catalog SET image_path=CASE id
    WHEN 1 THEN 'general/gen-01-transparent.png'
    WHEN 2 THEN 'general/gen-02-transparent.png'
    WHEN 3 THEN 'general/gen-03-transparent.png'
    ELSE image_path END
WHERE id IN (1,2,3);

WITH crests(number,filename) AS (VALUES
    (1,'gerb_1.webp'),(2,'gerb_2.webp'),(3,'gerb_3.webp'),(4,'gerb_4.webp'),
    (5,'gerb_5.webp'),(6,'gerb_6.webp'),(8,'gerb_8.webp'),(9,'gerb_9.webp'),
    (10,'gerb_10.webp'),(11,'gerb_11.webp'),(12,'gerb_12.webp'),(13,'gerb_13.webp'),
    (14,'gerb_14.webp'),(15,'gerb_15.webp'),(16,'gerb_16.webp'),(17,'gerb_17.webp'),
    (19,'gerb_19.webp'),(20,'gerb_20.webp')
), poses(code,label) AS (VALUES ('foot','Пеший'),('mounted','Конный'))
INSERT INTO general_catalog(name,description,image_path,health,attack,defense,initiative,speed,
    logistics,skills,experience_per_level,max_level,max_attack_bonus,max_defense_bonus,active,crest,pose)
SELECT 'Генерал герба '||number||' · '||label,
       label||' генерал, доступный только баронии с гербом '||number,
       'general/general-gerb-'||lpad(number::text,2,'0')||'-'||code||'.svg',
       10,1,1,1,1,10,'',100,10,9,9,true,filename,code
FROM crests CROSS JOIN poses
ON CONFLICT (name) DO UPDATE SET
    description=EXCLUDED.description,image_path=EXCLUDED.image_path,active=true,
    crest=EXCLUDED.crest,pose=EXCLUDED.pose,updated_at=now();

-- Переводим уже нанятых генералов на герб их текущей баронии. Старый третий
-- шаблон был конным; первый, второй и неизвестные варианты считаются пешими.
WITH direct_crests AS (
    SELECT user_id,replace(crest,'.png','.webp') AS crest
    FROM player_baronies WHERE crest IS NOT NULL AND crest<>''
), legacy_crests AS (
    SELECT DISTINCT ON ((data->>'Владелец')::integer)
        (data->>'Владелец')::integer AS user_id,
        replace(data->>'Герб баронии','.png','.webp') AS crest
    FROM hexes
    WHERE data->>'Тип владельца'='Игрок'
      AND data->>'Владелец'~'^[0-9]+$'
      AND coalesce(data->>'Герб баронии','')<>''
    ORDER BY (data->>'Владелец')::integer,r,q
), barony_crests AS (
    SELECT user_id,crest FROM direct_crests
    UNION ALL
    SELECT legacy.user_id,legacy.crest FROM legacy_crests legacy
    WHERE NOT EXISTS (SELECT 1 FROM direct_crests direct WHERE direct.user_id=legacy.user_id)
), replacements AS (
    SELECT pg.id AS player_general_id,target.id AS catalog_id,target.image_path
    FROM player_generals pg
    JOIN barony_crests barony ON barony.user_id=pg.user_id
    LEFT JOIN general_catalog previous ON previous.id=pg.catalog_id
    JOIN general_catalog target
      ON target.crest=barony.crest
     AND target.pose=CASE
        WHEN previous.pose='mounted' OR pg.icon LIKE '%gen-03%' OR pg.icon LIKE '%-mounted.svg'
        THEN 'mounted' ELSE 'foot' END
     AND target.active
)
UPDATE player_generals pg
SET catalog_id=replacements.catalog_id,icon=replacements.image_path
FROM replacements
WHERE pg.id=replacements.player_general_id;
