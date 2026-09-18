# Восстановление Rhisseth без ИИ

Инструкция для администратора. Проверенное восстановление: Ubuntu 24.04,
17.09.2026, ВМ 10.210.52.56. Команды выполняются человеком; ИИ не требуется.
Выполняйте шаги последовательно и останавливайтесь при ненулевом exit code.

Для запуска без установленного Python на ПК доступен
[Docker контроллер с локальным SSH конфигом](../deploy/recovery/README.md).

## 1. Выберите способ запуска

| Куда восстанавливаем | Где выполняются операции |
|---|---|
| Внутренняя ВМ, например 10.210.52.56 | На STU-AUTOMATION-01 (10.210.52.128); подключиться к runner можно с любого компьютера, имеющего сетевой доступ |
| ВМ с публичным IP | На runner либо на отдельном Linux компьютере/ВМ с локальными SSH ключами и конфигом |

Внутренние цели и Passbolt обслуживаются только через runner согласно
AGENTS.md. «Из любого места» для внутренних целей означает SSH подключение к
runner; прямой запуск из WSL/Docker Desktop/рабочей станции запрещен.
Для публичных целей Docker не нужен. Windows/macOS могут быть SSH терминалом;
сам переносимый контроллер требует Linux (использует fcntl).

## 2. Необходимый софт и доступы

**Компьютер оператора:** OpenSSH client, доступ по сети к runner, выданный
приватный SSH ключ и независимо подтвержденный host key runner. На Windows
проверить `ssh -V` в PowerShell. PowerShell 7 нужен только для дополнительной
Windows обертки; при обычном SSH подключении он не требуется.

**Linux контроллер:** Python >=3.11, git, OpenSSH client, curl, CA certificates,
tzdata; sshpass нужен при входе по паролю/Passbolt. Установить на новом публичном
Linux контроллере Ubuntu 24.04:

```bash
sudo apt-get update
sudo apt-get install -y python3 git openssh-client curl ca-certificates tzdata sshpass
python3 --version
ssh -V
git --version
```

На существующем runner эти зависимости и Passbolt CLI уже настроены. Не
экспортируйте конфиг/секреты Passbolt с runner на рабочий компьютер.

**Целевая ВМ:** Ubuntu 24.04 x86_64, >=1 vCPU, >=1 ГБ реальной RAM, >=10 ГБ
диска и достаточно свободного места для архива/распаковки/БД. Нужны Python 3
и OpenSSH server, вход root или учетная запись с sudo. Для входа ключом от
не-root требуется работающий `sudo -n`; для пароля контроллер передает тот же
пароль в sudo через приватный stdin. Для загрузки пакетов нужен интернет.
На образе Ubuntu Python/SSH должны быть подготовлены администратором образа.
Не устанавливайте nginx/PostgreSQL вручную перед preflight.

Скрипт сам устанавливает: git, nginx, postgresql-16, postgresql-client-16,
python3-venv, python3-pip, ca-certificates, openssl, openssh-client, tar, gzip,
curl, certbot, python3-certbot-nginx и зависимости приложения из requirements.lock
в отдельный venv. Создает конфиги и службы systemd. При активном UFW добавляет
TCP 80/443, сохраняя остальные правила. Cloud firewall/NAT настраиваются отдельно.

**Нужны доступы:** чтение GitHub urgat07-star/rhisseth, SSH к цели,
ограниченный ключ `rhisseth-backup` к 185.216.87.44 и право читать архивы.
Пароли, приватные ключи и controller config не помещайте в Git и отчеты.

## 3. Получите комплект скриптов

Комплект — каталог проекта со следующими файлами:

```text
scripts/automation/Run-RhissethRecovery.py
scripts/automation/rhisseth_deploy.py
scripts/automation/rhisseth_validate.py
scripts/automation/rhisseth_backup.py
scripts/automation/rhisseth_storage.py
scripts/automation/Bootstrap-RhissethStorage.py
tests/test_recovery_safety.py
deploy/native/controller.example.json
```

