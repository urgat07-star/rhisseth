# Release review 2026-09-18 (0.0.2): Transfer a reviewed player-onboarding package through the pinned runner.
# Details: docs/releases/0.0.2-changes-2026-09-18.md.
"""Transfer a reviewed player-onboarding package through the pinned runner."""
import datetime as dt
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from zoneinfo import ZoneInfo

RID = 'da44a388-e458-4379-ab4c-c204696804b2'
ROOT = Path.home() / 'rhisseth.ru'
now = dt.datetime.now(dt.timezone.utc)
directory = ROOT / 'reports/automation-logs' / now.strftime('%Y-%m-%d')
directory.mkdir(parents=True, exist_ok=True)
log = directory / f'{now:%Y%m%d-%H%M%S}-player-onboarding-runner.md'
log.write_text(f'# Player onboarding runner deployment\n\nUTC: {now.isoformat()}\nEurope/Moscow: {now.astimezone(ZoneInfo("Europe/Moscow")).isoformat()}\nTask: player-onboarding-release\nController: Codex\nRunner: STU-AUTOMATION-01 / 10.210.52.128\nTarget: 62.113.109.168 / rhisseth.ru\nAction: transfer reviewed package and execute reviewed VPS deployment\nPassbolt: {RID}\n', encoding='utf-8')

def emit(value):
    with log.open('a', encoding='utf-8') as stream:
        stream.write(str(value) + '\n')
    print(value, flush=True)

code = 1
try:
    if socket.gethostname().lower().split('.')[0] != 'stu-automation-01':
        raise RuntimeError('runner identity mismatch')
    package = ROOT / 'temp/player-onboarding.tar'
    script_name = 'PlayerOnboardingValidateVps.py' if sys.argv[1:] in (['validate'],['repair-assets']) else 'PlayerOnboardingVps.py'
    script = ROOT / 'scripts/automation' / script_name
    if not package.is_file() or not script.is_file():
        raise RuntimeError('reviewed files missing on runner')
    emit('Preflight: runner identity, audit path and reviewed package verified')
    phrase = Path('/etc/avalon-runner/passbolt/passphrase').read_text().rstrip('\r\n')
    env = os.environ.copy(); env['USERPASSWORD'] = phrase; env['userPassword'] = phrase
    result = subprocess.run(['passbolt', '--config', '/etc/avalon-runner/passbolt/passbolt-cli.yaml', 'get', 'resource', '--id', RID, '--json'], env=env, capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise RuntimeError('Passbolt retrieval failed')
    resource = json.loads(result.stdout)
    if resource.get('username') != 'root' or '62.113.109.168' not in resource.get('uri', ''):
        raise RuntimeError('Passbolt endpoint mismatch')
    ssh_env = os.environ.copy(); ssh_env['SSHPASS'] = resource['password'].rstrip('\r\n')
    options = ['-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','PreferredAuthentications=password,keyboard-interactive','-o','PubkeyAuthentication=no']
    def remote(args):
        return subprocess.run(['sshpass','-e',*args], env=ssh_env, capture_output=True, text=True, timeout=90)
    transfers = [(script, '/opt/rhisseth/scripts/automation/'+script_name)]
    if script_name == 'PlayerOnboardingVps.py':
        transfers.append((package, '/opt/rhisseth/temp/player-onboarding.tar'))
        transfers.append((ROOT/'scripts/automation/VerifyPlayerCabinet.py','/opt/rhisseth/scripts/automation/VerifyPlayerCabinet.py'))
    for source, target in transfers:
        result = remote(['scp',*options,str(source),'root@62.113.109.168:'+target])
        if result.returncode:
            raise RuntimeError('reviewed transfer failed')
    repair_arg = ' repair-assets' if sys.argv[1:] == ['repair-assets'] else ''
    process = subprocess.Popen(['sshpass','-e','ssh',*options,'root@62.113.109.168','/opt/rhisseth/venv/bin/python /opt/rhisseth/scripts/automation/'+script_name+repair_arg], env=ssh_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in process.stdout:
        emit(line.rstrip())
    code = process.wait()
    if code:
        raise RuntimeError('VPS deployment failed')
except Exception as error:
    code = 1
    emit('Failure: ' + type(error).__name__ + '; details suppressed')
finally:
    emit(f'Validation: exit_code={code}; reboot=false; VPS change status is recorded in remote log; log={log}')
sys.exit(code)
