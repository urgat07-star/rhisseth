[CmdletBinding()]
param([string]$Credentials = "$PSScriptRoot\vds-credentials.json")

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$cfg = Get-Content $Credentials -Raw | ConvertFrom-Json
Write-Host 'Подключение к VDS для интерактивного управления IP-списками...' -ForegroundColor Cyan
& ssh -tt -i $cfg.KeyPath "$($cfg.User)@$($cfg.Host)" 'if [ -x /usr/local/sbin/rhisseth-ip-sync ]; then sudo /usr/local/sbin/rhisseth-ip-sync; elif [ -x /opt/rhisseth/repository/deploy/native/rhisseth-ip-sync.sh ]; then sudo /opt/rhisseth/repository/deploy/native/rhisseth-ip-sync.sh; else echo "Rhisseth IP manager is not installed on VDS" >&2; exit 127; fi'
if ($LASTEXITCODE -ne 0) { throw "Удалённый скрипт завершился с кодом $LASTEXITCODE" }
