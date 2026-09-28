CREATE TABLE game_wallets (
    user_id integer PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    gold integer NOT NULL DEFAULT 0 CHECK (gold >= 0),
    starting_grant_at timestamptz NOT NULL DEFAULT now()
);
-- Existing baronies receive the same one-time starting grant as new baronies.
INSERT INTO game_wallets(user_id,gold) SELECT DISTINCT user_id,300 FROM player_baronies;

CREATE TABLE game_gold_ledger (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id integer NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    amount integer NOT NULL CHECK (amount <> 0),
    reason text NOT NULL CHECK (reason IN ('starting_grant','hire_general','ransom_paid','ransom_received','raid')),
    related_general_id bigint,
    created_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO game_gold_ledger(user_id,amount,reason)
SELECT user_id,300,'starting_grant' FROM game_wallets;

ALTER TABLE player_generals
    ADD COLUMN status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','wounded','captive','recovering')),
    ADD COLUMN captor_user_id integer REFERENCES users(user_id) ON DELETE SET NULL,
    ADD COLUMN captured_at timestamptz,
    ADD CONSTRAINT general_captive_consistency CHECK
       ((status='captive') = (captor_user_id IS NOT NULL));
CREATE INDEX player_generals_captor_idx ON player_generals(captor_user_id) WHERE status='captive';
