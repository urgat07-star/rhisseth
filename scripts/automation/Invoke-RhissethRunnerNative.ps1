#requires -Version 7.0
param([string]$ResourceId = '',
      [ValidateSet('Inspect-RhissethVpsFromRunner.py', 'Consolidate-RhissethRunnerFiles.py', 'Deploy-RhissethFromRunner.py', 'Publish-RhissethFromRunner.py', 'Diagnose-RhissethVps.py', 'Diagnose-RhissethRunner.py', 'Configure-RhissethSharedAuthFromRunner.py')]
      [string]$ScriptName = 'Inspect-RhissethVpsFromRunner.py',
      [ValidateSet('inspect', 'install', 'validate', 'hosting', 'snapshot', 'publish-map', 'audit-map', 'deploy-hexes', 'publish', 'publish-v03', 'publish-v031', 'publish-v032', 'publish-v033', 'apply')][string]$Operation = 'inspect')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
$workspaceRoot = (Resolve-Path -LiteralPath (Join-Path $root '..')).Path
$now = [DateTime]::UtcNow
$dir = Join-Path $root ('reports/automation-logs/' + $now.ToString('yyyy-MM-dd'))
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$log = Join-Path $dir ($now.ToString('yyyyMMdd-HHmmss') + '-rhisseth-runner-native.md')
@('# Rhisseth runner control operation', '', "- UTC: $($now.ToString('o'))", "- Europe/Moscow: $([TimeZoneInfo]::ConvertTimeBySystemTimeZoneId($now,'Russian Standard Time').ToString('o'))", "- Controller: $env:COMPUTERNAME / Codex", '- Runner: STU-AUTOMATION-01 / 10.210.52.128', '- Targets: runner project artifacts; selected VPS 62.113.109.168; project GitHub; Passbolt resource only', "- Passbolt resource: $ResourceId", "- Script: $ScriptName", '- Action: pinned SSH control, reviewed script transfer and execution', "- Operation: $Operation", '- Change/reboot: exact VPS changes recorded by remote operation; no reboot requested', '') | Set-Content -LiteralPath $log -Encoding utf8
$code = 1
try {
    if ($ResourceId -and $ResourceId -notmatch '^[a-fA-F0-9-]{36}$') { throw 'Invalid resource ID' }
    $line = Get-Content -LiteralPath "$workspaceRoot/containers/compose/ansible-control/.env" | Where-Object { $_ -match '^AVALON_SSH_PRIVATE_KEY=' } | Select-Object -First 1
    if (-not $line) { throw 'Runner key reference missing' }
    $key = $line.Substring($line.IndexOf('=') + 1).Trim().Trim('"').Trim("'")
    $known = "$workspaceRoot/temp/stu-automation-01-known_hosts"
    $fingerprint = & ssh-keygen.exe -lf $known 2>&1
    if ($LASTEXITCODE -ne 0 -or ($fingerprint -join ' ') -notmatch 'SHA256:ChgM7wjz5n58p0QUUh2RNkebM8ZuP/fan\+eo\+n2iQyQ') { throw 'Runner pinned fingerprint not confirmed' }
    'Preflight: reviewed script; pinned ED25519 fingerprint confirmed; audit log writable' | Add-Content -LiteralPath $log
    $opts = @('-i', $key, '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o', 'StrictHostKeyChecking=yes', '-o', "UserKnownHostsFile=$known", '-o', 'ConnectTimeout=10')
    $remote = '/home/avalon/rhisseth.ru/scripts/automation/' + $ScriptName
    $out = & ssh.exe @opts avalon@10.210.52.128 'mkdir -p /home/avalon/rhisseth.ru/scripts/automation' 2>&1
    if ($LASTEXITCODE -ne 0) { $out | Add-Content -LiteralPath $log; throw 'Runner project directory preparation failed' }
    $out = & scp.exe @opts "$root/scripts/automation/$ScriptName" "avalon@10.210.52.128:$remote" 2>&1
    if ($LASTEXITCODE -ne 0) { $out | Add-Content -LiteralPath $log; throw 'Runner transfer failed' }
    if ($ScriptName -eq 'Deploy-RhissethFromRunner.py') {
        $out = & scp.exe @opts "$root/scripts/automation/Deploy-RhissethVps.py" 'avalon@10.210.52.128:/home/avalon/rhisseth.ru/scripts/automation/Deploy-RhissethVps.py' 2>&1
        if ($LASTEXITCODE -ne 0) { $out | Add-Content -LiteralPath $log; throw 'VPS payload transfer to runner failed' }
        if ($Operation -eq 'hosting') {
            $out = & ssh.exe @opts avalon@10.210.52.128 'mkdir -p /home/avalon/rhisseth.ru/temp && chmod 700 /home/avalon/rhisseth.ru/temp' 2>&1
            if ($LASTEXITCODE -ne 0) { throw 'Runner archive directory preparation failed' }
            $out = & scp.exe @opts "$root/temp/hosting-bkp.zip" "$root/temp/sql-bkp.zip" 'avalon@10.210.52.128:/home/avalon/rhisseth.ru/temp/' 2>&1
            if ($LASTEXITCODE -ne 0) { $out | Add-Content -LiteralPath $log; throw 'Archive transfer to runner failed' }
        }
    }
    if ($ScriptName -eq 'Publish-RhissethFromRunner.py') {
        $payloadName = if ($Operation -eq 'publish-v03') { 'Publish-BatellV03Vps.py' } elseif ($Operation -eq 'publish-v031') { 'Publish-BatellV031Vps.py' } elseif ($Operation -eq 'publish-v032') { 'Publish-BatellV032Vps.py' } elseif ($Operation -eq 'publish-v033') { 'Publish-BatellV033Vps.py' } else { 'Publish-RhissethVps.py' }
        $out = & scp.exe @opts "$root/scripts/automation/$payloadName" "avalon@10.210.52.128:/home/avalon/rhisseth.ru/scripts/automation/$payloadName" 2>&1
        if ($LASTEXITCODE -ne 0) { $out | Add-Content -LiteralPath $log; throw 'VPS publication payload transfer failed' }
    }
    if ($ScriptName -eq 'Diagnose-RhissethVps.py') {
        $out = & scp.exe @opts "$root/scripts/automation/Diagnose-RhissethVps.py" 'avalon@10.210.52.128:/home/avalon/rhisseth.ru/scripts/automation/Diagnose-RhissethVps.py' 2>&1
        if ($LASTEXITCODE -ne 0) { $out | Add-Content -LiteralPath $log; throw 'VPS diagnostic script transfer failed' }
    }
    if ($ScriptName -eq 'Diagnose-RhissethRunner.py') {
        $out = & scp.exe @opts "$root/scripts/automation/Diagnose-RhissethRunner.py" 'avalon@10.210.52.128:/home/avalon/rhisseth.ru/scripts/automation/Diagnose-RhissethRunner.py' 2>&1
        if ($LASTEXITCODE -ne 0) { $out | Add-Content -LiteralPath $log; throw 'Runner diagnostic script transfer failed' }
    }
    if ($ScriptName -eq 'Configure-RhissethSharedAuthFromRunner.py') {
        $out = & scp.exe @opts "$root/scripts/automation/Configure-RhissethSharedAuthVps.py" 'avalon@10.210.52.128:/home/avalon/rhisseth.ru/scripts/automation/Configure-RhissethSharedAuthVps.py' 2>&1
        if ($LASTEXITCODE -ne 0) { $out | Add-Content -LiteralPath $log; throw 'Shared-auth VDS payload transfer failed' }
        if ($Operation -eq 'apply') {
            $out = & ssh.exe @opts avalon@10.210.52.128 'mkdir -p /home/avalon/rhisseth.ru/temp && chmod 700 /home/avalon/rhisseth.ru/temp' 2>&1
            if ($LASTEXITCODE -ne 0) { throw 'Runner temporary directory preparation failed' }
            $out = & scp.exe @opts "$root/app/backend/admin_users.py" 'avalon@10.210.52.128:/home/avalon/rhisseth.ru/temp/admin_users.py' 2>&1
            if ($LASTEXITCODE -ne 0) { $out | Add-Content -LiteralPath $log; throw 'Shared-auth application guard transfer failed' }
        }
    }
    if ($ScriptName -eq 'Publish-RhissethFromRunner.py') {
        $archive = Join-Path $env:TEMP ('rhisseth-publish-' + $now.ToString('yyyyMMdd-HHmmss') + '.tgz')
        $archiveRef = if ($Operation -eq 'publish-v031') { 'v0.3.1' } elseif ($Operation -eq 'publish-v032') { 'v0.3.2' } elseif ($Operation -eq 'publish-v033') { 'v0.3.3' } else { 'HEAD' }
        $archiveCommit = (git -C $root rev-list -n 1 $archiveRef).Trim()
        if ($LASTEXITCODE -ne 0 -or -not $archiveCommit) { throw 'Publication archive ref missing' }
        "Archive ref: $archiveRef; commit: $archiveCommit" | Add-Content -LiteralPath $log
        git -C $root archive --format=tar.gz --output=$archive $archiveRef
        if ($LASTEXITCODE -ne 0) { throw 'Local Git archive creation failed' }
        $out = & scp.exe @opts $archive 'avalon@10.210.52.128:/home/avalon/rhisseth.ru/temp/rhisseth-publish.tgz' 2>&1
        Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue
        if ($LASTEXITCODE -ne 0) { $out | Add-Content -LiteralPath $log; throw 'Publication archive transfer failed' }
    }
    $command = "python3 $remote"
    if ($ResourceId) { $command += " $ResourceId" }
    if ($ScriptName -eq 'Deploy-RhissethFromRunner.py' -or $ScriptName -eq 'Publish-RhissethFromRunner.py' -or $ScriptName -eq 'Diagnose-RhissethVps.py' -or $ScriptName -eq 'Diagnose-RhissethRunner.py' -or $ScriptName -eq 'Configure-RhissethSharedAuthFromRunner.py') { $command += " $Operation" }
    $out = & ssh.exe @opts avalon@10.210.52.128 $command 2>&1
    $code = $LASTEXITCODE
    $safe = ($out | ForEach-Object { [string]$_ }) -join "`n"
    $safe = $safe -replace '(?i)(password|passphrase|token|cookie|authorization)\s*[:=]\s*\S+', '$1=<redacted>'
    $safe | Add-Content -LiteralPath $log -Encoding utf8
    Write-Output $safe
} catch {
    "Failure: $($_.Exception.Message)" | Add-Content -LiteralPath $log
    Write-Output "Failure: $($_.Exception.Message)"
} finally {
    "Validation: exit_code=$code; operation=$Operation; change/reboot status in sanitized remote output" | Add-Content -LiteralPath $log
    Write-Output "Audit log: $log"
}
exit $code
