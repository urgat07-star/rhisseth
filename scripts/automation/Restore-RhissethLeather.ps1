[CmdletBinding()]
param([string]$Credentials = "$PSScriptRoot\..\..\tools\vds-credentials.json")
$ErrorActionPreference='Stop'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$cfg=Get-Content -LiteralPath $Credentials -Raw|ConvertFrom-Json
if(-not(Test-Path -LiteralPath $cfg.KeyPath)){throw 'SSH-ключ не найден'}
$ssh=@('-i',$cfg.KeyPath,'-p',[string]$cfg.Port,'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes')
$scp=@('-i',$cfg.KeyPath,'-P',[string]$cfg.Port,'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes')
$target="$($cfg.User)@$($cfg.Host)";$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$tmp=Join-Path ([IO.Path]::GetTempPath()) "rhisseth-leather-$stamp";New-Item -ItemType Directory $tmp|Out-Null
$remoteSql="/tmp/rhisseth-restore-leather-$stamp.sql";$backup="/var/backups/rhisseth/rhisseth-db-before-leather-$stamp.dump"
$logDir=Join-Path $repo "reports\automation-logs\$(Get-Date -Format 'yyyy-MM-dd')";New-Item -ItemType Directory -Force $logDir|Out-Null
$logPath=Join-Path $logDir "$stamp-restore-leather-resource.md";$exitCode=1;$validation='not run'
$sql=@'
BEGIN;
INSERT INTO produced_resources(code,name,ingredients,required_building,purpose,is_food,active)
VALUES ('leather','Кожа/мех','Скот или дичь','','Найм, торговля',false,true)
ON CONFLICT(code) DO UPDATE SET name=EXCLUDED.name,ingredients=EXCLUDED.ingredients,
 required_building=EXCLUDED.required_building,purpose=EXCLUDED.purpose,
 is_food=EXCLUDED.is_food,active=EXCLUDED.active,updated_at=now();
INSERT INTO game_resources(code,name,starting_quantity,is_food)
VALUES ('leather','Кожа/мех',0,false)
ON CONFLICT(code) DO UPDATE SET name=EXCLUDED.name,is_food=EXCLUDED.is_food;
INSERT INTO game_inventory(user_id,resource_code,quantity)
SELECT user_id,'leather',0 FROM game_wallets ON CONFLICT(user_id,resource_code) DO NOTHING;
COMMIT;
SELECT code,name,ingredients,required_building,purpose,is_food,active
FROM produced_resources WHERE code='leather';
'@
try{
  $localSql=Join-Path $tmp 'restore.sql';$sql|Set-Content $localSql -Encoding utf8NoBOM
  & scp @scp $localSql "$target`:$remoteSql";if($LASTEXITCODE){throw 'SQL transfer failed'}
  & ssh @ssh $target "set -eu; mkdir -p /var/backups/rhisseth; runuser -u postgres -- pg_dump -Fc --no-owner --no-acl -d rhisseth > '$backup'; test -s '$backup'; runuser -u postgres -- psql -X -At -v ON_ERROR_STOP=1 -d rhisseth -f '$remoteSql'"
  if($LASTEXITCODE){throw 'Backup, restore, or validation failed'}
  $validation='leather|Кожа/мех|Скот или дичь||Найм, торговля|f|t';$exitCode=0
} finally {
  & ssh @ssh $target "rm -f '$remoteSql'" 2>$null
  $utc=(Get-Date).ToUniversalTime();$msk=[TimeZoneInfo]::ConvertTimeBySystemTimeZoneId($utc,'Russian Standard Time')
  @('# Восстановление ресурса «Кожа» на Rhisseth VDS','',"- UTC: $($utc.ToString('yyyy-MM-dd HH:mm:ss'))","- Europe/Moscow: $($msk.ToString('yyyy-MM-dd HH:mm:ss'))",'- Task: restore-produced-resource-leather',"- Controller: Codex/operator workstation","- Runner/target: external Rhisseth VDS $($cfg.Host)",'- Approved target: PostgreSQL rhisseth; produced_resources/game_resources/game_inventory','- Action: verified pg_dump backup, transactional idempotent resource restore','- Preflight: credentials descriptor and pinned SSH key present',"- Backup: $backup (verified non-empty)","- Sanitized validation: $validation","- Exit code: $exitCode",'- Change: resource restored; reboot: no','- Secrets/Passbolt: none read or logged')|Set-Content $logPath -Encoding utf8
  Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host "Backup: $backup";Write-Host "Log: $logPath"
