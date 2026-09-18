ALTER TABLE player_baronies
    ADD COLUMN territory_name varchar(200) NOT NULL DEFAULT '',
    ADD COLUMN crest varchar(40) NOT NULL DEFAULT 'gerb_1.png',
    ADD COLUMN color varchar(7) NOT NULL DEFAULT '#b51f24' CHECK (color ~ '^#[0-9a-fA-F]{6}$'),
    ADD COLUMN agreement_at timestamptz;
UPDATE player_baronies SET territory_name=name;
UPDATE hexes h SET data=h.data || jsonb_build_object(
    'Название баронии',b.name,'Герб баронии',b.crest,'Цвет баронии',b.color)
FROM player_baronies b
WHERE h.data->>'ID территории'=b.id::text
  AND h.data->>'Владелец'=b.user_id::text
  AND h.data->>'Тип владельца'='Игрок';
