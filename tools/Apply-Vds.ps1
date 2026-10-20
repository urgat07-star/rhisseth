param([string]$Credentials = "$PSScriptRoot\vds-credentials.json")
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$remoteScriptSource = Join-Path $PSScriptRoot 'Apply-VdsRemote.sh'

if (-not (Test-Path $Credentials)) { throw "Не найден $Credentials" }
if (-not (Test-Path $remoteScriptSource)) { throw "Не найден серверный сценарий: $remoteScriptSource" }
$cfg = Get-Content $Credentials -Raw | ConvertFrom-Json
if (-not (Test-Path $cfg.KeyPath)) { throw "SSH-ключ не найден: $($cfg.KeyPath)" }
if (-not $cfg.RemotePath) { throw 'В файле учётных данных не задан RemotePath.' }

$ssh = @('-i',$cfg.KeyPath,'-p',[string]$cfg.Port,'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes')
$scp = @('-i',$cfg.KeyPath,'-P',[string]$cfg.Port,'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes')
$target = "$($cfg.User)@$($cfg.Host)"
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$remoteScript = "/tmp/rhisseth-apply-$stamp.sh"
$logDirectory = Join-Path $repo ("reports\automation-logs\{0}" -f (Get-Date -Format 'yyyy-MM-dd'))
$logPath = Join-Path $logDirectory "$stamp-apply-vds.md"
$startedUtc = (Get-Date).ToUniversalTime()
$startedMoscow = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId($startedUtc, 'Russian Standard Time')
$output = @()
$exitCode = -1
$validation = 'не выполнена'
$changeOccurred = 'нет'

$ok = (Read-Host 'Создать backup БД, проверить все миграции на временной копии, применить их и перезапустить службы? Введите YES').Trim()
if ($ok -cne 'YES') { throw 'Операция отменена.' }

New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
@(
    '# Применение изменений Rhisseth на VDS',
    '',
    "- UTC начало: $($startedUtc.ToString('yyyy-MM-dd HH:mm:ss'))",
    "- Москва начало: $($startedMoscow.ToString('yyyy-MM-dd HH:mm:ss'))",
    '- Задача: apply-vds (пункт 7)',
    "- Контроллер: $env:COMPUTERNAME",
    "- Цель: Rhisseth VDS $($cfg.Host)",
    '- Статус: операция начата; итог будет записан после выполнения'
) | Set-Content -Encoding UTF8 $logPath
if (-not (Test-Path $logPath)) { throw 'Не удалось создать обязательный журнал операции; изменения не выполнялись.' }
try {
    & scp @scp $remoteScriptSource "$target`:$remoteScript"
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось передать проверенный сценарий на VDS.' }

    $remoteCommand = "chmod 700 '$remoteScript' && '$remoteScript' '$($cfg.RemotePath)'"
    $output = @(& ssh @ssh $target $remoteCommand 2>&1)
    $exitCode = $LASTEXITCODE
    $output | ForEach-Object { Write-Host $_ }
    if ($exitCode -ne 0) { throw "Применение изменений завершилось ошибкой. Код: $exitCode" }
    $validation = 'backup БД проверен; все миграции проверены на восстановленной копии и в production; rhisseth/nginx активны; health-check успешен'
    $changeOccurred = 'да: применены ожидающие миграции и перезапущена служба rhisseth'
} finally {
    & ssh @ssh $target "rm -f '$remoteScript'" 2>$null
    $finishedUtc = (Get-Date).ToUniversalTime()
    $finishedMoscow = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId($finishedUtc, 'Russian Standard Time')
    $safeOutput = ($output -join "`n") -replace '(?i)(password|token|secret|cookie)\s*[=:]\s*\S+', '$1=[REDACTED]'
    @(
        '# Применение изменений Rhisseth на VDS',
        '',
        "- UTC начало: $($startedUtc.ToString('yyyy-MM-dd HH:mm:ss'))",
        "- Москва начало: $($startedMoscow.ToString('yyyy-MM-dd HH:mm:ss'))",
        "- UTC окончание: $($finishedUtc.ToString('yyyy-MM-dd HH:mm:ss'))",
        "- Москва окончание: $($finishedMoscow.ToString('yyyy-MM-dd HH:mm:ss'))",
        '- Задача: apply-vds (пункт 7)',
        "- Контроллер: $env:COMPUTERNAME",
        "- Цель: Rhisseth VDS $($cfg.Host)",
        '- Тип действия: backup PostgreSQL, тестовый restore, репетиция всех миграций, production migrations, restart/reload, health-check',
        '- Preflight: выполняется серверным сценарием до любых изменений',
        "- Exit code: $exitCode",
        "- Изменение/перезапуск: $changeOccurred",
        "- Валидация: $validation",
        '- Секреты: не выводились; потенциальные значения отредактированы',
        '',
        '## Санитизированный вывод',
        '',
        '```text',
        $safeOutput,
        '```'
    ) | Set-Content -Encoding UTF8 $logPath
    Write-Host "Журнал операции: $logPath"
}

Write-Host 'Backup БД проверен, все миграции прошли репетицию и применены, службы проверены.' -ForegroundColor Green
