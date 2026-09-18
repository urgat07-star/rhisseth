CREATE TABLE territories (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(200) NOT NULL,
    kind text NOT NULL CHECK (kind IN ('Баронство','Княжество','Королевство')),
    rules text NOT NULL DEFAULT ''
);
CREATE TABLE player_baronies (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id integer NOT NULL UNIQUE REFERENCES users(user_id),
    name varchar(200) NOT NULL,
    title text NOT NULL DEFAULT 'Барон' CHECK (title='Барон')
);

-- Remove the retired parameter; preserve all other historical metadata.
UPDATE hexes SET data=(data - 'Пресная вода') ||
    jsonb_build_object('Название',COALESCE(data->>'Название',''),
                      'Тип владельца',COALESCE(data->>'Тип владельца','Ничейная территория'),
                      'Владелец',COALESCE(data->>'Владелец',''));

-- Materialize every cell of the existing browser grid; unknown terrain remains unknown.
INSERT INTO hexes(q,r,data)
SELECT q,r,jsonb_build_object('Q',q::text,'R',r::text,'Название','',
    'Тип владельца','Ничейная территория','Владелец','',
    'Статус данных','Требует описания')
FROM generate_series(0,18) AS r
CROSS JOIN LATERAL generate_series(ceil(-0.5-r/2.0)::int,
    floor(3200/(sqrt(3.0)*80)+0.5-r/2.0)::int) AS q
ON CONFLICT(q,r) DO NOTHING;

-- "Outside canvas" is a legacy grid marker, not a terrain category.
UPDATE hexes SET data=data - 'Категория' ||
    jsonb_build_object('Статус данных','Требует описания')
WHERE COALESCE(data->>'Категория','') NOT IN ('Суша','Побережье','Море');

UPDATE hexes SET data=data || jsonb_build_object('Категория',
    CASE WHEN data->>'Остров'='Да' THEN 'Побережье'
         WHEN (data->>'Доля суши, %')::numeric=0 THEN 'Море'
         WHEN (data->>'Доля суши, %')::numeric=100 THEN 'Суша'
         ELSE 'Побережье' END)
WHERE data->>'Доля суши, %' ~ '^[0-9]+([.][0-9]+)?$';
