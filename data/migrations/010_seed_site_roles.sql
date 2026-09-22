INSERT INTO roles (role_id, role_name, role_alias)
VALUES
    (1, 'Администраторы', 'admin'),
    (2, 'Модераторы', 'moderator'),
    (3, 'Пользователи', 'user')
ON CONFLICT (role_id) DO UPDATE
SET role_name = EXCLUDED.role_name,
    role_alias = EXCLUDED.role_alias;
