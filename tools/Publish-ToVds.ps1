param([string]$Credentials = "$PSScriptRoot\vds-credentials.json", [string]$Branch = "")
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot; Set-Location $repo
if (-not (Test-Path $Credentials)) { throw "Не найден файл учётных данных: $Credentials" }
$cfg = Get-Content $Credentials -Raw | ConvertFrom-Json
if (-not (Test-Path $cfg.KeyPath)) { throw "SSH-ключ не найден: $($cfg.KeyPath)" }
if (-not $Branch) { $Branch = (git branch --show-current).Trim() }
if (-not $Branch) { throw "Не удалось определить ветку." }
if ((git status --porcelain) -join "") { throw "Есть незакоммиченные изменения." }
$ok = Read-Host "Загрузить ветку $Branch на VDS $($cfg.Host)? Введите YES"
if ($ok -cne 'YES') { throw "Публикация отменена." }
$ssh = @('-i',$cfg.KeyPath,'-p',[string]$cfg.Port,'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes')
$target = "$($cfg.User)@$($cfg.Host)"; $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$archive = Join-Path ([IO.Path]::GetTempPath()) "rhisseth-$stamp.tgz"
try {
    git archive --format=tar.gz --output=$archive $Branch
    Get-Content -LiteralPath $archive -AsByteStream | & ssh @ssh $target "mkdir -p '$($cfg.RemotePath)' && tar -xzf - -C '$($cfg.RemotePath)'"
    if ($LASTEXITCODE -ne 0) { throw "Загрузка на VDS завершилась ошибкой." }
    Write-Host "Ветка $Branch загружена на VDS."
} finally { Remove-Item $archive -Force -ErrorAction SilentlyContinue }
