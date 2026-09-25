"""Reviewed Passbolt-backed publication of the current checked-out release archive."""
import datetime as dt, json, os, socket, subprocess, sys
from pathlib import Path
from zoneinfo import ZoneInfo

RID = 'da44a388-e458-4379-ab4c-c204696804b2'
if len(sys.argv) != 3 or sys.argv[1] != RID or sys.argv[2] not in ('publish','publish-v03','publish-v031','publish-v032'): raise SystemExit('Invalid operation')
now = dt.datetime.now(dt.timezone.utc)
root = Path.home() / 'rhisseth.ru'
archive = root / 'temp/rhisseth-publish.tgz'
logdir = root / 'reports/automation-logs' / now.strftime('%Y-%m-%d')
logdir.mkdir(parents=True, exist_ok=True)
log = logdir / (now.strftime('%Y%m%d-%H%M%S') + '-vps-publish.md')
log.write_text(f'# Rhisseth VDS publication\n\n- UTC: {now.isoformat()}\n- Europe/Moscow: {now.astimezone(ZoneInfo("Europe/Moscow")).isoformat()}\n- Controller: Codex\n- Runner: STU-AUTOMATION-01 / 10.210.52.128\n- Target: VPS 62.113.109.168\n- Action: publish reviewed archive\n- Passbolt resource: {RID}\n\n', encoding='utf-8')
def emit(value):
    with log.open('a', encoding='utf-8') as stream: stream.write(str(value) + '\n')
    print(value, flush=True)
def main():
    if socket.gethostname().lower().split('.')[0] != 'stu-automation-01': raise RuntimeError('Runner identity mismatch')
    if not archive.is_file() or archive.stat().st_size == 0: raise RuntimeError('Publication archive missing')
    phrase = Path('/etc/avalon-runner/passbolt/passphrase').read_text().rstrip('\r\n')
    env = {**os.environ, 'USERPASSWORD': phrase, 'userPassword': phrase}
    result = subprocess.run(['passbolt', '--config', '/etc/avalon-runner/passbolt/passbolt-cli.yaml', 'get', 'resource', '--id', RID, '--json'], env=env, capture_output=True, text=True, timeout=45)
    if result.returncode: raise RuntimeError('Passbolt retrieval failed')
    resource = json.loads(result.stdout)
    if resource.get('username') != 'root' or '62.113.109.168' not in resource.get('uri', ''): raise RuntimeError('Passbolt endpoint mismatch')
    sshenv = {**os.environ, 'SSHPASS': resource['password'].rstrip('\r\n')}
    options = ['-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=12', '-o', 'PreferredAuthentications=password,keyboard-interactive', '-o', 'PubkeyAuthentication=no']
    def ssh(args): return subprocess.run(['sshpass', '-e', *args], env=sshenv, capture_output=True, text=True, timeout=180)
    result = ssh(['scp', *options, str(archive), 'root@62.113.109.168:/opt/rhisseth/temp/rhisseth-publish.tgz'])
    if result.returncode: raise RuntimeError('Archive upload failed')
    name = {'publish-v03':'Publish-BatellV03Vps.py','publish-v031':'Publish-BatellV031Vps.py','publish-v032':'Publish-BatellV032Vps.py'}.get(sys.argv[2], 'Publish-RhissethVps.py')
    payload = Path(__file__).with_name(name)
    result = ssh(['scp', *options, str(payload), 'root@62.113.109.168:/opt/rhisseth/scripts/automation/'+name])
    if result.returncode: raise RuntimeError('Reviewed VDS payload upload failed')
    interpreter = '/opt/rhisseth/venv/bin/python' if sys.argv[2] in ('publish-v03','publish-v031','publish-v032') else 'python3'
    result = ssh(['ssh', *options, 'root@62.113.109.168', interpreter+' /opt/rhisseth/scripts/automation/'+name+' '+sys.argv[2]])
    emit((result.stdout + '\n' + result.stderr).replace(resource['password'], '<redacted>').strip())
    emit('Exit code: ' + str(result.returncode))
    if result.returncode: raise RuntimeError('VDS publication failed')
try:
    emit('Preflight: runner identity, archive and Passbolt endpoint verified; reboot=false')
    main(); code = 0
except Exception as error:
    emit(f'Failure: {type(error).__name__}: {error}'); code = 1
finally:
    emit(f'Validation: exit_code={locals().get("code", 1)}; reboot=false; secrets_logged=false')
sys.exit(code)
