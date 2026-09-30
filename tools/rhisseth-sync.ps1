[CmdletBinding()]
param(
    [Parameter(Position=0)] [ValidateSet('menu','status','pull-github','push-github','compare','deploy-vds','pull-vds','rollback-vds','apply-vds','branches','help')]
    [string]$Command = 'menu',
    [string]$Branch = '',
    [string]$Credentials = "$PSScriptRoot\vds-credentials.json",
    [string]$Backup = '',
    [string]$CommitMessage = '',
    [switch]$Commit,
    [switch]$SkipBackup
)

$ErrorActionPreference = 'Stop'
$Tools = $PSScriptRoot
$Repo = Split-Path -Parent $Tools
Set-Location $Repo

function Invoke-Tool([string]$Name, [hashtable]$Params = @{}) {
    $file = Join-Path $Tools $Name
    if (-not (Test-Path $file)) { throw "Инструмент не найден: $file" }
    Write-Host "`n>>> Запуск: $Name" -ForegroundColor Cyan
    & $file @Params
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "Инструмент завершился с кодом ${LASTEXITCODE}: $Name" }
}

function Write-Report([string]$Title, [string]$Body) {
    $dir = Join-Path $Repo 'reports\Git-sync'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $stamp = Get-Date -Format 'yyyy-MM-dd-HHmmss'
    $path = Join-Path $dir "$Title-$stamp.md"
    $commit = git log -1 --pretty=format:'%H' 2>$null
    $subject = git log -1 --pretty=format:'%s' 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $commit) { $commit = 'не создан'; $subject = 'не создан' }
    @("# $Title", "", "- Дата: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')", "- Компьютер: $env:COMPUTERNAME", "- Репозиторий: $Repo", "- Git commit: $commit", "- Комментарий коммита: $subject", "", $Body) | Set-Content -Encoding UTF8 $path
    Write-Host "Отчёт: $path"
}

function Write-Header([string]$Text) {
    Write-Host "`n=== Rhisseth: $Text ===" -ForegroundColor Green
}

function Start-InteractiveMenu {
    do {
        Clear-Host
        Write-Host '==============================================' -ForegroundColor DarkCyan
        Write-Host '       Rhisseth — управление синхронизацией' -ForegroundColor Green
        Write-Host '==============================================' -ForegroundColor DarkCyan
        Write-Host "Репозиторий: $Repo"
        Write-Host "Отчёты:      $(Join-Path $Repo 'reports\Git-sync')"
        Write-Host ''
        Write-Host '  1. Показать состояние локального репозитория, GitHub и VDS'
        Write-Host '  2. Получить изменения из GitHub'
        Write-Host '  3. Отправить изменения в GitHub'
        Write-Host '  4. Развернуть код из GitHub на VDS с резервной копией'
        Write-Host '  5. Скачать изменения VDS, создать коммит и отправить в GitHub'
        Write-Host '  6. Восстановить VDS из резервной копии (выбор по дате)'
        Write-Host '  7. Применить изменения на VDS и перезапустить службы'
        Write-Host '  8. Управление ветками fix/*, batell и economic'
        Write-Host '  9. Выход'
        Write-Host ''
        $choice = (Read-Host 'Выберите действие').Trim()
        $selected = switch ($choice) {
            '1' { 'status' }
            '2' { 'pull-github' }
            '3' { 'push-github' }
            '4' { 'deploy-vds' }
            '5' { 'pull-vds' }
            '6' { 'rollback-vds' }
            '7' { 'apply-vds' }
            '0' { '' }
            '8' { 'branches' }
            '9' { '' }
            default { Write-Host 'Неизвестный пункт меню.' -ForegroundColor Yellow; Read-Host 'Нажмите Enter для продолжения'; $null }
        }
        if ($selected) {
            $menuCommitMessage=''
            if($selected -in @('push-github','pull-vds')){
                $menuCommitMessage=(Read-Host 'Введите комментарий для коммита').Trim()
                if(-not $menuCommitMessage){Write-Host 'Комментарий коммита обязателен.' -ForegroundColor Yellow;Read-Host 'Нажмите Enter для продолжения';continue}
            }
            if ($selected -eq 'apply-vds') {
                & $PSCommandPath -Command $selected -Credentials $Credentials
            } elseif ($Branch) {
                & $PSCommandPath -Command $selected -Branch $Branch -Credentials $Credentials -CommitMessage $menuCommitMessage
            } else {
                & $PSCommandPath -Command $selected -Credentials $Credentials -CommitMessage $menuCommitMessage
            }
            Write-Host ''
            if ($LASTEXITCODE -eq 0) { Write-Host 'Операция завершена успешно.' -ForegroundColor Green } else { Write-Host 'Операция завершилась с ошибкой.' -ForegroundColor Red }
            Read-Host 'Нажмите Enter, чтобы вернуться в меню'
        }
    } while ($choice -notin @('0','9'))
}

