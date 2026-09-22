# Настройка SSH-доступа к VDS

## Что означает `KeyPath`

`KeyPath` — это полный путь к **приватному SSH-ключу на вашем компьютере**. Это не URL сайта, не IP-адрес и не пароль.

Пример:

```json
"KeyPath": "C:/Users/ИмяПользователя/.ssh/rhisseth_vds_ed25519"
```

Файл без расширения `*.pub` является приватным ключом и не должен передаваться другим людям или помещаться в Git.

## Проверка существующего ключа

В PowerShell выполните:

```powershell
Get-ChildItem "$env:USERPROFILE\.ssh" -Force
```

Если есть файл `rhisseth_vds_ed25519`, в `vds-credentials.json` укажите:

```json
"KeyPath": "C:/Users/ВАШЕ_ИМЯ/.ssh/rhisseth_vds_ed25519"
```

Если такого файла нет, проверьте стандартные ключи `id_ed25519` или `id_rsa`. Используйте приватный файл без `.pub`.

## Создание нового ключа

Если ключа нет, создайте его:

```powershell
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\rhisseth_vds_ed25519" -C "rhisseth-vds"
```

Команда создаст два файла:

- `rhisseth_vds_ed25519` — приватный ключ; хранить в секрете;
- `rhisseth_vds_ed25519.pub` — открытый ключ; его можно передать администратору VDS.

Открытый ключ можно посмотреть так:

```powershell
Get-Content "$env:USERPROFILE\.ssh\rhisseth_vds_ed25519.pub"
```

Его нужно добавить на VDS в файл `~/.ssh/authorized_keys` пользователя, указанного в `vds-credentials.json`.

## Заполнение `vds-credentials.json`

Создайте рабочий файл из шаблона:

```powershell
Copy-Item .\tools\vds-credentials.example.json .\tools\vds-credentials.json
notepad .\tools\vds-credentials.json
```

Минимальный пример:

```json
{
  "Host": "62.113.109.168",
  "User": "root",
  "Port": 22,
  "KeyPath": "C:/Users/ВАШЕ_ИМЯ/.ssh/rhisseth_vds_ed25519",
  "RemotePath": "/opt/rhisseth/repository"
}
```

Если проект на VDS находится в другом каталоге, замените `RemotePath` на фактический путь.

## Проверка подключения

До запуска скриптов проверьте SSH-доступ вручную:

```powershell
ssh -i "$env:USERPROFILE\.ssh\rhisseth_vds_ed25519" root@62.113.109.168 "hostname"
```

Ожидаемый результат — имя VDS `rhisseth` или аналогичное имя хоста. Если появляется запрос подтверждения отпечатка, убедитесь, что адрес правильный, и подтвердите его только после проверки у администратора.

## Безопасность

- Не отправляйте приватный ключ в чат, GitHub или мессенджеры.
- Не переименовывайте приватный ключ в `.pub`.
- Файл `vds-credentials.json` уже исключён из Git через `.gitignore`.
- Если ключ скомпрометирован, удалите его из `authorized_keys` на VDS и создайте новый.

## Установка открытого ключа на VDS

Сначала убедитесь, что открытый ключ существует:

```powershell
Test-Path "$env:USERPROFILE\.ssh\rhisseth_vds_ed25519.pub"
```

Добавьте его на сервер, используя текущий пароль пользователя `root`:

```powershell
Get-Content "$env:USERPROFILE\.ssh\rhisseth_vds_ed25519.pub" -Raw |
    ssh root@62.113.109.168 "umask 077; mkdir -p /root/.ssh; cat >> /root/.ssh/authorized_keys; chmod 700 /root/.ssh; chmod 600 /root/.ssh/authorized_keys"
```

Проверьте вход с принудительным использованием ключа:

```powershell
ssh -i "$env:USERPROFILE\.ssh\rhisseth_vds_ed25519" -o IdentitiesOnly=yes root@62.113.109.168 "hostname"
```

При успешном подключении сервер возвращает имя `rhisseth` без запроса пароля учётной записи VDS.

## Автоматическое подключение через ssh-agent

Если приватный ключ защищён парольной фразой, Windows может хранить расшифрованный ключ в памяти `ssh-agent`. Парольную фразу потребуется ввести один раз после добавления ключа.

Откройте PowerShell от имени администратора и включите службу:

```powershell
Set-Service ssh-agent -StartupType Automatic
Start-Service ssh-agent
```

Добавьте ключ в агент:

```powershell
ssh-add "$env:USERPROFILE\.ssh\rhisseth_vds_ed25519"
```

Проверьте загруженные ключи:

```powershell
ssh-add -l
```

После этого подключение и скрипты используют ключ автоматически:

```powershell
ssh -i "$env:USERPROFILE\.ssh\rhisseth_vds_ed25519" -o IdentitiesOnly=yes root@62.113.109.168 "hostname"
.\tools\Check-VdsChanges.ps1
.\tools\Publish-ToVds.ps1 -Branch main
```

Если после перезагрузки ключ не загружен в агент, повторите только команду `ssh-add`. Служба `ssh-agent` при этом уже запускается автоматически.

## Настройка файла подключения

Рабочий файл `vds-credentials.json` должен содержать:

```json
{
  "Host": "62.113.109.168",
  "User": "root",
  "Port": 22,
  "KeyPath": "C:/Users/NLavrov/.ssh/rhisseth_vds_ed25519",
  "RemotePath": "/opt/rhisseth/repository"
}
```

Проверка конфигурации:

```powershell
$cfg = Get-Content .\tools\vds-credentials.json -Raw | ConvertFrom-Json
Test-Path $cfg.KeyPath
ssh -i $cfg.KeyPath -o IdentitiesOnly=yes "$($cfg.User)@$($cfg.Host)" "hostname"
```

Первая команда проверки пути должна вернуть `True`, а SSH — имя сервера `rhisseth`.
