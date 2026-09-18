ALTER TABLE player_barony_audit DROP CONSTRAINT player_barony_audit_action_check;
ALTER TABLE player_barony_audit ADD CONSTRAINT player_barony_audit_action_check CHECK (action IN ('crest','abandon','rename'));