try {
    if ($Command -eq 'menu') { Start-InteractiveMenu; exit 0 }
    if ($Command -eq 'help') {
        Write-Host @'
Русский интерфейс управления Rhisseth

Использование: .\rhisseth-sync.ps1 <команда> [параметры]

status                 показать состояние локального репозитория и GitHub
pull-github            получить изменения из GitHub безопасным способом
push-github            отправить локальные изменения в GitHub
compare                сравнить локальный код, GitHub и VDS
deploy-vds             развернуть подтверждённый код GitHub на VDS с backup
pull-vds               создать ветку/коммит состояния VDS и отправить в GitHub
rollback-vds           выбрать по дате и восстановить резервную копию VDS
apply-vds              перезапустить службы и проверить сайт
branches               создать/выбрать рабочую ветку и подготовить PR в main

Примеры:
  .\rhisseth-sync.ps1 status -Branch main
  .\rhisseth-sync.ps1 deploy-vds -Branch main
  .\rhisseth-sync.ps1 pull-vds -Branch main
  .\rhisseth-sync.ps1 rollback-vds
'@
        exit 0
    }

    if (-not $Branch) { $Branch = (git branch --show-current).Trim() }
    if (-not $Branch -and $Command -notin @('rollback-vds','apply-vds')) { throw 'Не удалось определить ветку. Укажите -Branch.' }

    switch ($Command) {
        'status' {
            Write-Header "Проверка состояния"
            git status --short --branch
            git fetch --prune origin
            $remote = "origin/$Branch"
            git show-ref --verify --quiet "refs/remotes/$remote"
            if ($LASTEXITCODE -eq 0) {
                Write-Host "Ветка: $Branch"
                Write-Host "Текущий локальный commit: $((git rev-parse --short $Branch).Trim())"
                Write-Host "Локальных коммитов впереди GitHub: $((git rev-list --count "$remote..$Branch").Trim())"
                Write-Host "Коммитов GitHub впереди локального: $((git rev-list --count "$Branch..$remote").Trim())"
            } else { Write-Host "Удалённая ветка $remote ещё не существует на GitHub." -ForegroundColor Yellow }
            Write-Host "Последний commit: $((git log -1 --pretty=format:'%h %s').Trim())"
            Write-Host "`n--- Состояние VDS и сравнение файлов ---" -ForegroundColor Cyan
            Invoke-Tool 'Compare-Deployment.ps1' @{ Credentials=$Credentials; Branch=$Branch }
            Write-Host "`nСводная проверка локального репозитория, GitHub и VDS завершена." -ForegroundColor Green
            Write-Report 'status' "Ветка: $Branch`n`nЛокальный commit: $((git log -1 --pretty=format:'%h %s').Trim())`n`nПроверка GitHub и VDS: выполнена"
        }
        'pull-github' { Write-Header "Получение изменений из GitHub"; Invoke-Tool 'Sync-FromGitHub.ps1' @{ Branch=$Branch }; Write-Host "Успешно: локальная ветка обновлена или уже актуальна." -ForegroundColor Green; Write-Report 'pull-github' "Результат: успешно`nВетка: $Branch" }
        'push-github' { Write-Header "Публикация в GitHub"; Invoke-Tool 'Publish-ToGitHub.ps1' @{ Branch=$Branch; CommitMessage=$CommitMessage }; Write-Host "Успешно: изменения опубликованы в GitHub." -ForegroundColor Green; Write-Report 'push-github' "Результат: успешно`nВетка: $Branch" }
        'compare' { Write-Header "Сравнение источников"; Invoke-Tool 'Compare-Deployment.ps1' @{ Credentials=$Credentials; Branch=$Branch }; Write-Host "Проверка сравнения завершена." -ForegroundColor Green; Write-Report 'compare' "Результат: проверка завершена`nВетка: $Branch" }
        'deploy-vds' {
            Write-Header "Публикация на тестовый VDS"
            $p=@{ Credentials=$Credentials; Branch=$Branch }; if($SkipBackup){$p.SkipBackup=$true}
            Invoke-Tool 'Publish-ToVds.ps1' $p; Write-Host "Успешно: код опубликован на VDS." -ForegroundColor Green; Write-Report 'deploy-vds' "Результат: успешно`nВетка: $Branch"
        }
        'pull-vds' {
            Write-Header "Получение состояния с VDS"
            $p=@{ Credentials=$Credentials; SourceBranch=$Branch; Push=$true; CommitMessage=$CommitMessage }
            Invoke-Tool 'Sync-FromVds.ps1' $p; Write-Host "Успешно: состояние VDS скачано." -ForegroundColor Green; Write-Report 'pull-vds' "Результат: успешно`nВетка: $Branch"
        }
        'rollback-vds' {
            Write-Header "Восстановление VDS"
            $p=@{ Credentials=$Credentials }; if($Backup){$p.Backup=$Backup}
            Invoke-Tool 'Rollback-Vds.ps1' $p; Write-Host "Успешно: VDS восстановлен из резервной копии." -ForegroundColor Green; Write-Report 'rollback-vds' "Результат: успешно`nРезервная копия: $Backup"
        }
        'apply-vds' {
            Write-Header "Применение изменений и проверка служб"
            Invoke-Tool 'Apply-Vds.ps1' @{ Credentials=$Credentials }
            Write-Host "Успешно: службы перезапущены, сайт проверен." -ForegroundColor Green
            Write-Report 'apply-vds' "Результат: успешно`nПроверены: rhisseth, nginx, /health"
        }
        'branches' {
            Write-Header "Управление ветками"
            Invoke-Tool 'Manage-Branches.ps1'
        }
    }
    exit 0
} catch { Write-Error $_; exit 1 }
