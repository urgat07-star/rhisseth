# Первый тестовый деплой: nginx + PostgreSQL + systemd

После переноса хостинга вход и регистрация из архива становятся главными
страницами сайта; старая Basic Auth заменяется PostgreSQL-аккаунтами.
Для текущей версии см. [перенос сайта и пользователей](../../docs/hosting-migration.md).
Разделы о mapadmin ниже описывают историческую первую тестовую конфигурацию,
а не дополнительный пароль для перенесённого сайта.

Этот вариант предназначен для VPS Ubuntu 24.04 с 1 vCPU / 1 GB RAM.
Использует PostgreSQL 16 из Ubuntu, один процесс Uvicorn и существующий nginx.
Compose с PostgreSQL 18 остаётся отдельным вариантом и здесь не запускается.
[Установка PostgreSQL в Ubuntu](https://ubuntu.com/server/docs/how-to/databases/install-postgresql/).

| Путь на VPS | Назначение |
|---|---|
| `/opt/rhisseth/repository` | Clone GitHub, программный код и deployment templates |
| `/opt/rhisseth/venv` | Python environment с requirements.lock |
| `/opt/rhisseth/secrets` | Пароли и временный TLS; не в Git и не в web-root |
| `/opt/rhisseth/backups` | Дампы и копия конфигурации nginx |
| `/opt/rhisseth/reports` | Санитизированные журналы и nginx logs |
| `/opt/rhisseth/release.json` | SHA развёрнутого коммита и версия БД |

PostgreSQL хранит физические данные в стандартном системном каталоге
`/var/lib/postgresql/16/main`; база `rhisseth` принадлежит роли `rhisseth`,
не имеющей superuser/createdb/createrole. Это системное хранилище службы,
а переносимые проектные дампы размещаются внутри `/opt/rhisseth/backups`.
API слушает только 127.0.0.1:8080, PostgreSQL — localhost:5432.

Первое развёртывание выполняет проверенный скрипт `scripts/automation/Deploy-RhissethVps.py`:
clone/fetch непосредственно на VPS, установка пакетов, создание отдельной базы,
миграции, одноразовый импорт, systemd и отдельный virtual host nginx.
Повторный запуск не импортирует CSV поверх существующих данных.
Перед изменением nginx сохраняется исходная конфигурация; reload выполняется
после `nginx -t`. Существующий default virtual host сохраняется.
Скрипт предназначен для данного тестового VPS, а не для произвольного production.

Доступ для первого теста: `https://62.113.109.168/`, логин `mapadmin`.
Пароль генерируется на VPS и хранится только в root-only
`/opt/rhisseth/secrets/web-password.txt`; получайте его через защищённый
SSH/менеджер секретов, не помещайте в команды и журналы.
Сертификат временный, self-signed, действует 30 дней: обычный браузер не доверяет
ему автоматически. Проверки используют конкретный сертификат, полученный
через закреплённый SSH, без отключения TLS verification.
После настройки DNS на VPS заменить его сертификатом публичного CA.
Готовая процедура и скрипт: [ранбук Let's Encrypt](../../docs/runbooks/letsencrypt-tls.md).
После выпуска сохранять ACME-настройки действующего nginx virtual host;
исторический `nginx.conf` ниже использует временный self-signed TLS.

## Передача команде сайта

Первый выпуск успешно проверен 16.09.2026, Git SHA `31b698e`.
Полное сравнение 667 строк, сохранение после рестартов, восстановление дампа
и внешний nginx/TLS с runner прошли. Свободно ~535 MB RAM и 5.8 GB диска;
длительная нагрузка не проверялась. Отчёты находятся в локальном `reports/`.
Git checkout принадлежит root: до выделения отдельного deploy-пользователя
приведённые команды Git выполнять с разрешённым sudo, например
`sudo git -C /opt/rhisseth/repository fetch origin main`.

Команда получает права на GitHub и отдельный SSH-пользователь/ключ через
владельца инфраструктуры. Данные root из Passbolt не копировать в Git.
Публичный репозиторий сейчас читается по HTTPS без GitHub credentials;
для private repo нужен read-only deploy key или иной отдельный доступ.
[GitHub cloning](https://docs.github.com/en/repositories/creating-and-managing-repositories/cloning-a-repository).

Контроллер выполняет операции через доступный runner с журналированием;
по указанию владельца при его недоступности использовать локальный Docker
для доступа к публичному VDS (см. ранбук TLS).
Ниже команды на VPS после предоставления команде утверждённого доступа:

```bash
cd /opt/rhisseth/repository
git status --short
git fetch origin main
git log --oneline HEAD..origin/main
```

Перед обновлением сохранить дамп, SHA версии и проверить рабочее дерево.
Для принятого выпуска:

```bash
git merge --ff-only origin/main
/opt/rhisseth/venv/bin/pip install --no-cache-dir -r app/backend/requirements.lock
sudo systemctl restart rhisseth
sudo nginx -t
sudo systemctl status rhisseth nginx postgresql@16-main --no-pager
```

При новых SQL migrations сначала отдельно выполнить `migrate.py` с
`DB_HOST=127.0.0.1` и `DB_PASSWORD_FILE=/opt/rhisseth/secrets/db-password.txt`
в окружении разрешённого процесса. Не передавать сам пароль аргументом.
Скрипт не должен читать/печатать полный секретный env-файл в журнал.
Обновления схемы проверять на восстановленной тестовой копии до применения.
Изменения frontend/backend отслеживаются в Git; секреты и данные не затрагиваются
pull. Не использовать force/reset --hard на VPS с неизвестными локальными правками.

При откате приложения выбирать прежний проверенный SHA после резервирования.
Откат SQL-схемы отдельный: старый код должен быть совместим с текущей схемой,
иначе требуется восстановление с согласованной потерей более поздних записей.

Проверки первого выпуска: все CSV-поля совпадают с API, nginx/HTTPS/Basic Auth,
статика и PNG, отказ невалидных записей, сохранение после перезапуска приложения
и БД, восстановление дампа в изолированную БД с совпадением checksum.
Временное тестовое изменение возвращается к исходному значению.
Это проверка компонентов, не нагрузочный тест и не проверка полного reboot VPS.
