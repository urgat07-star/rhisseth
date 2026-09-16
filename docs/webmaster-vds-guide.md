# Rhisseth.ru: инструкция веб-мастеру по доступу и обслуживанию VDS

Дата: 16.09.2026. Инструкция составлена по исходникам проекта и документированному развёртыванию. Удалённый VDS при подготовке документа не проверялся; фактические настройки нужно сверить командами ниже. Последний описанный перенос сайта — release `17ef94c`.

Отдельный ранбук для замены временного TLS и автоматического продления:
[Let's Encrypt для rhisseth.ru](runbooks/letsencrypt-tls.md). Он также фиксирует
статус задачи. 16.09.2026 сертификат Let's Encrypt установлен через локальный
Docker, доверенный HTTPS проверен из Docker и Windows. Срок и продление — в ранбуке.

## 1. Что работает на сервере и где PHP

VDS: `62.113.109.168`, Ubuntu 24.04. Рабочая схема: браузер → nginx (HTTPS, 443) → FastAPI/Uvicorn (127.0.0.1:8080) → PostgreSQL 16 (localhost:5432). Приложение запускается службой systemd `rhisseth` от системного пользователя `rhisseth`.

**Текущая версия не использует PHP.** Старый сайт был на PHP/MySQL, но при переносе оформление переведено в HTML-шаблоны Jinja2, а логика — в Python. Адреса с `.php` оставлены для совместимости. Файлов `index.php`, `register.php`, `conn.php` в рабочем коде нет; PHP-FPM для этих страниц не требуется. Добавление PHP-файла в каталог проекта само по себе не создаёт рабочую страницу.

| Адрес в браузере | Где менять на VDS | Назначение |
|---|---|---|
| `/` | `app/backend/main.py` | Перенаправление на вход |
| `/index.php` | `app/site/templates/login.html`, `app/backend/site_auth.py` | Оформление и обработка входа |
| `/register.php` | `app/site/templates/register.html`, `app/backend/site_auth.py` | Оформление и обработка регистрации |
| `/logout` | `app/backend/site_auth.py` | Выход, POST с CSRF |
| `/site/css/style.css` | `app/site/static/css/style.css` | Стили входа и регистрации |
| `/site/img/...` | `app/site/static/img/` | Логотип и фоновые изображения |
| `/interactive-map/` | `app/frontend/index.html`, `styles.css`, `app.js` | Интерфейс карты |
| `/api/hexes`, `/api/me`, `/health` | `app/backend/main.py` | Данные карты, текущий пользователь, проверка БД |

Все относительные пути в таблице начинаются от `/opt/rhisseth/repository/`. Старый адрес `/map/interactive-map/index.html` перенаправляется на текущую карту.

## 2. Подключение к файлам

Владелец инфраструктуры должен выдать отдельный SSH-логин, порт, ключ, проверенный отпечаток host key и разрешённые права sudo. SSH-логин и порт в документации проекта не указаны. Логин сайта, GitHub и системный SSH-пользователь — разные учётные записи. Старый `mapadmin` относился к Basic Auth первого теста; после переноса используются аккаунты сайта.

Для операций контроллера доступен runner `STU-AUTOMATION-01` (`10.210.52.128`). По уточнению владельца от 16.09.2026 при его недоступности использовать локальный Docker для доступа к публичному VDS. В обоих случаях нужны закреплённый SSH host key и журналирование. Процедура приведена в [ранбуке TLS](runbooks/letsencrypt-tls.md).

Пример из разрешённой точки доступа, с заменой заполнителей:

```bash
ssh -p SSH_PORT -i PATH_TO_PRIVATE_KEY SSH_USER@62.113.109.168
```

При первом подключении сверить отпечаток с полученным от владельца. Приватный ключ хранить на своей рабочей станции, не загружать в каталог сайта.

Для WinSCP: протокол **SFTP**, хост `62.113.109.168`, выданные порт и SSH-логин, приватный ключ, удалённый каталог `/opt/rhisseth/repository`. Для VS Code Remote SSH — тот же SSH-профиль, затем Open Folder → `/opt/rhisseth/repository`.

Checkout по документации принадлежит root, поэтому подключение по SFTP не гарантирует право записи. Предпочтительный рабочий процесс: правка локальной копии → коммит и проверка → публикация в GitHub → обновление VDS. Для срочных ручных изменений использовать выданное право `sudoedit`. Не менять владельца всего `/opt/rhisseth` и не выдавать `chmod 777`: там находятся секреты и резервные копии.

## 3. Структура непосредственно на VDS

| Полный путь | Назначение |
|---|---|
| `/opt/rhisseth/repository/` | Рабочая Git-копия приложения |
| `/opt/rhisseth/repository/app/backend/main.py` | Маршруты, API, контроль доступа к карте, проверка полей гексов, раздача статики |
| `/opt/rhisseth/repository/app/backend/site_auth.py` | Вход, регистрация, bcrypt, сессии, CSRF |
| `/opt/rhisseth/repository/app/backend/db.py` | Подключение к PostgreSQL, чтение пароля из файла |
| `/opt/rhisseth/repository/app/backend/migrate.py` | Применение ещё не выполненных SQL-миграций |
| `/opt/rhisseth/repository/app/backend/import_csv.py` | Первичный импорт карты; не способ обновления действующих данных |
| `/opt/rhisseth/repository/app/backend/import_users.py` | Одноразовый перенос пользователей старого сайта |
| `/opt/rhisseth/repository/app/backend/requirements.lock` | Зафиксированные Python-зависимости |
| `/opt/rhisseth/repository/app/site/templates/` | `login.html`, `register.html`; сохранять Jinja2-переменные и скрытые CSRF-поля |
| `/opt/rhisseth/repository/app/site/static/` | CSS, логотип `img/logo.webp`, фоны входа и регистрации |
| `/opt/rhisseth/repository/app/frontend/` | `index.html`, `styles.css`, `app.js` и PNG-карты |
| `/opt/rhisseth/repository/data/migrations/001_hexes.sql` | Схема хранения гексов |
| `/opt/rhisseth/repository/data/migrations/002_site_accounts.sql` | Роли, пользователи и сессии |
| `/opt/rhisseth/repository/data/import/hex-initial-parameters.csv` | Исторический источник первичного импорта, не действующая БД |
| `/opt/rhisseth/repository/deploy/native/` | Шаблоны nginx, systemd, PostgreSQL и ротации журналов |
| `/opt/rhisseth/repository/deploy/compose.yml` | Альтернативный Docker-вариант; не используется одновременно с нативным |
| `/opt/rhisseth/repository/docs/`, `tests/`, `scripts/automation/` | Документация, проверки, автоматизация deployment |
| `/opt/rhisseth/repository/archive/strat-tools/` | Старые генераторы для справки |
| `/opt/rhisseth/venv/` | Python-окружение; не редактировать библиотеки вместо исходников |
| `/opt/rhisseth/secrets/app.env` | Окружение службы, ссылки на секреты |
| `/opt/rhisseth/secrets/db-password.txt` | Пароль роли БД; не публиковать |
| `/opt/rhisseth/secrets/tls.crt`, `tls.key` | Временный сертификат и закрытый ключ |
| `/opt/rhisseth/secrets/web-password.txt`, `web.htpasswd` | Возможные остатки прежней Basic Auth, не аккаунты текущего сайта |
| `/opt/rhisseth/backups/` | Дампы БД и копии конфигурации |
| `/opt/rhisseth/reports/` | Журналы операций, `nginx-access.log`, `nginx-error.log` |
| `/opt/rhisseth/release.json` | Запись версии развёртывания; сверять с фактическим Git SHA |
| `/opt/rhisseth/temp/` | Приватные исходные архивы старого хостинга; не web-root |
| `/etc/nginx/sites-available/rhisseth` | Действующая конфигурация nginx сайта |
| `/etc/nginx/sites-enabled/rhisseth` | Ссылка, включающая virtual host |
| `/etc/systemd/system/rhisseth.service` | Действующий unit приложения |
| `/etc/logrotate.d/rhisseth` | Ротация nginx-журналов проекта |
| `/var/lib/postgresql/16/main/` | Физические файлы БД; обслуживаются PostgreSQL, вручную не редактируются |

В nginx нет обычного PHP web-root: запросы проксируются приложению, а оно раздаёт разрешённые каталоги. `secrets`, `backups`, `.git` и архивы не должны становиться общедоступными.

## 4. Сверка состояния перед работой

Следующие команды выполняются **на VDS**, после входа через разрешённый маршрут:

```bash
sudo git -C /opt/rhisseth/repository status --short
sudo git -C /opt/rhisseth/repository rev-parse HEAD
sudo systemctl status rhisseth nginx postgresql@16-main --no-pager
sudo ss -ltnp
sudo nginx -t
sudo ls -l /etc/nginx/sites-enabled/rhisseth
sudo journalctl -u rhisseth -n 50 --no-pager
```

Ожидается: nginx на 80/443, приложение только на 127.0.0.1:8080, PostgreSQL на loopback:5432. Проверка `/health` без сессии возвращает 401 — это предусмотренная защита. Успешная проверка после входа возвращает `{"status":"ok"}`.

## 5. Резервирование и обновление из Git

До изменений проверить локальные правки и сделать дамп. Пример в Bash на VDS; каталог backups должен уже существовать с ограниченным доступом:

```bash
set -o pipefail
backup_stamp=$(date -u +%Y%m%dT%H%M%SZ)
sudo install -m 600 /dev/null "/opt/rhisseth/backups/rhisseth-${backup_stamp}.dump"
sudo -u postgres pg_dump -Fc -d rhisseth | sudo tee "/opt/rhisseth/backups/rhisseth-${backup_stamp}.dump" > /dev/null
sudo cat "/opt/rhisseth/backups/rhisseth-${backup_stamp}.dump" | sudo -u postgres pg_restore --list > /dev/null
```

После каждой команды проверить код завершения (`echo $?` должен показать `0`); при ошибке обновление не продолжать. Проверка оглавления не заменяет пробное восстановление в отдельную БД. Записать предыдущий SHA в журнал операции. Перед правками nginx сохранить его текущий файл в backups.

Обновление для проверенного выпуска в `main`:

```bash
sudo git -C /opt/rhisseth/repository fetch origin main
sudo git -C /opt/rhisseth/repository log --oneline HEAD..origin/main
sudo git -C /opt/rhisseth/repository merge --ff-only origin/main
```

При локальных правках сначала разобрать их и сохранить; не применять `reset --hard` или force push. Если изменились зависимости:

```bash
sudo /opt/rhisseth/venv/bin/pip install --no-cache-dir -r /opt/rhisseth/repository/app/backend/requirements.lock
```

Если выпуск содержит новые миграции, предварительно проверить их на восстановленной тестовой БД. Затем применить на VDS:

```bash
sudo env DB_HOST=127.0.0.1 DB_NAME=rhisseth DB_USER=rhisseth DB_PASSWORD_FILE=/opt/rhisseth/secrets/db-password.txt /opt/rhisseth/venv/bin/python /opt/rhisseth/repository/app/backend/migrate.py
```

Сам пароль в команду не вставлять. Миграции не запускаются автоматически при старте. После обновления backend или шаблонов:

```bash
sudo systemctl restart rhisseth
sudo systemctl status rhisseth --no-pager
```

Изменение только CSS/JS/PNG обычно видно после обновления страницы с очисткой браузерного кэша. При изменении unit выполнить `sudo systemctl daemon-reload` и restart. При изменении nginx выполнить `sudo nginx -t` и только при успехе `sudo systemctl reload nginx`. Шаблон в Git и действующий файл в `/etc` — разные файлы: изменение одного не обновляет другой автоматически.

## 6. Срочная ручная правка

Например, изменить текст страницы входа:

```bash
sudoedit /opt/rhisseth/repository/app/site/templates/login.html
sudo systemctl restart rhisseth
sudo git -C /opt/rhisseth/repository diff -- app/site/templates/login.html
```

Сохранить UTF-8, структуру формы, её action, имена полей и CSRF. Проверить страницу и вход; перенести правку в Git, чтобы очередное обновление её учитывало. Для CSS аналогично редактировать `app/site/static/css/style.css`, для карты — файлы `app/frontend/`. Какой PNG используется сейчас, проверить по ссылкам в `app.js`/`index.html`, а не по номеру версии в имени.

## 7. Ручная настройка домена, HTTPS и окружения

По имеющейся документации DNS и публичный TLS ещё не завершены. Перед настройкой проверить их фактическое состояние.

1. В DNS-панели домена направить A-запись `rhisseth.ru` на `62.113.109.168`. `www` добавлять только если нужен; тогда также включить его в nginx и сертификат. AAAA добавлять только для реально настроенного IPv6 VDS.
2. Проверить разрешение имени и доступность 80/443. Не публиковать 8080 и 5432 в интернет.
3. В `/etc/nginx/sites-available/rhisseth` сверить `server_name`, проксирование на `127.0.0.1:8080`, заголовки `Host`, `X-Forwarded-Proto`, `X-Forwarded-For` и ограничение POST к формам. Не заменять проксирование правилом PHP-FPM.
4. Получить сертификат публичного CA выбранным инфраструктурным способом, указать его реальные пути в `ssl_certificate` и `ssl_certificate_key`. Текущие `tls.crt`/`tls.key` — временный self-signed сертификат, документированный срок 30 дней.
5. Проверить `nginx -t`, перезагрузить nginx, проверить HTTPS в браузере без предупреждения, настроить и проверить автоматическое продление сертификата. Точную команду выдачи выбирать после проверки установленного ACME-клиента и способа подтверждения домена.

Окружение приложения находится в `/opt/rhisseth/secrets/app.env`. Используемые параметры: `DB_HOST=127.0.0.1`, `DB_PASSWORD_FILE=/opt/rhisseth/secrets/db-password.txt`; `DB_NAME` и `DB_USER` по умолчанию `rhisseth`, `DB_PORT` — `5432`. Для изменения использовать `sudoedit`, затем restart службы. Не выводить секретный файл в терминал или журнал целиком. При изменении расположения пароля проверить право чтения у пользователя службы `rhisseth`.

Если действительно потребуется новая функциональность именно на PHP, это отдельное изменение архитектуры: потребуются PHP runtime, отдельная схема маршрутизации nginx, доступ к PostgreSQL и решение совместимости авторизации. Старый `conn.php` с MySQL и Apache `.htaccess` для текущего приложения не подходят. В приватном архиве `/opt/rhisseth/temp/` могут оставаться исходные PHP-файлы, но они не обслуживают текущий сайт; их точные имена и состав нужно проверять отдельно без публикации секретов.

## 8. Данные, права и проверка результата

Рабочие гексы, пользователи и сессии хранятся в PostgreSQL. Правка CSV не изменит карту. Регистрация создаёт роль `user`; `admin` и `moderator` могут редактировать, `user` — просматривать. Штатная панель назначения ролей в этой инструкции не предусмотрена: изменение ролей проводить отдельной контролируемой операцией в БД с проверкой пользователя.

После обновления проверить:

- Вход, регистрацию и выход на HTTPS; оформление и изображения.
- Открытие карты после входа; без входа — перенаправление на страницу входа.
- Чтение карты пользователем `user`, запрет редактирования для него.
- Сохранение разрешённой правки `admin`/`moderator`, её наличие после restart; тестовую правку вернуть.
- Отсутствие новых ошибок в journalctl и nginx error log.

| Симптом | Что проверить |
|---|---|
| 502 от nginx | Статус `rhisseth`, журнал службы, порт 8080 |
| 503 от приложения | PostgreSQL, путь/права файла пароля, применённые миграции |
| 401 на API или `/health` | Вход и сессионный cookie |
| 403 при сохранении | Роль, CSRF-токен, актуальность сессии |
| 429 на форме | Ограничение частоты запросов nginx |
| Вход не сохраняется по HTTP | Cookie имеет Secure; использовать рабочий HTTPS |
| Браузер предупреждает о сертификате | Остался временный TLS, срок или имя сертификата |
| CSS/JS не изменились | Правильный каталог, браузерный кэш, Git SHA на VDS |

Откат кода выполнять к заранее записанному проверенному SHA после сохранения текущих правок и свежего дампа. Проверить совместимость старого кода с текущей схемой БД. Восстановление дампа — отдельная операция, способная потерять более новые записи; не заменять ей обычный откат оформления. Физический каталог PostgreSQL не копировать как замену логическому дампу.

## 9. Что передать веб-мастеру

Передать через защищённый канал: SSH-профиль и отпечаток сервера, ключ/порядок его регистрации, разрешённый маршрут и права sudo, доступ к GitHub, DNS-панели и учётной записи сайта с нужной ролью. Указать ответственного за резервирование и сертификаты. Пароли, приватные ключи, дампы пользователей и архив старого хостинга в эту инструкцию и Git не добавлять.

Источники внутри проекта: [описание нативного deployment](../deploy/native/README.md), [перенос хостинга](hosting-migration.md), [общий deployment](../deploy/README.md). Документ хранится в `rhisseth.ru/docs/` согласно правилу хранения материалов проекта в README.
