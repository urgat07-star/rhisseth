ALTER TABLE player_general_units
    ADD COLUMN current_health integer,
    ADD COLUMN status text NOT NULL DEFAULT 'ready' CHECK (status IN ('ready','wounded')),
    ADD COLUMN recover_turn bigint;
UPDATE player_general_units pgu SET current_health=uc.health
FROM unit_catalog uc WHERE pgu.unit_id=uc.id;
ALTER TABLE player_general_units ALTER COLUMN current_health SET NOT NULL;
ALTER TABLE player_general_units ADD CONSTRAINT player_unit_health_positive CHECK (current_health>0);
ALTER TABLE player_generals ADD COLUMN last_retreat_turn bigint;

CREATE TABLE game_battles (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    attacker_user_id integer NOT NULL REFERENCES users(user_id),
    general_id bigint NOT NULL REFERENCES player_generals(id),
    target_q integer NOT NULL,
    target_r integer NOT NULL,
    source_q integer NOT NULL,
    source_r integer NOT NULL,
    target_owner_type text NOT NULL,
    target_owner_id text NOT NULL DEFAULT '',
    purpose text NOT NULL CHECK (purpose IN ('capture','raid','encounter')),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','attacker_won','defender_won','retreated')),
    round_number integer NOT NULL DEFAULT 1 CHECK (round_number>=1),
    created_turn bigint NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);
CREATE UNIQUE INDEX one_active_battle_per_general ON game_battles(general_id) WHERE status='active';
CREATE UNIQUE INDEX one_active_battle_per_hex ON game_battles(target_q,target_r) WHERE status='active';

CREATE TABLE game_battle_units (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    battle_id bigint NOT NULL REFERENCES game_battles(id) ON DELETE CASCADE,
    side text NOT NULL CHECK (side IN ('attacker','defender')),
    assignment_id bigint REFERENCES player_general_units(id) ON DELETE SET NULL,
    unit_id integer REFERENCES unit_catalog(id) ON DELETE RESTRICT,
    is_general boolean NOT NULL DEFAULT false,
    name text NOT NULL,
    image_path text NOT NULL,
    x smallint NOT NULL CHECK (x BETWEEN 0 AND 9),
    y smallint NOT NULL CHECK (y BETWEEN 0 AND 9),
    health integer NOT NULL CHECK (health>=0),
    max_health integer NOT NULL CHECK (max_health>0),
    attack integer NOT NULL CHECK (attack>=0),
    defense integer NOT NULL CHECK (defense>=0),
    armor integer NOT NULL CHECK (armor>=0),
    attack_range integer NOT NULL CHECK (attack_range>=1),
    speed integer NOT NULL CHECK (speed>=0),
    initiative integer NOT NULL CHECK (initiative>=0),
    active boolean NOT NULL DEFAULT true,
    moved boolean NOT NULL DEFAULT false,
    attacked boolean NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX one_general_per_battle ON game_battle_units(battle_id,side) WHERE is_general;

CREATE TABLE game_battle_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    battle_id bigint NOT NULL REFERENCES game_battles(id) ON DELETE CASCADE,
    round_number integer NOT NULL,
    event_type text NOT NULL,
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

UPDATE unit_catalog SET combat_level=CASE
    WHEN image_path IN ('units/unit-019.webp','units/unit-001.webp','units/unit-007.webp','units/barbarians-001.webp','units/animal-001.webp') THEN 1
    WHEN image_path IN ('units/unit-002.webp','units/unit-008.webp','units/unit-009.webp','units/unit-010.webp','units/barbarians-002.webp') THEN 2
    WHEN image_path IN ('units/unit-011.webp','units/unit-012.webp','units/unit-020.webp','units/barbarians-003.webp') THEN 3
    WHEN image_path IN ('units/unit-013.webp','units/unit-014.webp','units/unit-018.webp','units/barbarians-004.webp') THEN 4
    ELSE 5 END;
