-- Annual population, food and tax audit for the rules approved 2026-10-19.
ALTER TABLE game_gold_ledger DROP CONSTRAINT game_gold_ledger_reason_check;
ALTER TABLE game_gold_ledger ADD CONSTRAINT game_gold_ledger_reason_check
 CHECK (reason IN ('starting_grant','hire_general','hire_unit','ransom_paid','ransom_received',
                   'raid','test_reset','encounter','annual_tax'));

CREATE TABLE hex_economy_state (
    q integer NOT NULL,
    r integer NOT NULL,
    double_capacity_years smallint NOT NULL DEFAULT 0 CHECK (double_capacity_years BETWEEN 0 AND 5),
    PRIMARY KEY (q,r),
    FOREIGN KEY (q,r) REFERENCES hexes(q,r) ON DELETE CASCADE
);

CREATE TABLE hex_population_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    year integer NOT NULL CHECK (year >= 0),
    turn_number integer NOT NULL CHECK (turn_number >= 0),
    q integer NOT NULL,
    r integer NOT NULL,
    user_id integer REFERENCES users(user_id) ON DELETE SET NULL,
    amount integer NOT NULL CHECK (amount <> 0),
    reason text NOT NULL CHECK (reason IN ('reserve_transfer')),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX hex_population_events_year_user_idx ON hex_population_events(user_id,year);

CREATE TABLE hex_economy_history (
    year integer NOT NULL CHECK (year >= 0),
    q integer NOT NULL,
    r integer NOT NULL,
    owner_type text NOT NULL,
    owner_id text NOT NULL DEFAULT '',
    barony_id integer,
    population_before integer NOT NULL CHECK (population_before >= 0),
    food_delta integer NOT NULL,
    federal_food_used integer NOT NULL DEFAULT 0 CHECK (federal_food_used >= 0),
    famine_loss integer NOT NULL DEFAULT 0 CHECK (famine_loss >= 0),
    natural_growth integer NOT NULL DEFAULT 0 CHECK (natural_growth >= 0),
    manual_change integer NOT NULL DEFAULT 0,
    population_after integer NOT NULL CHECK (population_after >= 0),
    tax integer NOT NULL DEFAULT 0 CHECK (tax >= 0),
    level_before smallint NOT NULL CHECK (level_before BETWEEN 1 AND 8),
    level_after smallint NOT NULL CHECK (level_after BETWEEN 1 AND 8),
    auto_level_up boolean NOT NULL DEFAULT false,
    processed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (year,q,r)
);
CREATE INDEX hex_economy_history_barony_year_idx ON hex_economy_history(barony_id,year,q,r);
CREATE INDEX hex_economy_history_owner_year_idx ON hex_economy_history(owner_id,year,q,r)
 WHERE owner_type='Игрок';

-- Population/tax processing is intentionally independent from the older
-- resource marker, which may already contain years reached by admin clock jumps.
CREATE TABLE game_population_years (
    year integer PRIMARY KEY CHECK (year >= 0),
    processed_at timestamptz NOT NULL DEFAULT now()
);

UPDATE hexes SET data=data || jsonb_build_object('Население','0'),updated_at=now()
WHERE data->>'Категория'='Море' AND COALESCE(data->>'Остров','Нет')<>'Да';
