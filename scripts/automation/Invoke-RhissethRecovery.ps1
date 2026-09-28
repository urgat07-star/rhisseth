# Release review 2026-09-18 (0.0.2): Control reviewed recovery operations through pinned runner SSH with audit logs.
# Details: docs/releases/0.0.2-changes-2026-09-18.md.
#requires -Version 7.0
param([ValidateSet('inventory','setup-storage','backup','test-access','schedule','list','inspect-start-zones','inspect-vds-backups','inspect-barony-dumps','inspect-barony-zones','validate-v03','diagnose-storage','preflight-test','restore-test','validate-test','reboot-test','verify-scripts','collect-evidence','run-scheduled','inspect-version','diagnose-memory','backup-summary','pin-target','finalize-test','progress-test','external-check','source-git-status','network-test','cleanup-test')][string]$Operation = 'inventory', [ValidatePattern('^(?:(?:release/)?v?\d+\.\d+\.\d+)?$')][string]$ApprovedRef = '')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$workspaceRoot = (Resolve-Path (Join-Path $root '..')).Path
$now = [DateTime]::UtcNow
$dir = Join-Path $root ('reports/automation-logs/' + $now.ToString('yyyy-MM-dd'))
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$log = Join-Path $dir ($now.ToString('yyyyMMdd-HHmmss') + '-recovery-control.md')
$targetDescription = if ($Operation -eq 'validate-v03') { 'Targets: runner script transfer; Rhisseth VDS 62.113.109.168; read-only production database backup and temporary restored database; Passbolt resource da44a388-e458-4379-ab4c-c204696804b2' } else { 'Targets: runner script transfer; read-only inventory of 62.113.109.168, 185.216.87.44, 10.210.52.56; Passbolt; GitHub urgat07-star/rhisseth' }
$changeDescription = if ($Operation -eq 'validate-v03') { 'Changes/reboot: backup file and temporary validation database on VDS; production database unchanged; no reboot' } else { 'Changes/reboot: script transfer only; target changes governed by selected operation; no reboot unless explicitly requested' }
@('# Rhisseth recovery control', '', "UTC: $($now.ToString('o'))", "Moscow: $([TimeZoneInfo]::ConvertTimeBySystemTimeZoneId($now,'Russian Standard Time').ToString('o'))", 'Task: backup-and-portable-deployment; Controller: Codex', 'Runner: STU-AUTOMATION-01 / 10.210.52.128', $targetDescription, $changeDescription) | Set-Content -LiteralPath $log -Encoding utf8
"Operation authorization: $Operation; approved target changes are limited to reviewed script actions; reboot requested=$($Operation -eq 'reboot-test')" | Add-Content -LiteralPath $log
$code = 1
try {
    $line = Get-Content -LiteralPath "$workspaceRoot/containers/compose/ansible-control/.env" | Where-Object { $_ -match '^AVALON_SSH_PRIVATE_KEY=' } | Select-Object -First 1
    if (-not $line) { throw 'Runner key reference missing' }
    $key = $line.Substring($line.IndexOf('=') + 1).Trim().Trim('"').Trim("'")
    $known = "$workspaceRoot/temp/stu-automation-01-known_hosts"
    $fp = & ssh-keygen.exe -lf $known 2>&1
    if ($LASTEXITCODE -ne 0 -or ($fp -join ' ') -notmatch 'SHA256:ChgM7wjz5n58p0QUUh2RNkebM8ZuP/fan\+eo\+n2iQyQ') { throw 'Runner fingerprint mismatch' }
    'Preflight: audit writable; reviewed script; runner SSH pinned' | Add-Content -LiteralPath $log
    $opts = @('-i', $key, '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o', 'StrictHostKeyChecking=yes', '-o', "UserKnownHostsFile=$known", '-o', 'ConnectTimeout=10')
    "Approved operation: $Operation; targets and changes governed by reviewed controller script" | Add-Content -LiteralPath $log
    if ($Operation -eq 'validate-v03') {
        & "$root/.local/hex-venv/Scripts/python.exe" "$root/scripts/automation/Build-RhissethV03MigrationArchive.py"
        if ($LASTEXITCODE -ne 0) { throw 'Migration archive build failed' }
        $archive = "$root/.local/batell-v03-migrations.tar.gz"
        & ssh.exe @opts avalon@10.210.52.128 'mkdir -p /home/avalon/rhisseth.ru/temp /home/avalon/rhisseth.ru/scripts/automation'
        if ($LASTEXITCODE -ne 0) { throw 'Runner staging directory preparation failed' }
        & scp.exe @opts $archive 'avalon@10.210.52.128:/home/avalon/rhisseth.ru/temp/batell-v03-migrations.tar.gz'
        if ($LASTEXITCODE -ne 0) { throw 'Migration archive transfer failed' }
        foreach ($name in @('Validate-RhissethV03FromRunner.py','Validate-RhissethV03Vps.py')) {
            & scp.exe @opts "$root/scripts/automation/$name" "avalon@10.210.52.128:/home/avalon/rhisseth.ru/scripts/automation/$name"
            if ($LASTEXITCODE -ne 0) { throw 'Reviewed validation script transfer failed' }
        }
        $out = & ssh.exe @opts avalon@10.210.52.128 'python3 /home/avalon/rhisseth.ru/scripts/automation/Validate-RhissethV03FromRunner.py' 2>&1
        $code = $LASTEXITCODE
        $out | Add-Content -LiteralPath $log -Encoding utf8
        $out | Write-Output
        "Target validation: VDS 62.113.109.168; read-only production backup and temporary database; exit_code=$code" | Add-Content -LiteralPath $log
        exit $code
    }
    $names = @('Inspect-RhissethRecoveryFromRunner.py','Inspect-RhissethStartZones.py','Inspect-RhissethVdsBackups.py','Run-RhissethRecovery.py','rhisseth_backup.py','rhisseth_storage.py','Bootstrap-RhissethStorage.py','rhisseth-backup.service','rhisseth-backup.timer','rhisseth_deploy.py','rhisseth_validate.py','Inspect-RhissethMemory.sh','Finalize-RhissethRecovery.py','Read-RhissethRecoveryProgress.py')
    foreach ($name in $names) {
        & scp.exe @opts "$root/scripts/automation/$name" "avalon@10.210.52.128:/home/avalon/rhisseth.ru/scripts/automation/$name"
        if ($LASTEXITCODE -ne 0) { throw 'Reviewed script transfer failed' }
    }
    & ssh.exe @opts avalon@10.210.52.128 'mkdir -p /home/avalon/rhisseth.ru/tests'
    if ($LASTEXITCODE -ne 0) { throw 'Runner tests directory preparation failed' }
    & scp.exe @opts "$root/tests/test_recovery_safety.py" 'avalon@10.210.52.128:/home/avalon/rhisseth.ru/tests/test_recovery_safety.py'
    if ($LASTEXITCODE -ne 0) { throw 'Safety checks transfer failed' }
    $remote = if ($Operation -eq 'inventory') { '/home/avalon/rhisseth.ru/scripts/automation/Inspect-RhissethRecoveryFromRunner.py' } elseif ($Operation -eq 'inspect-start-zones') { '/home/avalon/rhisseth.ru/scripts/automation/Inspect-RhissethStartZones.py' } elseif ($Operation -in @('inspect-vds-backups','inspect-barony-dumps','inspect-barony-zones')) { '/home/avalon/rhisseth.ru/scripts/automation/Inspect-RhissethVdsBackups.py' } else { '/home/avalon/rhisseth.ru/scripts/automation/Run-RhissethRecovery.py' }
    $command = "python3 $remote"
    if ($Operation -eq 'inspect-barony-dumps') { $command += ' --counts' }
    elseif ($Operation -eq 'inspect-barony-zones') { $command += ' --zones' }
    elseif ($Operation -ne 'inventory' -and $Operation -ne 'inspect-start-zones' -and $Operation -ne 'inspect-vds-backups') { $command += " $Operation" }
    if ($ApprovedRef) {
        if ($Operation -ne 'restore-test') { throw 'Explicit reference only applies to restoration' }
        "Explicit owner-selected reference: $ApprovedRef" | Add-Content -LiteralPath $log
        $command += " $ApprovedRef"
    }
    $out = & ssh.exe @opts avalon@10.210.52.128 $command 2>&1
    $code = $LASTEXITCODE
    $out | Add-Content -LiteralPath $log -Encoding utf8
    $out | Write-Output
} catch {
    "Failure: $($_.Exception.Message)" | Add-Content -LiteralPath $log
    Write-Output "Failure: $($_.Exception.Message)"
} finally {
    "Validation: exit_code=$code; operation=$Operation; changes detailed in runner log; reboot_requested=$($Operation -eq 'reboot-test')" | Add-Content -LiteralPath $log
    Write-Output "Audit log: $log"
}
exit $code

