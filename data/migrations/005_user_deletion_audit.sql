ALTER TABLE user_admin_audit ADD COLUMN target_login varchar(50);
ALTER TABLE user_admin_audit ALTER COLUMN actor_id DROP NOT NULL;
ALTER TABLE user_admin_audit ALTER COLUMN target_id DROP NOT NULL;
ALTER TABLE user_admin_audit DROP CONSTRAINT user_admin_audit_actor_id_fkey;
ALTER TABLE user_admin_audit DROP CONSTRAINT user_admin_audit_target_id_fkey;
ALTER TABLE user_admin_audit ADD CONSTRAINT user_admin_audit_actor_id_fkey
    FOREIGN KEY (actor_id) REFERENCES users(user_id) ON DELETE SET NULL;
ALTER TABLE user_admin_audit ADD CONSTRAINT user_admin_audit_target_id_fkey
    FOREIGN KEY (target_id) REFERENCES users(user_id) ON DELETE SET NULL;
