param([string]$Credentials = "$PSScriptRoot\vds-credentials.json")
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot; Set-Location $repo
if (-not (Test-Path $Credentials)) { throw "Не найден файл учётных данных: $Credentials. Скопируйте vds-credentials.example.json в vds-credentials.json." }
$cfg = Get-Content $Credentials -Raw | ConvertFrom-Json
if (-not (Test-Path $cfg.KeyPath)) { throw "SSH-ключ не найден: $($cfg.KeyPath)" }
$ssh = @('-i',$cfg.KeyPath,'-p',[string]$cfg.Port,'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes')
$scp = @('-i',$cfg.KeyPath,'-P',[string]$cfg.Port,'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes')
$target = "$($cfg.User)@$($cfg.Host)"
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$tmp = Join-Path ([IO.Path]::GetTempPath()) "rhisseth-vds-$stamp"
New-Item -ItemType Directory -Path $tmp | Out-Null
$remoteArchive = "/tmp/rhisseth-vds-$stamp.tgz"
try {
    & ssh @ssh $target "tar --exclude=.git -czf '$remoteArchive' -C '$($cfg.RemotePath)' ."
    if ($LASTEXITCODE -ne 0) { throw "Не удалось создать снимок проекта на VDS." }
    & scp @scp "$target`:$remoteArchive" (Join-Path $tmp 'remote.tgz')
    if ($LASTEXITCODE -ne 0) { throw "Не удалось скачать снимок VDS." }
    $remote = Join-Path $tmp 'remote'; New-Item -ItemType Directory $remote | Out-Null
    tar -xzf (Join-Path $tmp 'remote.tgz') -C $remote
    $baseline = Join-Path $tmp 'baseline'; New-Item -ItemType Directory $baseline | Out-Null
    $baselineArchive = Join-Path $tmp 'baseline.tgz'
    git archive --format=tar.gz --output=$baselineArchive HEAD
    if ($LASTEXITCODE -ne 0) { throw "Не удалось создать локальный снимок Git." }
    tar -xzf $baselineArchive -C $baseline
    $diff = Join-Path $tmp 'diff'
    $null = git diff --no-index -- $baseline $remote 2>&1 | Set-Content $diff
    if ($LASTEXITCODE -eq 0) { Write-Host "Изменений на VDS не обнаружено."; exit 0 }
    git switch elvizzz 2>$null; if ($LASTEXITCODE -ne 0) { git switch -c elvizzz }
    Copy-Item (Join-Path $remote '*') $repo -Recurse -Force
    git add -A
    git commit -m "Import manual VDS changes $stamp" 2>$null
    Write-Host "Изменения VDS сохранены в ветке elvizzz. Проверьте git diff main..elvizzz."
} finally {
    & ssh @ssh $target "rm -f '$remoteArchive'" 2>$null
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
