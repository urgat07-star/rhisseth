UPDATE roles SET role_name=CASE role_alias WHEN 'admin' THEN 'Администраторы' WHEN 'moderator' THEN 'Модераторы' WHEN 'user' THEN 'Пользователи' END WHERE role_alias IN ('admin','moderator','user');
CREATE TABLE user_admin_audit (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 happened_at timestamptz NOT NULL DEFAULT now(),
 actor_id integer NOT NULL REFERENCES users(user_id),
 target_id integer NOT NULL REFERENCES users(user_id),
 changed_fields jsonb NOT NULL,
 old_role text NOT NULL,
 new_role text NOT NULL
);
