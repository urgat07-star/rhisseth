param(
    [string]$Branch = ""
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

if (-not (Test-Path (Join-Path $repo ".git"))) { throw "Репозиторий не найден: $repo" }
if ((git status --porcelain) -join "") { throw "Есть локальные изменения. Сначала сохраните или закоммитьте их." }

if (-not $Branch) { $Branch = (git branch --show-current).Trim() }
if (-not $Branch) { throw "Не удалось определить текущую ветку." }

git fetch --prune origin
$remoteRef = "origin/$Branch"
git show-ref --verify --quiet "refs/remotes/$remoteRef"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Удалённая ветка $remoteRef ещё не создана на GitHub."
    Write-Host "Для первой публикации запустите: .\tools\Publish-ToGitHub.ps1"
    exit 0
}

$ahead = [int](git rev-list --count "$remoteRef..$Branch")
$behind = [int](git rev-list --count "$Branch..$remoteRef")
if ($ahead -gt 0 -and $behind -gt 0) { throw "Ветки разошлись: локальных коммитов $ahead, удалённых $behind." }
if ($behind -gt 0) {
    git pull --ff-only origin $Branch
    Write-Host "Локальная копия обновлена из GitHub: $Branch"
} elseif ($ahead -gt 0) {
    Write-Host "Локальная ветка новее GitHub; загрузка не выполняется. Используйте второй скрипт."
} else {
    Write-Host "Версии полностью совпадают: $Branch"
}
