# Release review 2026-09-18 (0.0.2): Pinned runner to selected VPS; Passbolt credentials never leave this process.
# Details: docs/releases/0.0.2-changes-2026-09-18.md.
"""Pinned runner to selected VPS; Passbolt credentials never leave this process."""
import datetime as dt
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from zoneinfo import ZoneInfo

rid = 'da44a388-e458-4379-ab4c-c204696804b2'
if len(sys.argv) != 3 or sys.argv[1] != rid or sys.argv[2] not in ('inspect', 'deploy'):
    raise SystemExit('Invalid approved operation')
operation = sys.argv[2]
now = dt.datetime.now(dt.timezone.utc)
root = Path.home() / 'rhisseth.ru'
directory = root / 'reports/automation-logs' / now.strftime('%Y-%m-%d')
directory.mkdir(parents=True, exist_ok=True)
log = directory / (now.strftime('%Y%m%d-%H%M%S') + '-vps-' + operation + '.md')
log.write_text(f'# VPS {operation}\n\n- UTC: {now.isoformat()}\n- Europe/Moscow: {now.astimezone(ZoneInfo("Europe/Moscow")).isoformat()}\n- Controller: N7198 / Codex\n- Runner: STU-AUTOMATION-01 / 10.210.52.128\n- Targets: VPS 62.113.109.168:22; rhisseth.ru HTTP/HTTPS; GitHub urgat07-star/rhisseth\n- Action: {operation}\n- Passbolt resource: {rid}\n\n', encoding='utf-8')
def emit(text):
    with log.open('a', encoding='utf-8') as stream:
        stream.write(str(text) + '\n')
    print(text, flush=True)
code = 1
try:
    if socket.gethostname().lower().split('.')[0] != 'stu-automation-01':
        raise RuntimeError('Runner identity mismatch')
    emit('Preflight: runner identity verified; audit logging writable; VPS host key pinned from prior operation')
    if (root/'temp/sql-bkp.zip').exists():
        (root/'temp').chmod(0o700)
        for name in ('hosting-bkp.zip','sql-bkp.zip'):
            (root/'temp'/name).chmod(0o600)
        emit('Runner archive permissions verified: private directory and owner-only files')
    env = os.environ.copy()
    phrase = Path('/etc/avalon-runner/passbolt/passphrase').read_text().rstrip('\r\n')
    env['USERPASSWORD'] = phrase
    env['userPassword'] = phrase
    result = subprocess.run(['passbolt', '--config', '/etc/avalon-runner/passbolt/passbolt-cli.yaml', 'get', 'resource', '--id', rid, '--json'], env=env, capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise RuntimeError('Passbolt retrieval failed; raw output suppressed')
    resource = json.loads(result.stdout)
    if resource.get('username') != 'root' or '62.113.109.168' not in resource.get('uri', ''):
        raise RuntimeError('Passbolt endpoint mismatch')
    password = resource['password'].rstrip('\r\n')
    ssh_env = os.environ.copy()
    ssh_env['SSHPASS'] = password
    options = ['-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=12', '-o', 'PreferredAuthentications=password,keyboard-interactive', '-o', 'PubkeyAuthentication=no']
    def ssh(args):
        return subprocess.run(['sshpass', '-e', *args], env=ssh_env, capture_output=True, text=True, timeout=60)
    result = ssh(['ssh', *options, 'root@62.113.109.168', 'mkdir -p /opt/rhisseth/scripts/automation /opt/rhisseth/reports/automation-logs'])
    if result.returncode:
        raise RuntimeError('VPS project directory preparation failed')
    payload_name = 'UserAdminVps.py'
    result = ssh(['scp', *options, str(Path(__file__).with_name(payload_name)), 'root@62.113.109.168:/opt/rhisseth/scripts/automation/' + payload_name])
    if result.returncode:
        raise RuntimeError('Reviewed VPS script transfer failed')
    result = ssh(['scp', *options, str(Path(__file__).with_name('VerifyUserAdmin.py')), 'root@62.113.109.168:/opt/rhisseth/scripts/automation/VerifyUserAdmin.py'])
    if result.returncode:raise RuntimeError('Integration verifier transfer failed')
    if operation == 'hosting':
        (root/'temp').chmod(0o700)
        for name in ('hosting-bkp.zip','sql-bkp.zip'):
            (root/'temp'/name).chmod(0o600)
        result = ssh(['ssh', *options, 'root@62.113.109.168', 'mkdir -p /opt/rhisseth/temp && chmod 700 /opt/rhisseth/temp'])
        if result.returncode:
            raise RuntimeError('VPS archive directory preparation failed')
        result = ssh(['scp', *options, str(root / 'temp/hosting-bkp.zip'),str(root / 'temp/sql-bkp.zip'),'root@62.113.109.168:/opt/rhisseth/temp/'])
        if result.returncode:
            raise RuntimeError('Reviewed hosting archives transfer failed')
    if operation == 'deploy':
        result = ssh(['scp', *options, str(root / 'temp/user-admin.tar'), 'root@62.113.109.168:/opt/rhisseth/temp/user-admin.tar'])
        if result.returncode: raise RuntimeError('Package transfer failed')
    interpreter = '/opt/rhisseth/venv/bin/python'
    process = subprocess.Popen(['sshpass', '-e', 'ssh', *options, 'root@62.113.109.168', f'{interpreter} /opt/rhisseth/scripts/automation/{payload_name} {operation}'], env=ssh_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in process.stdout:
        emit(line.rstrip().replace(password, '<redacted>'))
    code = process.wait()
    if code == 0:
        (root / 'reports/user-admin-live-files').mkdir(exist_ok=True)
        result = ssh(['scp', '-r', *options, 'root@62.113.109.168:/opt/rhisseth/reports/user-admin-live-files/.', str(root / 'reports/user-admin-live-files')])
        if result.returncode: raise RuntimeError('Live frontend retrieval failed')
        result = ssh(['scp', *options, 'root@62.113.109.168:/opt/rhisseth/reports/user-admin-source.json', str(root / 'reports/user-admin-source.json')])
        if result.returncode: raise RuntimeError('Sanitized export retrieval failed')
    if code == 0 and operation in ('install', 'validate', 'hosting', 'snapshot'):
        certificate = root / '.local/vps-test-tls.crt'
        certificate.parent.mkdir(parents=True, exist_ok=True)
        result = ssh(['scp', *options, 'root@62.113.109.168:/opt/rhisseth/secrets/tls.crt', str(certificate)])
        if result.returncode:
            raise RuntimeError('Public certificate retrieval failed')
        emit('External validation: TLS certificate trusted from pinned SSH transport')
        endpoints = [('http://62.113.109.168/', '301'), ('https://62.113.109.168/health', '401')]
        if operation in ('hosting','snapshot'):
            endpoints.append(('https://62.113.109.168/index.php','200'))
        for url, expected in endpoints:
            result = subprocess.run(['curl', '--max-time', '20', '--cacert', str(certificate), '-sS', '-o', '/dev/null', '-w', '%{http_code}', url], capture_output=True, text=True)
            emit(f'External endpoint: {url}; status={result.stdout}; exit_code={result.returncode}')
            if result.returncode or result.stdout != expected:
                code = 1
                raise RuntimeError('External nginx/TLS/access validation failed')
except Exception as error:
    code = 1
    emit(f'Failure: {type(error).__name__}: {error}')
finally:
    emit(f'Validation: exit_code={code}; operation={operation}; reboot=false; VPS change details above')
    emit(f'Runner audit log: {log}')
sys.exit(code)

