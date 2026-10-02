#requires -Version 7.0
[CmdletBinding()]
param([ValidateSet('StageAndVerify','DownloadAndVerify','Cleanup','Maintenance')][string]$Operation='StageAndVerify',[ValidatePattern('^\d{8}T\d{6}Z$')][string]$Stage='')
$ErrorActionPreference='Stop'; $project=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path; $workspace=(Resolve-Path (Join-Path $project '..')).Path
$line=Get-Content -LiteralPath "$workspace/containers/compose/ansible-control/.env"|Where-Object{$_-match'^AVALON_SSH_PRIVATE_KEY='}|Select-Object -First 1
if(-not $line){throw'Runner key reference missing'}; $key=$line.Substring($line.IndexOf('=')+1).Trim().Trim('"').Trim("'"); $known="$workspace/temp/stu-automation-01-known_hosts"
$opts=@('-i',$key,'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','-o',"UserKnownHostsFile=$known",'-o','ConnectTimeout=10')
& scp.exe @opts (Join-Path $PSScriptRoot 'Migrate-RhissethBackups.py') 'avalon@10.210.52.128:/home/avalon/rhisseth.ru/scripts/automation/Migrate-RhissethBackups.py'; if($LASTEXITCODE-ne 0){throw'Runner script transfer failed'}
if($Operation-in@('StageAndVerify','DownloadAndVerify')){
 if($Operation-eq'StageAndVerify'){$raw=& ssh.exe @opts avalon@10.210.52.128 'python3 /home/avalon/rhisseth.ru/scripts/automation/Migrate-RhissethBackups.py stage'; if($LASTEXITCODE-ne 0){throw"Runner stage failed: $($raw-join' ')"}; $jsonLine=@($raw|Where-Object{$_-match'^\s*\{'})[-1]; $result=$jsonLine|ConvertFrom-Json; $Stage=$result.stage}
 elseif(-not$Stage){throw'Stage required for DownloadAndVerify'}
 $local=Join-Path $project "backups/$Stage"; New-Item -ItemType Directory -Force -Path $local|Out-Null
 & scp.exe -r @opts "avalon@10.210.52.128:/home/avalon/rhisseth.ru/temp/backup-migration/$Stage/." $local; if($LASTEXITCODE-ne 0){throw'Runner-to-workstation transfer failed'}
 $manifest=Get-Content -Raw -LiteralPath (Join-Path $local 'manifest.json')|ConvertFrom-Json; $verified=0
 foreach($item in $manifest.files){$path=Join-Path $local ($item.relative-replace'/',[IO.Path]::DirectorySeparatorChar); if(-not(Test-Path -LiteralPath $path -PathType Leaf)){throw"Missing: $($item.relative)"}; if((Get-Item -LiteralPath $path).Length-ne[long]$item.bytes){throw"Size mismatch: $($item.relative)"}; if((Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()-ne$item.sha256){throw"SHA mismatch: $($item.relative)"}; $verified++}
 $marker=@{stage=$Stage;verified_files=$verified;verified_utc=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json; $markerPath=Join-Path $local 'verified.json'; Set-Content -LiteralPath $markerPath -Value $marker -Encoding utf8NoBOM
 & scp.exe @opts $markerPath "avalon@10.210.52.128:/home/avalon/rhisseth.ru/temp/backup-migration/$Stage/verified.json"; if($LASTEXITCODE-ne 0){throw'Verified marker transfer failed'}
 [pscustomobject]@{Stage=$Stage;Selected=$manifest.selected.Count;VerifiedFiles=$verified;LocalPath=$local;CleanupReady=$true}|ConvertTo-Json
}elseif($Operation-eq'Cleanup'){if(-not$Stage){throw'Stage required'}; & ssh.exe @opts avalon@10.210.52.128 "python3 /home/avalon/rhisseth.ru/scripts/automation/Migrate-RhissethBackups.py cleanup $Stage"; if($LASTEXITCODE-ne 0){throw'Cleanup failed'}}
else{& ssh.exe @opts avalon@10.210.52.128 'python3 /home/avalon/rhisseth.ru/scripts/automation/Migrate-RhissethBackups.py maintenance'; if($LASTEXITCODE-ne 0){throw'Maintenance failed'}}