Для дополнительных диагностических операций передавайте весь каталог
`scripts/automation`. На runner комплект уже находится в
`/home/avalon/rhisseth.ru`. На новом контроллере положите проверенный комплект,
например в `$HOME/rhisseth.ru`. Получение кода приложения при восстановлении
выполняется самим контроллером из GitHub; комплект автоматизации нужен отдельно.
На дату этой инструкции новые файлы автоматизации в локальной рабочей копии
еще не опубликованы в GitHub: простой clone выбранного релиза не гарантирует
наличие комплекта. Используйте переданный администратором комплект или после
публикации клонируйте версию, действительно содержащую эти файлы.

Готовый архив: `reports/distribution/rhisseth-recovery-kit-2026-09-17.zip`.
Он содержит скрипты, проверки, примеры конфигурации и эту инструкцию без
приватных ключей/паролей. Передайте его на выбранный Linux контроллер;
распаковать без дополнительного unzip можно так:

```bash
mkdir -p "$HOME/rhisseth.ru"
python3 -m zipfile -e rhisseth-recovery-kit-2026-09-17.zip "$HOME/rhisseth.ru"
cd "$HOME/rhisseth.ru"
```

Не распаковывайте новый комплект поверх работающего runner без проверки версии
администратором. Секреты и доверенные host keys выдаются отдельно.

## 4. Внутренняя ВМ: подключение и настройка runner

На компьютере оператора укажите свой ключ и файл доверенных host keys:

```bash
ssh -i /path/to/runner-key -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/path/to/known_hosts avalon@10.210.52.128
```

Windows принимает аналогичные пути вида `C:/secure/runner-key`. Ожидаемый
fingerprint runner:
`SHA256:ChgM7wjz5n58p0QUUh2RNkebM8ZuP/fan+eo+n2iQyQ`.
Не отключайте проверку host key. Доверенный known_hosts получите у администратора.

Все следующие команды этого раздела выполняются **в SSH сессии runner**:

```bash
hostname
cd /home/avalon/rhisseth.ru
umask 077
mkdir -p "$HOME/.config/rhisseth"
cp deploy/native/controller.example.json "$HOME/.config/rhisseth/controller.json"
chmod 600 "$HOME/.config/rhisseth/controller.json"
nano "$HOME/.config/rhisseth/controller.json"
```

В targets.test укажите IP/логин цели и ID ресурса Passbolt; URI и логин ресурса
должны совпадать. Роль `test` в конфиге означает целевую ВМ, включая публичную.
Сейчас: IP 10.210.52.56, логин avalon, resource_id
34b8e391-f4e8-4dbc-9304-6fcc22e942ab. Оставьте enforce_runner=true.
В instance.test_ip также укажите новый IP. Для испытания tls_mode=test,
domain=rhisseth.ru; промышленный DNS менять не нужно.

Источник и хранилище уже настроены. Ключ хранилища на runner:
`/home/avalon/rhisseth.ru/.local/recovery/storage-key`. Проверить наличие, не выводя содержимое:

```bash
test -r .local/recovery/storage-key
python3 scripts/automation/Run-RhissethRecovery.py list --controller-config "$HOME/.config/rhisseth/controller.json"
```

## 5. Новый публичный Linux контроллер

Этот вариант разрешен только если **все** targets.source/storage/test имеют
публичные IP. Внутренний Passbolt здесь не используется.
Создайте `$HOME/.config/rhisseth/controller.json` с правами 600:

```json
{
  "enforce_runner": false,
  "targets": {
    "source": {
      "host": "62.113.109.168",
      "username": "root",
      "identity_file": "/home/operator/.ssh/source-key"
    },
    "storage": {
      "host": "185.216.87.44",
      "automation_identity_file": "/home/operator/.ssh/rhisseth-storage-key"
    },
    "test": {
      "host": "PUBLIC_TARGET_IP",
      "username": "root",
      "identity_file": "/home/operator/.ssh/target-key"
    }
  },
  "instance": {
    "domain": "recovery.example.org",
    "tls_mode": "test",
    "test_ip": "PUBLIC_TARGET_IP",
    "acme_email": "",
    "public_ip": "",
    "application_port": 8080,
    "database_port": 5432
  }
}
```

