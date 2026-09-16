# Развёртывание и перенос на VPS

Все приведённые команды выполняются на подготовленном VPS, не на рабочей станции
против внутренних адресов. Для внутренней инфраструктуры обязательны
STU-AUTOMATION-01 (10.210.52.128), закреплённый SSH host key и Markdown-журнал
каждой операции по политике `C:/Avalon-repo/AGENTS.md`.
Здесь удалённые операции не выполнялись. До изменений нужен адрес VPS,
способ доступа, подтверждённый host key и разрешённый маршрут контроллера.

## Первый запуск

Для тестового VPS 1 vCPU / 1 GB использовать оба файла во всех командах:
`docker compose -f compose.yml -f compose.test.yml ...`.
Лимиты: БД 320 MB, приложение 200 MB, proxy 96 MB; остаток требуется ОС и Docker.
Это потолки контейнеров, а не гарантия фактического потребления.
Предложение: swap 1–2 GB после проверки диска; сборку образа проводить вне
малого VPS и доставлять готовый образ. Swap и установка здесь не выполнялись.
Перерисовку/дополнительные workers не включать до измерений.

Проверка 16.09.2026 через runner: VPS `62.113.109.168`, hostname `rhisseth`,
1 CPU, 961 MB RAM, 619 MB available, swap отсутствует; диск 8.7 GB,
свободно 6.1 GB. Nginx активен, Docker/PostgreSQL/Caddy не активны.
Статус inactive не доказывает отсутствие установленного пакета.
Перед применением Compose проверить текущую роль nginx и занятые порты.
Предпочтительно сохранить существующий nginx как HTTPS proxy, либо согласовать
его замену Caddy после проверки конфигурации. Оба proxy одновременно на
одних портах запускать нельзя. Установка, swap и смена proxy не выполнялись.
На малом диске ограничить размер журналов и локальных резервных копий.
Параметры памяти PostgreSQL выбраны для общего сервера, а не выделенной БД:
[Resource Consumption](https://www.postgresql.org/docs/18/runtime-config-resource.html).
Проверять память и OOM после запуска и под тестовой нагрузкой.

Установить Docker Engine и Compose из официального репозитория ОС по
[официальной инструкции](https://docs.docker.com/engine/install/ubuntu/).
Скопировать проверенный проект в `/opt/rhisseth`. Из каталога `deploy`:

1. Скопировать `.env.example` в `.env`, указать DOMAIN и администратора.
2. Создать секрет по `secrets/README.md`.
3. Получить hash интерактивно: `docker run --rm -it caddy:2 caddy hash-password`.
   Поместить hash в `.env` в одинарных кавычках.
4. Выполнить команды ниже. Не выводить `docker compose config` в журналы:
   он может раскрыть конфигурацию и hash. Для проверки использовать `--quiet`.

```bash
docker compose config --quiet
docker compose build app
docker compose up -d db
docker compose run --rm app python migrate.py
docker compose run --rm app python import_csv.py /project/data/import/hex-initial-parameters.csv --check-only
docker compose run --rm app python import_csv.py /project/data/import/hex-initial-parameters.csv
docker compose up -d
```

Открыть `https://rhisseth.ru/`, проверить запрос пароля, карту, PUT через редактор
и `/health` с авторизацией. Перезапустить app и проверить сохранение правок.
Проверить отказ запросов без авторизации, 404 для неизвестного гекса,
400 для неверного рейтинга. Не публиковать API напрямую.
Схема не создаётся автоматически при старте приложения.

## Резервная копия

На VPS из `deploy`, с ограниченными правами на каталог backups:

```bash
mkdir -p ../backups
chmod 700 ../backups
docker compose exec -T db pg_dump -U rhisseth -d rhisseth -Fc -f /tmp/rhisseth.dump
docker compose cp db:/tmp/rhisseth.dump ../backups/rhisseth.dump
docker compose exec -T db rm /tmp/rhisseth.dump
sha256sum ../backups/rhisseth.dump
```

Имя дампа должно содержать время UTC при автоматизации; пример фиксированного
имени предназначен для ручной первой проверки. Настроить scheduler, retention
и зашифрованное внешнее хранение. Копировать также точную версию приложения,
PNG, конфигурацию и отдельно защищённые секреты. Сейчас PNG находится в Git;
когда появятся изменяемые изображения, добавить volume и его резервирование.
[pg_dump/pg_restore](https://www.postgresql.org/docs/current/backup-dump.html)
позволяют логический перенос на другую машину; роли и права требуют отдельного учёта.

## Новый VPS / проверка восстановления

Создать отдельное окружение с пустой базой, теми же major-версией PostgreSQL
и версией приложения. Не импортировать начальный CSV и не выполнять миграции
до восстановления: дамп уже содержит схему и schema_migrations.

```bash
docker compose up -d db
docker compose cp ../backups/rhisseth.dump db:/tmp/rhisseth.dump
docker compose exec -T db pg_restore -U rhisseth -d rhisseth --no-owner --no-acl --exit-on-error --single-transaction /tmp/rhisseth.dump
docker compose exec -T db rm /tmp/rhisseth.dump
docker compose run --rm app python migrate.py
docker compose up -d
```

Сверить число гексов и поля с исходной БД, проверить редактирование и перезапуск.
Не использовать этот пример против непустой production-БД.
Для переключения остановить запись на старом сервере, сделать финальный дамп,
восстановить его на новом и только после проверки переключить DNS.
Не использовать `docker compose down -v`: это удаляет постоянные данные.
