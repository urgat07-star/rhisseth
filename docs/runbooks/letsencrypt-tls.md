# rhisseth.ru: выпуск и продление сертификата Let's Encrypt

Задача от 16.09.2026: убрать предупреждение о сертификате при открытии
`https://rhisseth.ru/`, заменить временный self-signed TLS публичным
сертификатом и обеспечить автоматическое продление.

**Статус: выполнено 16.09.2026 через локальный Docker.**
Из Docker и Windows страница входа возвращает 200 с обычной проверкой CA.
Issuer: Let's Encrypt YE2; SAN: `rhisseth.ru`; срок до
15.12.2026 18:05:25 UTC. `rhisseth-certbot.timer` активен.
Пробное продление `--dry-run --run-deploy-hooks` успешно, установочный
контроллер завершился с кодом 0. Первый запуск timer:
17.09.2026 00:54:09 UTC (03:54:09 МСК).
Резервная копия исходного nginx:
`/opt/rhisseth/backups/nginx-before-letsencrypt-20260916T190327Z.conf`.
Локальные доказательства: `reports/automation-logs/2026-09-16/` —
`20260916-190253-tls-local-docker.md` и `20260916-190559-public-tls.json`.

Первоначально на рабочей станции A-запись
разрешилась в `62.113.109.168`, AAAA-запись не обнаружена. Это локальная
проверка DNS, а не подтверждение выдачи сертификата. В текущем workspace
отсутствуют `containers/compose/ansible-control/.env` и
`temp/stu-automation-01-known_hosts`, используемые существующим контроллером.
Контактный email ACME: `urgat07@gmail.com` (предоставлен владельцем).
По уточнению владельца runner — один из маршрутов; при его недоступности
использовать локальный Docker. Docker Desktop запущен, из образа
`ops-nettools:latest` SSH-порт VDS доступен; до установки curl подтвердил self-signed TLS.
Владелец предоставил `C:\Users\user\.ssh\known_hosts` и защищённый файл
`C:\Users\user\.ssh\.pass\62.113.109.168`. В файле — `root` и пароль
на отдельных строках; контроллер поддерживает этот формат и файл только
с паролем. Запись host key найдена, SSH прошёл с StrictHostKeyChecking=yes.

## Хранение и маршрут доступа

Локально все материалы находятся в `rhisseth.ru/`: этот ранбук в
`docs/runbooks/`, скрипт и units в `deploy/native/`, журналы в
`reports/automation-logs/YYYY-MM-DD/`. На runner использовать
`/home/avalon/rhisseth.ru/`. На VDS — существующий проект `/opt/rhisseth/`.
Секреты, ключи ACME, сертификаты с приватными ключами и журналы в Git не добавлять.
Системные units и nginx virtual host устанавливаются в стандартные `/etc/`
из исходников проекта.

Контроллер работает через доступный runner или локальный Docker
с закреплёнными host keys и журналированием.
VDS: `62.113.109.168:22`; существующий ресурс Passbolt для SSH:
`da44a388-e458-4379-ab4c-c204696804b2`. Пароль получать только внутри
защищённого процесса контроллера, не вставлять в команды и отчёты.
Не отключать проверку SSH/TLS. Локальный Docker разрешён владельцем
как резервный маршрут к этому публичному VDS.

## Предварительные проверки

1. Проверить A и AAAA через публичные резолверы и авторитетные DNS.
   A должна вести на VDS; если появится AAAA, IPv6 также должен обслуживать сайт.
   Проверить CAA, если записи существуют: они должны разрешать Let's Encrypt.
2. Проверить доступность порта 80 из внешней сети и отсутствие фильтрации
   `/.well-known/acme-challenge/`. HTTP-01 использует порт 80.
3. Через утверждённый SSH проверить `sudo nginx -t`, активность nginx,
   `/etc/nginx/sites-enabled/rhisseth` и конфигурацию
   `/etc/nginx/sites-available/rhisseth`. Сверить, что это именно сайт Rhisseth.
4. Проверить отсутствие другой операции Certbot, существующие сертификаты,
   место на диске и корректное время. Согласованный контактный email передать
   скрипту; команда выпуска принимает условия Let's Encrypt от имени владельца.
5. Доставить три файла из `deploy/native/` в соответствующий каталог
   `/opt/rhisseth/repository/deploy/native/` через runner. Обновление всего
   приложения и импорт БД для этой операции не требуются.

## Выпуск и установка

На VDS через runner или локальный Docker:

```bash
sudo bash /opt/rhisseth/repository/deploy/native/install-letsencrypt.sh urgat07@gmail.com
```

Скрипт сохраняет текущий virtual host в
`/opt/rhisseth/backups/nginx-before-letsencrypt-UTC.conf`, устанавливает Ubuntu
пакеты `certbot` и `python3-certbot-nginx`, выпускает сертификат только для
`rhisseth.ru` и устанавливает его nginx-плагином с HTTPS redirect.
Дополнительные имена, включая `www`, добавлять только после проверки их DNS.
Сертификат для домена не удостоверяет адрес `https://62.113.109.168/`:
пользователи должны открывать `https://rhisseth.ru/`.