Замените placeholders реальными IP/путями/доменом. Пути должны быть абсолютными:
`~` внутри JSON не разворачивается. Источник нужен для backup; операции
list/preflight/restore/validate не требуют входа на источник.
Не вызывайте setup-storage для уже действующего хранилища без его администратора.
Ограниченный ключ для чтения передается защищенным каналом либо администратор
выдает новый ключ с ограниченным доступом. Для list/get используется специальный
SSH протокол, а не SFTP: копирование архивов через обычный scp не поддерживается.

```bash
chmod 600 "$HOME/.config/rhisseth/controller.json"
chmod 600 "$HOME/.ssh/target-key" "$HOME/.ssh/rhisseth-storage-key"
cd "$HOME/rhisseth.ru"
python3 scripts/automation/Run-RhissethRecovery.py list --controller-config "$HOME/.config/rhisseth/controller.json"
```

До запуска проверьте fingerprint цели/хранилища по независимому каналу и внесите
их в `$HOME/.ssh/known_hosts`. Один ssh-keyscan без сверки не удостоверяет сервер.
Получить кандидата и показать fingerprint можно так, заменив TARGET_IP:

```bash
ssh-keyscan -t ed25519 TARGET_IP > /tmp/rhisseth-hostkey
ssh-keygen -lf /tmp/rhisseth-hostkey
```

Только после сверки:

```bash
mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
cat /tmp/rhisseth-hostkey >> "$HOME/.ssh/known_hosts"
chmod 600 "$HOME/.ssh/known_hosts"
rm /tmp/rhisseth-hostkey
```

Для текущей внутренней цели fingerprint
`SHA256:ou0iqFYwatLJlceBIuqF2Xd+re58cbFAtpAL5G1dpVc` уже закреплен на runner.
Смена ключа требует сверки с администратором, а не удаления предупреждения.

## 6. Утвержденный релиз

В GitHub владелец urgat07-star открывает Releases → Draft a new release,
выбирает tag, например v0.0.1, и проверенный commit, снимает pre-release и
публикует Release своим аккаунтом. Ветка сама по себе не является Release.
Контроллер без дополнительного аргумента выбирает последний по published_at
стабильный Release, опубликованный владельцем; fallback на main отсутствует.
Теги должны соответствовать vX.Y.Z, X.Y.Z или release/X.Y.Z.

Однократный выбор ветки `release/0.0.1` владельцем был разрешен для испытания.
Для повторения именно этого испытания допустима команда из шага 7 с явным
аргументом. Для штатной работы публикуйте Release. До публикации команда без
аргумента завершится ошибкой `No owner-published approved stable release`.

## 7. Preflight и восстановление

На выбранном Linux контроллере, из корня комплекта:

```bash
python3 scripts/automation/Run-RhissethRecovery.py preflight --controller-config "$HOME/.config/rhisseth/controller.json"
```

Продолжать только при exit code 0. Занятые порты, существующий экземпляр,
кластер БД или нехватка RAM/диска останавливают установку. На уже работающей
10.210.52.56 отказ preflight ожидаем: она восстановлена. Для нового восстановления
используйте чистую ВМ; скрипт не перезаписывает действующую базу.

Штатное восстановление из последнего завершенного архива и утвержденного Release:

```bash
python3 scripts/automation/Run-RhissethRecovery.py restore --controller-config "$HOME/.config/rhisseth/controller.json"
```

Повторение согласованного испытания выбранной версии, **вместо** предыдущей команды:

```bash
python3 scripts/automation/Run-RhissethRecovery.py restore release/0.0.1 --controller-config "$HOME/.config/rhisseth/controller.json"
```

Контроллер скачивает архив, сверяет SHA256 и размер, проверяет безопасную
распаковку и миграции, загружает зафиксированный код, устанавливает пакеты,
восстанавливает данные и проверяет приложение. Не запускайте две операции
одновременно. Изменять закрепленный SHA ветки без согласования нельзя.
Выбор произвольного исторического архива флагом контроллера пока не реализован;
эта инструкция восстанавливает последний завершенный архив.

## 8. Обязательная приемка и перезагрузка

```bash
python3 scripts/automation/Run-RhissethRecovery.py validate --controller-config "$HOME/.config/rhisseth/controller.json"
```

Ожидаются PASS для ролей, CSRF, регистрации, карты/API и сохранности данных;
службы должны быть active. Для tls_mode=test дополнительно проверить доступ
с контроллера, сертификат и имя:

