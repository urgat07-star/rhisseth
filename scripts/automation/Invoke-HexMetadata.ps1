# Release review 2026-09-18 (0.0.2): Run hex metadata inspection and deployment through pinned runner SSH with audit logs.
# Details: docs/releases/0.0.2-changes-2026-09-18.md.
#requires -Version 7.0
param([string]$ResourceId = '',
      [ValidateSet('Inspect-RhissethVpsFromRunner.py', 'Consolidate-RhissethRunnerFiles.py', 'Deploy-RhissethFromRunner.py', 'HexMetadataRunner.py', 'PlayerOnboardingRunner.py')]
      [string]$ScriptName = 'Inspect-RhissethVpsFromRunner.py',
      [ValidateSet('inspect', 'install', 'validate', 'hosting', 'snapshot', 'publish-map', 'audit-map', 'publish-preview', 'deploy', 'repair-assets')][string]$Operation = 'inspect')
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
    if ($ScriptName -eq 'HexMetadataRunner.py') {
        & scp.exe @opts "$root/scripts/automation/VerifyHexMetadata.py" 'avalon@10.210.52.128:/home/avalon/rhisseth.ru/scripts/automation/VerifyHexMetadata.py'
        if ($LASTEXITCODE -ne 0) { throw 'Verifier transfer failed' }
        & scp.exe @opts "$root/scripts/automation/HexMetadataVps.py" 'avalon@10.210.52.128:/home/avalon/rhisseth.ru/scripts/automation/HexMetadataVps.py'
        if ($LASTEXITCODE -ne 0) { throw 'VPS script transfer failed' }
        if ($Operation -eq 'deploy') {
            & scp.exe @opts "$root/temp/hex-metadata.tar" 'avalon@10.210.52.128:/home/avalon/rhisseth.ru/temp/hex-metadata.tar'
            if ($LASTEXITCODE -ne 0) { throw 'Package transfer failed' }
        }
    }
    if ($ScriptName -eq 'PlayerOnboardingRunner.py') {
        & scp.exe @opts "$root/scripts/automation/VerifyPlayerCabinet.py" 'avalon@10.210.52.128:/home/avalon/rhisseth.ru/scripts/automation/VerifyPlayerCabinet.py'
        if ($LASTEXITCODE -ne 0) { throw 'Cabinet integration verifier transfer failed' }
        & scp.exe @opts "$root/scripts/automation/PlayerOnboardingValidateVps.py" 'avalon@10.210.52.128:/home/avalon/rhisseth.ru/scripts/automation/PlayerOnboardingValidateVps.py'
        if ($LASTEXITCODE -ne 0) { throw 'Validation script transfer failed' }
        & scp.exe @opts "$root/scripts/automation/PlayerOnboardingVps.py" 'avalon@10.210.52.128:/home/avalon/rhisseth.ru/scripts/automation/PlayerOnboardingVps.py'
        if ($LASTEXITCODE -ne 0) { throw 'VPS deployment script transfer failed' }
        & ssh.exe @opts avalon@10.210.52.128 'mkdir -p /home/avalon/rhisseth.ru/temp && chmod 700 /home/avalon/rhisseth.ru/temp' 2>&1 | Add-Content -LiteralPath $log
        if ($LASTEXITCODE -ne 0) { throw 'Runner package directory preparation failed' }
        & scp.exe @opts "$root/temp/player-onboarding.tar" 'avalon@10.210.52.128:/home/avalon/rhisseth.ru/temp/player-onboarding.tar'
        if ($LASTEXITCODE -ne 0) { throw 'Player onboarding package transfer failed' }
    }
    if ($ScriptName -eq 'Deploy-RhissethFromRunner.py') {
        $payloadName = if ($Operation -eq 'publish-preview') { 'Publish-Hex70PreviewVps.py' } else { 'Deploy-RhissethVps.py' }
        $out = & scp.exe @opts "$root/scripts/automation/$payloadName" "avalon@10.210.52.128:/home/avalon/rhisseth.ru/scripts/automation/$payloadName" 2>&1
        if ($LASTEXITCODE -ne 0) { $out | Add-Content -LiteralPath $log; throw 'VPS payload transfer to runner failed' }
        if ($Operation -eq 'hosting') {
            $out = & ssh.exe @opts avalon@10.210.52.128 'mkdir -p /home/avalon/rhisseth.ru/temp && chmod 700 /home/avalon/rhisseth.ru/temp' 2>&1
            if ($LASTEXITCODE -ne 0) { throw 'Runner archive directory preparation failed' }
            $out = & scp.exe @opts "$root/temp/hosting-bkp.zip" "$root/temp/sql-bkp.zip" 'avalon@10.210.52.128:/home/avalon/rhisseth.ru/temp/' 2>&1
            if ($LASTEXITCODE -ne 0) { $out | Add-Content -LiteralPath $log; throw 'Archive transfer to runner failed' }
        }
    }
    $command = "python3 $remote"
    if ($ScriptName -eq 'PlayerOnboardingRunner.py' -and $Operation -in @('validate','repair-assets')) { $command += " $Operation" }
    if ($ResourceId) { $command += " $ResourceId" }
    if ($ScriptName -in @('Deploy-RhissethFromRunner.py','HexMetadataRunner.py')) { $command += " $Operation" }
    $out = & ssh.exe @opts avalon@10.210.52.128 $command 2>&1
    $code = $LASTEXITCODE
    if ($code -eq 0 -and $ScriptName -eq 'HexMetadataRunner.py') {
        & scp.exe @opts 'avalon@10.210.52.128:/home/avalon/rhisseth.ru/reports/hex-metadata-source.json' "$root/reports/hex-metadata-source.json"
        if ($LASTEXITCODE -ne 0) { throw 'Sanitized export retrieval failed' }
        New-Item -ItemType Directory -Force -Path "$root/reports/hex-metadata-live-files" | Out-Null
        & scp.exe -r @opts 'avalon@10.210.52.128:/home/avalon/rhisseth.ru/reports/hex-metadata-live-files/.' "$root/reports/hex-metadata-live-files"
        if ($LASTEXITCODE -ne 0) { throw 'Live frontend retrieval failed' }
    }
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