ACME state и ключи: `/opt/rhisseth/secrets/letsencrypt/`;
рабочие файлы: `/opt/rhisseth/.local/certbot/`;
логи: `/opt/rhisseth/reports/certbot/`.
В nginx устанавливаются `live/rhisseth.ru/fullchain.pem` и `privkey.pem`
из указанного каталога state. Не копировать их в web-root.

При отказе команды выдачи скрипт восстанавливает исходный virtual host.
При ошибке последующих проверок сертификат может уже быть установлен:
изучить журнал и проверить состояние, прежде чем запускать повторно.
Пакеты и ACME state при отказе сохраняются. Не применять `--force-renewal`
при повторных попытках; учитывать ограничения частоты выпуска CA.

## Продление и приёмка

Отдельный `rhisseth-certbot.timer` запускает проверку дважды в сутки
с задержкой до часа и догоняет пропущенный запуск. Deploy hook проверяет
nginx и делает reload после успешного продления. Стандартный timer Certbot
обслуживает `/etc/letsencrypt`; для нашего каталога используется отдельный unit.

```bash
sudo systemctl status rhisseth-certbot.timer --no-pager
sudo systemctl list-timers rhisseth-certbot.timer --no-pager
sudo certbot renew --config-dir /opt/rhisseth/secrets/letsencrypt --work-dir /opt/rhisseth/.local/certbot --logs-dir /opt/rhisseth/reports/certbot --cert-name rhisseth.ru --dry-run --run-deploy-hooks --no-random-sleep-on-renew
curl --fail --show-error --silent --output /dev/null --write-out '%{http_code}\n' https://rhisseth.ru/index.php
curl --show-error --silent --head http://rhisseth.ru/
sudo journalctl -u rhisseth-certbot.service --no-pager -n 30
```

Обязательная внешняя проверка с runner или локального Docker: доверенная цепочка и имя домена
без `-k` и без подмены CA, страница входа возвращает 200, HTTP перенаправляется
на HTTPS, карта без сессии перенаправляет на вход. Проверка аккаунта и карты
после входа выполняется веб-мастером при передаче; для TLS аккаунты не меняются.
Зафиксировать UTC, issuer, SAN, срок действия, результат dry-run и timer
в проектном журнале. Проверять ошибки timer и срок сертификата регулярно.
Задача закрывается только после успешных внешних проверок и dry-run.

## Откат и последующие deployment

Если новый virtual host нарушил работу, восстановить конкретную копию,
указанную скриптом; заменить `UTC` фактическим timestamp:

```bash
sudo cp -p /opt/rhisseth/backups/nginx-before-letsencrypt-UTC.conf /etc/nginx/sites-available/rhisseth
sudo nginx -t && sudo systemctl reload nginx
```

Такой откат возвращает прежний сертификат и его предупреждение. Сертификаты
и ключи не удалять: сначала установить причину сбоя. Приложение и БД эта
операция не меняет.

Исторический `deploy/native/nginx.conf` содержит self-signed пути.
В текущий `Deploy-RhissethVps.py` добавлена защита install/hosting:
virtual host с `/letsencrypt/live/` сохраняется. Старые копии скрипта этой
защиты не имеют; защита применяется после доставки текущей версии скрипта.
Не перезаписывать старым шаблоном действующий virtual host после выпуска.
Перед обновлением nginx сверять diff и сохранять ACME-настройки.
Резервные копии ACME state хранить защищённо, отдельно от публичного Git.

Источники: [HTTP-01 Let's Encrypt](https://letsencrypt.org/docs/challenge-types/),
[Certbot: nginx, renewal и каталоги](https://eff-certbot.readthedocs.io/en/stable/using.html).

## Запуск контроллера в локальном Docker

`scripts/automation/Configure-TlsFromDocker.py` поддерживает `inspect`, `status` и
`install`, фиксирует журнал внутри проекта и обращается только к выбранному
VDS как root. Контейнер должен содержать Python 3, OpenSSH, sshpass и curl;
эти инструменты проверены в локальном `ops-nettools:latest`.

PowerShell с файлами доступа, предоставленными владельцем:

```powershell
docker run --rm --mount 'type=bind,source=C:\OPS\rhisseth.ru,target=/project' --mount 'type=bind,source=C:\Users\user\.ssh\.pass\62.113.109.168,target=/run/secrets/vds-password,readonly' --mount 'type=bind,source=C:\Users\user\.ssh\known_hosts,target=/run/secrets/known_hosts,readonly' --entrypoint python3 ops-nettools:latest /project/scripts/automation/Configure-TlsFromDocker.py inspect --password-file /run/secrets/vds-password --known-hosts /run/secrets/known_hosts
```

После успешного preflight заменить `inspect` на `install`. Для SSH-ключа вместо
пароля монтировать соответствующий файл и использовать `--ssh-key`.
Сам пароль не передаётся аргументом Docker или SSH. Копия SSH-ключа с правами
0600 существует только в временном `/run` контейнера и удаляется после работы.
Не получать trusted known_hosts простым непроверенным ssh-keyscan:
сверить отпечаток через владельца/панель VDS или ранее проверенный контроллер.