```bash
python3 scripts/automation/Run-RhissethRecovery.py external-check --controller-config "$HOME/.config/rhisseth/controller.json"
```

Ожидаются HTTP 200/401/303. Эта дополнительная команда рассчитана на тестовый
сертификат; для public TLS используйте curl к настроенному домену без -k:

```bash
curl --connect-timeout 10 --max-time 20 -sS -o /dev/null -w '%{http_code}\n' https://recovery.example.org/index.php
```

Проверка автозапуска прерывает работу только целевой ВМ:

```bash
python3 scripts/automation/Run-RhissethRecovery.py reboot-test --controller-config "$HOME/.config/rhisseth/controller.json"
```

Дождитесь доступности SSH цели, затем:

```bash
python3 scripts/automation/Run-RhissethRecovery.py validate --controller-config "$HOME/.config/rhisseth/controller.json"
```

Ожидается подтверждение изменения boot ID и повторные PASS. После перезагрузки
повторите соответствующую внешнюю HTTPS проверку. Тестовый сертификат браузер
не считает публично доверенным; это не ошибка восстановления.

## 9. Домен и публичный HTTPS

До восстановления укажите в instance: domain, tls_mode=public, acme_email,
public_ip при NAT. DNS должен указывать исключительно на эту ВМ/ее public_ip,
входящие 80/443 доступны, включая внешний firewall. Не переключайте рабочий
rhisseth.ru на испытательную ВМ без отдельного решения.

После установки конфиг находится на цели в `/etc/rhisseth/instance.json`.
Для изменения подключайтесь к цели **с разрешенного контроллера**:

```bash
ssh root@TARGET_IP
sudo nano /etc/rhisseth/instance.json
sudo python3 /opt/rhisseth/scripts/automation/rhisseth_deploy.py apply-config --config /etc/rhisseth/instance.json
sudo python3 /opt/rhisseth/scripts/automation/rhisseth_deploy.py validate --config /etc/rhisseth/instance.json
exit
```

Замените root логином цели при необходимости. Затем синхронизируйте instance
в конфиге контроллера. Применение выполняет проверку nginx и выпуск сертификата
ACME webroot; продление обслуживает certbot timer. Публичный ACME в текущем
испытании не проверялся.

## 10. Журналы, отчет и типовые ошибки

Каждая команда контроллера создает Markdown журнал:
`reports/automation-logs/YYYY-MM-DD/`. Журнал цели:
`/var/log/rhisseth/reports/automation-logs/`. Финальная строка содержит exit code
и путь. Сохраните эти файлы вместе с номером релиза, SHA и именем/хешем архива.
Предъявите заказчику отчет: цель, время UTC/МСК, preflight, выбранные данные/код,
изменения, reboot, результаты PASS/HTTP, ограничения и ссылки на журналы.
Пароли/ключи не включайте. Пример:
`reports/2026-09-17-rhisseth-backup-recovery.md` и соответствующий Word.
При анализе инфраструктурного сбоя нужны технический Markdown и управленческий Word.

| Ошибка | Действие |
|---|---|
| Нет утвержденного Release | Владелец публикует стабильный Release; не подменять main |
| SSH host key changed | Независимо сверить новый fingerprint, затем обновить доверенную запись |
| Passbolt endpoint mismatch | Исправить URI/IP ресурса и controller config |
| Permission denied / sudo unavailable | Проверить логин, ключ/секрет, sudo; пароль не передавать аргументом |
| Порт/кластер/каталог занят | Предъявить конфликт; использовать чистую ВМ, не удалять чужое ПО/данные |
| HTTP timeout | Проверить UFW, cloud firewall/NAT и nginx; не отключать firewall целиком |
| Dirty source checkout при backup | Владелец сохраняет изменения в Git и очищает checkout; расширенный worktree бэкап пока не согласован |
| Установка прервалась | Сохранить журналы; частично установленный экземпляр не перезаписывать, восстановить снимок/подготовить другую чистую ВМ |

Факт восстановления с новым публичным контроллером и публичный выпуск TLS
пока не испытаны. Проверенный вариант — SSH на существующий runner и целевая
Ubuntu 24.04; переносимый режим предоставлен с указанными требованиями.
