# Восстановление с компьютера через Docker

ИИ, Python и runner на компьютере не нужны. Docker запускает только контроллер;
проект устанавливается на целевую Ubuntu 24.04 как native systemd/nginx/PostgreSQL.
Внутренние адреса блокируются согласно AGENTS.md; для них нужен STU-AUTOMATION-01.
Этот вариант предназначен для целевой ВМ с публичным IP.

## Подготовка

1. Установите [Docker Desktop для Windows/macOS/Linux](https://docs.docker.com/get-started/get-docker/)
   либо [Docker Engine и Compose plugin для Linux](https://docs.docker.com/engine/install/).
   На Windows включите Linux containers. Откройте терминал в каталоге комплекта.
2. Цель: чистая Ubuntu 24.04 x86_64, >=1 CPU/1 ГБ RAM/10 ГБ диска,
   установленный Python 3 и SSH server, интернет для пакетов. SSH-учетка root
   либо sudo с тем же паролем. Свободные порты: 80/443/5432/8080.
3. Получите у администратора backup-хранилища ограниченный SSH ключ для
   пользователя rhisseth-backup и сохраните как `deploy/recovery/storage-key.local`.
   Пароль целевой ВМ не дает доступа к бэкапу, поэтому этот отдельный ключ обязателен.
4. Получите независимо проверенные SSH host keys цели и backup-сервера и сохраните
   в `deploy/recovery/known_hosts.local` в формате OpenSSH known_hosts.
   Для нестандартного SSH порта запись должна иметь вид `[IP]:PORT`.
   Не отключайте проверку host keys; один ssh-keyscan без сверки недостаточен.

```bash
docker version
docker compose version
```

## Один конфиг с IP и паролем

Windows PowerShell, из корня комплекта:

```powershell
Copy-Item deploy/recovery/recovery.example.json deploy/recovery/recovery.local.json
notepad deploy/recovery/recovery.local.json
```

Linux/macOS:

```bash
cp deploy/recovery/recovery.example.json deploy/recovery/recovery.local.json
chmod 600 deploy/recovery/recovery.local.json deploy/recovery/storage-key.local
nano deploy/recovery/recovery.local.json
```

Заполните target.ip, target.port, target.username и target.password. Это
единственный постоянный файл с SSH паролем цели; не передавайте его в Git,
командную строку или архив комплекта. Ограничьте доступ к файлу своей учетной
записью на ПК. JSON требует экранировать кавычку как `\"`, обратный слеш как `\\`.
Backup по умолчанию 185.216.87.44. Пароль не нужен в Dockerfile/.env.

Конфиг подключается как read-only Compose secret; временный файл для контроллера
создается только в tmpfs контейнера и удаляется после команды. SSH пароль не
копируется на целевую ВМ, в постоянный Docker volume или журналы. При SSH
используется кратковременная переменная окружения дочернего процесса sshpass;
пользователь с административным доступом к ПК/Docker может читать секреты.
Compose secret не шифрует исходный локальный JSON.
[Механизм Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/).

## Команды

Все команды выполняются из корня комплекта. До restore проверьте список архивов
и успешный preflight. При ошибке остановитесь и изучите журнал.

```bash
docker compose -f deploy/recovery/compose.yaml build
docker compose -f deploy/recovery/compose.yaml run --rm recovery list
docker compose -f deploy/recovery/compose.yaml run --rm recovery preflight
docker compose -f deploy/recovery/compose.yaml run --rm recovery restore
docker compose -f deploy/recovery/compose.yaml run --rm recovery validate
```

Restore выбирает последний завершенный архив и последний стабильный GitHub
Release, опубликованный владельцем urgat07-star. Требуется опубликованный Release;
ветка сама по себе не является утвержденным релизом. После отдельного выбора
владельцем конкретного ref вместо обычной restore можно выполнить:

```bash
docker compose -f deploy/recovery/compose.yaml run --rm recovery restore release/0.0.1
```

Пакеты Ubuntu, PostgreSQL 16, nginx, venv/Python зависимости из requirements.lock,
конфиги, службы и данные устанавливаются автоматически. Конфликты существующих
служб/БД/каталогов останавливают операцию; действующее приложение не перезаписывается.
Не запускайте операции одновременно. Восстановление подтверждено только если
restore и validate завершились с exit code 0 и ожидаемыми PASS.

Для instance.tls_mode=test внешний HTTPS проверить так:

```bash
docker compose -f deploy/recovery/compose.yaml run --rm recovery external-check
```

Ожидаются HTTP 200/401/303. Сертификат тестовый, браузер предупредит о доверии.
Далее проверка после перезагрузки целевой ВМ:

```bash
docker compose -f deploy/recovery/compose.yaml run --rm recovery reboot-test
```

Дождитесь доступности SSH, затем:

```bash
docker compose -f deploy/recovery/compose.yaml run --rm recovery validate
docker compose -f deploy/recovery/compose.yaml run --rm recovery external-check
```

Ожидается изменение boot ID и успешные проверки. Локальные журналы:
`deploy/recovery/reports/automation-logs/YYYY-MM-DD/`; предъявите их заказчику
вместе с именем/хешем архива, релизом/SHA и результатами приемки.

## Домен и HTTPS

Для теста оставьте tls_mode=test. Для публичного HTTPS заполните domain,
tls_mode=public, acme_email, public_ip при NAT. DNS должен указывать на цель,
внешний firewall/NAT пропускать TCP 80/443. Рабочий rhisseth.ru не переключайте
без согласования. Для public режима external-check не используется; проверьте
`https://ВАШ_ДОМЕН/index.php` браузером или curl без отключения проверки TLS.

После установки домен задается на ВМ в `/etc/rhisseth/instance.json`; команды
изменения и применения находятся в `docs/manual-recovery.md`, раздел 9.

## Ограничения и очистка

Нужен сетевой доступ из Docker к SSH цели, SSH-хранилищу, GitHub и интернету.
Docker не устраняет ограничения VPN/NAT. На целевую ВМ Docker не устанавливается.
Переносимая Docker схема должна быть испытана на разрешенной чистой публичной
ВМ перед штатным использованием; успешное восстановление 17.09 было через runner.
Локально проверены сборка образа, структура Compose, три проверки безопасности
в контейнере без сети и запрет внутренних IP до записи реквизитов/сетевых операций.
Новая операция восстановления через Docker на реальной ВМ не выполнялась.

Локальное состояние, архив во время передачи и reboot ID хранятся в named volume
recovery_state; внутри него могут временно оставаться данные при аварийном выходе.
После завершения приемки удалить контейнерное состояние (на ВМ это не влияет):

```bash
docker compose -f deploy/recovery/compose.yaml down --volumes
```

Команда удалит также сохраненный reboot ID. Локальный конфиг, ключ и журналы
останутся на ПК: храните их с ограниченным доступом либо удалите вручную согласно
правилам своей организации.
