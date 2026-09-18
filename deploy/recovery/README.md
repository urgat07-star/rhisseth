# Восстановление Rhisseth с Windows

Все команды вводите в **PowerShell на своем ПК**, по одной. Нужны интернет,
Docker Desktop и чистая Ubuntu 24.04 с **публичным IP**. Для внутреннего адреса
10.210.52.56 этот вариант без runner заблокирован согласно AGENTS.md.

## 1. Получите у администратора

| Что получить | Куда положить |
|---|---|
| `rhisseth-docker-recovery-kit-2026-09-17.zip` | В папку **Загрузки** |
| `storage-key.local` — ключ доступа к бэкапам | `C:\Rhisseth-recovery\deploy\recovery\storage-key.local` после распаковки |
| `known_hosts.local` — проверенные SSH ключи вашей ВМ и хранилища | `C:\Rhisseth-recovery\deploy\recovery\known_hosts.local` после распаковки |
| IP новой ВМ, SSH порт, логин и пароль | В конфиг из шага 3 |

Комплект передает администратор проекта: в его рабочем репозитории он находится
в `reports/distribution/rhisseth-docker-recovery-kit-2026-09-17.zip`.
В GitHub комплект пока не опубликован. Ключ бэкапа выдает администратор хранилища;
оба `.local` файла передаются отдельно, в архиве их нет.

**Бэкап берется автоматически:** сервер `185.216.87.44`, каталог
`/srv/backups/rhisseth`, пользователь `rhisseth-backup`.
**Приложение берется автоматически:** `https://github.com/urgat07-star/rhisseth`.
**Восстанавливается:** на вашу ВМ в `/opt/rhisseth` и PostgreSQL.
Скачивать архив бэкапа и клонировать GitHub самостоятельно не нужно.

Администратор готовит ВМ: Ubuntu 24.04 x86_64, минимум 1 CPU / 1 ГБ RAM /
10 ГБ диска, Python 3 и SSH server, свободные порты 80/443/5432/8080.
Логин — root либо пользователь с sudo и тем же паролем.

## 2. Установите Docker и распакуйте комплект

Скачайте [Docker Desktop для Windows](https://docs.docker.com/desktop/setup/install/windows-install/).
В установщике выберите WSL 2, если предлагается; выполните указания и перезагрузку,
если потребуется. Запустите Docker Desktop через Пуск, дождитесь готовности Engine.
Используются Linux containers. Если Docker не запускается, обратитесь к администратору.

Откройте **Пуск → PowerShell**:

```powershell
docker version
docker compose version
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\rhisseth-docker-recovery-kit-2026-09-17.zip" -DestinationPath 'C:\Rhisseth-recovery'
Set-Location 'C:\Rhisseth-recovery'
```

В `docker version` должны быть Client и Server без ошибки. В папке должны быть
`deploy`, `scripts`, `tests`. Не распаковывайте поверх старого комплекта.
Положите два `.local` файла по адресам из таблицы. Не добавляйте к именам `.txt`.

## 3. Заполните конфиг

```powershell
Copy-Item 'deploy\recovery\recovery.example.json' 'deploy\recovery\recovery.local.json'
notepad 'deploy\recovery\recovery.local.json'
```

В Блокноте замените только `PUBLIC_VM_IP` на IP ВМ, `root` на свой логин,
`FILL_LOCALLY` на пароль; SSH порт `22` в разделе `target` измените, если выдан другой.
Остальное оставьте как есть. Сохраните и закройте Блокнот. Кавычки и запятые
не удаляйте. В пароле кавычку запишите как `\"`, обратный слеш как `\\`.
Пароль хранится в этом локальном конфиге: не отправляйте файл с отчетом или в GitHub.

```powershell
Test-Path 'deploy\recovery\recovery.local.json'
Test-Path 'deploy\recovery\storage-key.local'
Test-Path 'deploy\recovery\known_hosts.local'
```

Все три результата должны быть `True`.

## 4. Восстановите и проверьте

После каждой команды сразу выполните **`$LASTEXITCODE`**: должно быть **0**.
Если другое число или ошибка — остановитесь и передайте ее администратору.
Сначала сборка, список бэкапов (не должен быть пустым) и проверка чистой ВМ:

```powershell
docker compose -f deploy/recovery/compose.yaml build
$LASTEXITCODE
docker compose -f deploy/recovery/compose.yaml run --rm recovery list
$LASTEXITCODE
docker compose -f deploy/recovery/compose.yaml run --rm recovery preflight
$LASTEXITCODE
```

Только после успешной проверки:

```powershell
docker compose -f deploy/recovery/compose.yaml run --rm recovery restore
$LASTEXITCODE
docker compose -f deploy/recovery/compose.yaml run --rm recovery validate
$LASTEXITCODE
docker compose -f deploy/recovery/compose.yaml run --rm recovery external-check
$LASTEXITCODE
```

Выбираются последний завершенный бэкап и утвержденный GitHub Release; нужный софт
устанавливается автоматически. Ожидайте `PASS`, для HTTPS — ответы `200`, `401`, `303`.
При `No owner-published approved stable release` владелец должен опубликовать Release.
При занятых портах/существующей БД ничего самостоятельно не удаляйте.

## 5. Перезагрузка и отчет

Перезагрузите целевую ВМ (не свой ПК):

```powershell
docker compose -f deploy/recovery/compose.yaml run --rm recovery reboot-test
$LASTEXITCODE
```

Подождите 1–2 минуты и повторите проверки:

```powershell
docker compose -f deploy/recovery/compose.yaml run --rm recovery validate
$LASTEXITCODE
docker compose -f deploy/recovery/compose.yaml run --rm recovery external-check
$LASTEXITCODE
```

Если ВМ еще загружается, повторите проверку позже, **не restore**.
Откройте `https://IP_ВАШЕЙ_ВМ/`. Предупреждение браузера о тестовом сертификате
ожидаемо. Проверьте страницу входа; настройку публичного домена поручите администратору.

Передайте заказчику IP, результаты проверки и папку
`C:\Rhisseth-recovery\deploy\recovery\reports\automation-logs`.
**Конфиг и SSH ключ не отправляйте.** После приемки удалите временные данные Docker:

```powershell
docker compose -f deploy/recovery/compose.yaml down --volumes
$LASTEXITCODE
```

Приложение на ВМ и журналы на ПК останутся. Конфиг и ключ также останутся:
храните их с ограниченным доступом либо удалите по указанию администратора.

Комплект прошел сборку и локальные проверки; восстановление через Docker на
публичной ВМ пока не испытано. Для администратора: `docs/docker-recovery-admin.md`.
