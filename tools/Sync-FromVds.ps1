[CmdletBinding()]
param(
    [string]$Credentials = "$PSScriptRoot\vds-credentials.json",
    [string]$SourceBranch = 'main',
    [string]$ImportBranch = '',
    [switch]$Push
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
if (-not (Test-Path -LiteralPath $Credentials)) { throw "Не найден $Credentials" }
if ((git status --porcelain) -join '') { throw 'Есть локальные изменения. Сначала сохраните или отмените их.' }
$cfg = Get-Content -LiteralPath $Credentials -Raw | ConvertFrom-Json
if (-not (Test-Path -LiteralPath $cfg.KeyPath)) { throw "SSH-ключ не найден: $($cfg.KeyPath)" }
if ($cfg.RemotePath -notmatch '^/[A-Za-z0-9._/-]+$') { throw 'RemotePath содержит недопустимые символы.' }

$ssh = @('-i',$cfg.KeyPath,'-p',[string]$cfg.Port,'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes')
$scp = @('-i',$cfg.KeyPath,'-P',[string]$cfg.Port,'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes')
$target = "$($cfg.User)@$($cfg.Host)"
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
if (-not $ImportBranch) { $ImportBranch = "vds/import-$stamp" }
if ($ImportBranch -notmatch '^[A-Za-z0-9._/-]+$') { throw 'Недопустимое имя ветки импорта.' }
$originalBranch = (git branch --show-current).Trim()
if (-not $originalBranch) { throw 'Импорт нельзя запускать из detached HEAD.' }
$tmp = Join-Path ([IO.Path]::GetTempPath()) "rhisseth-vds-import-$stamp"
$remoteArchive = "/tmp/rhisseth-import-$stamp.tgz"
$remoteDbSql = "/tmp/rhisseth-editable-$stamp.sql"
$remoteDbJson = "/tmp/rhisseth-editable-$stamp.json"
New-Item -ItemType Directory -Path $tmp | Out-Null
$switched = $false

try {
    git fetch --prune origin
    if ($LASTEXITCODE) { throw 'Не удалось обновить сведения GitHub.' }
    git show-ref --verify --quiet "refs/remotes/origin/$SourceBranch"
    if ($LASTEXITCODE) { throw "Ветка origin/$SourceBranch не найдена." }
    git show-ref --verify --quiet "refs/heads/$ImportBranch"
    if (-not $LASTEXITCODE) { throw "Локальная ветка $ImportBranch уже существует." }
    git ls-remote --exit-code --heads origin $ImportBranch *> $null
    if (-not $LASTEXITCODE) { throw "Ветка origin/$ImportBranch уже существует." }

    $exclude = "--exclude=.git --exclude=.env --exclude=.env.* --exclude=secrets --exclude=deploy/secrets --exclude=reports --exclude=temp --exclude=backups --exclude=.local --exclude=.venv --exclude=__pycache__ --exclude='*.pyc'"
    & ssh @ssh $target "tar $exclude -czf '$remoteArchive' -C '$($cfg.RemotePath)' ."
    if ($LASTEXITCODE) { throw 'Не удалось создать безопасный снимок VDS.' }
    & scp @scp "$target`:$remoteArchive" (Join-Path $tmp 'vds.tgz')
    $downloadCode = $LASTEXITCODE
    & ssh @ssh $target "rm -f '$remoteArchive'" 2>$null
    if ($downloadCode) { throw 'Не удалось скачать снимок VDS.' }
    $snapshot = Join-Path $tmp 'vds'
    New-Item -ItemType Directory -Path $snapshot | Out-Null
    tar -xzf (Join-Path $tmp 'vds.tgz') -C $snapshot
    if ($LASTEXITCODE) { throw 'Не удалось распаковать снимок VDS.' }

    $dbSql=@'
SELECT jsonb_pretty(jsonb_build_object(
 'format',1,'exported_at',now(),
 'hexes',(SELECT COALESCE(jsonb_agg(jsonb_build_object('q',q,'r',r,'data',data) ORDER BY r,q),'[]') FROM hexes),
 'units',(SELECT COALESCE(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM (SELECT u.*,r.predecessor_unit_id,COALESCE((SELECT jsonb_object_agg(c.resource_code,c.quantity) FROM unit_resource_costs c WHERE c.unit_id=u.id),'{}') cost FROM unit_catalog u LEFT JOIN unit_upgrade_requirements r ON r.unit_id=u.id) x),
 'extractable_resources',(SELECT COALESCE(jsonb_agg(to_jsonb(x) ORDER BY code),'[]') FROM extractable_resources x),
 'produced_resources',(SELECT COALESCE(jsonb_agg(to_jsonb(x) ORDER BY code),'[]') FROM produced_resources x),
 'buildings',(SELECT COALESCE(jsonb_agg(to_jsonb(x) ORDER BY code),'[]') FROM additional_building_catalog x),
 'hex_buildings',(SELECT COALESCE(jsonb_agg(to_jsonb(x) ORDER BY r,q,building_code),'[]') FROM hex_additional_buildings x),
 'generals',(SELECT COALESCE(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM general_catalog x)
));
'@
    $localDbSql=Join-Path $tmp 'editable.sql';$dbSql|Set-Content $localDbSql -Encoding utf8NoBOM
    & scp @scp $localDbSql "$target`:$remoteDbSql";if($LASTEXITCODE){throw 'Не удалось передать запрос экспорта БД.'}
    & ssh @ssh $target "runuser -u postgres -- psql -X -At -d rhisseth -f '$remoteDbSql' > '$remoteDbJson'"
    if($LASTEXITCODE){throw 'Не удалось экспортировать редактируемые данные PostgreSQL.'}
    $snapshotDir=Join-Path $snapshot 'data\snapshots';New-Item -ItemType Directory -Force -Path $snapshotDir|Out-Null
    & scp @scp "$target`:$remoteDbJson" (Join-Path $snapshotDir 'editable-database.json')
    if($LASTEXITCODE){throw 'Не удалось скачать снимок редактируемой БД.'}
    $null=Get-Content (Join-Path $snapshotDir 'editable-database.json') -Raw|ConvertFrom-Json

    git switch -c $ImportBranch "origin/$SourceBranch"
    if ($LASTEXITCODE) { throw "Не удалось создать ветку $ImportBranch." }
    $switched = $true
    # Overlay preserves tracked local-only reports/tools excluded from VDS.
    Get-ChildItem -LiteralPath $snapshot -Force | Copy-Item -Destination $repo -Recurse -Force
    git add -A
    if ($LASTEXITCODE) { throw 'Не удалось подготовить изменения к коммиту.' }
    git diff --cached --quiet
    if (-not $LASTEXITCODE) {
        Write-Host 'VDS совпадает с GitHub: коммит и новая ветка не требуются.' -ForegroundColor Green
        git switch $originalBranch
        $switched = $false
        git branch -D $ImportBranch | Out-Host
        exit 0
    }

    $message = "Import VDS state $stamp"
    git commit -m $message
    if ($LASTEXITCODE) { throw 'Не удалось создать коммит состояния VDS.' }
    if ($Push) {
        git push --set-upstream origin $ImportBranch
        if ($LASTEXITCODE) { throw 'Коммит создан локально, но отправка в GitHub завершилась ошибкой.' }
    }
    Write-Host "Снимок VDS сохранён: $ImportBranch" -ForegroundColor Green
    Write-Host "Коммит: $((git rev-parse --short HEAD).Trim()) — $message"
    if ($Push) { Write-Host "Ветка опубликована в GitHub: origin/$ImportBranch" -ForegroundColor Green }
}
finally {
    & ssh @ssh $target "rm -f '$remoteArchive' '$remoteDbSql' '$remoteDbJson'" 2>$null
    if ($switched) {
        git switch $originalBranch 2>$null | Out-Host
        if (-not $LASTEXITCODE) { Write-Host "Возврат в исходную ветку: $originalBranch" }
    }
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
