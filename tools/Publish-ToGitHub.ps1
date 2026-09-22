param([string]$Branch = "")

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
if (-not $Branch) { $Branch = (git branch --show-current).Trim() }
if (-not $Branch) { throw "Не удалось определить текущую ветку." }

git fetch --prune origin
$remoteRef = "origin/$Branch"
if (git show-ref --verify --quiet "refs/remotes/$remoteRef") {
    $behind = [int](git rev-list --count "$Branch..$remoteRef")
    if ($behind -gt 0) { throw "GitHub содержит $behind более новых коммит(а). Сначала запустите Sync-FromGitHub.ps1." }
}

$choice = Read-Host "Выберите действие: 1 - добавить релиз; 2 - отправить данные без релиза"
if ($choice -notin @("1", "2")) { throw "Допустимы только варианты 1 или 2." }

if ($choice -eq "1") {
    $previous = (git tag --list "v*" --sort=-version:refname | Select-Object -First 1)
    if (-not $previous) { $previous = "нет предыдущего релиза" }
    Write-Host "Предыдущий релиз: $previous"
    $release = Read-Host "Введите новый номер релиза (например, 0.0.3)"
    if ($release -notmatch '^v?\d+\.\d+\.\d+$') { throw "Номер релиза должен иметь формат 0.0.0." }
    $tag = if ($release.StartsWith("v")) { $release } else { "v$release" }
    if (git tag --list $tag) { throw "Релиз $tag уже существует." }
}

git add -A
if ((git diff --cached --quiet)) { Write-Host "Изменений для отправки нет."; exit 0 }
$message = Read-Host "Введите сообщение коммита"
if (-not $message) { $message = if ($choice -eq "1") { "Release $tag" } else { "Update project files" } }
git commit -m $message
git push --set-upstream origin $Branch
if ($choice -eq "1") { git tag -a $tag -m "Release $tag"; git push origin $tag }
Write-Host "Публикация завершена. Ветка: $Branch"
