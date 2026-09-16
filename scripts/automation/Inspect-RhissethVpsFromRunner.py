"""Read-only discovery; passwords remain inside the runner process."""
import datetime as dt
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

now = dt.datetime.now(dt.timezone.utc)
directory = Path.home() / 'rhisseth.ru/reports/automation-logs' / now.strftime('%Y-%m-%d')
directory.mkdir(parents=True, exist_ok=True)
log = directory / (now.strftime('%Y%m%d-%H%M%S') + '-rhisseth-vps.md')
log.write_text(f'# Rhisseth VPS discovery/check\n\n- UTC: {now.isoformat()}\n- Europe/Moscow: {now.astimezone(ZoneInfo("Europe/Moscow")).isoformat()}\n- Controller: Codex / N7198\n- Runner: STU-AUTOMATION-01 / 10.210.52.128\n- Action: read-only\n- Targets: Passbolt metadata matching rhisseth/elvizzz/VPS/VDS; explicitly selected VPS only\n- Change/reboot: no\n\n', encoding='utf-8')

def emit(text):
    with log.open('a', encoding='utf-8') as stream:
        stream.write(str(text) + '\n')
    print(text, flush=True)

def cli(args):
    env = os.environ.copy()
    phrase = Path('/etc/avalon-runner/passbolt/passphrase').read_text().rstrip('\r\n')
    env['USERPASSWORD'] = phrase
    env['userPassword'] = phrase
    result = subprocess.run(['passbolt', '--config', '/etc/avalon-runner/passbolt/passbolt-cli.yaml', *args], capture_output=True, text=True, env=env, timeout=45)
    if result.returncode:
        raise RuntimeError('Passbolt request failed; raw output suppressed')
    return json.loads(result.stdout)

def endpoint(uri):
    return urlsplit(uri if '://' in uri else 'ssh://' + uri)

code = 1
try:
    if socket.gethostname().lower().split('.')[0] != 'stu-automation-01':
        raise RuntimeError('Runner identity mismatch')
    emit('Preflight: runner identity verified; audit log writable')
    if len(sys.argv) == 1:
        rows = cli(['list', 'resource', '--column', 'id', '--column', 'name', '--column', 'username', '--column', 'uri', '--json'])
        for row in rows:
            if re.search(r'rhisseth|elvizzz|\bvps\b|\bvds\b', ' '.join(str(row.get(k, '')) for k in ('name', 'uri')), re.I):
                parsed = endpoint(row.get('uri') or '')
                emit(json.dumps({'id': row.get('id'), 'name': row.get('name'), 'username': row.get('username'), 'host': parsed.hostname, 'port': parsed.port, 'scheme': parsed.scheme}, ensure_ascii=False))
    else:
        rid = sys.argv[1]
        if not re.fullmatch(r'[a-fA-F0-9-]{36}', rid):
            raise RuntimeError('Invalid resource ID')
        resource = cli(['get', 'resource', '--id', rid, '--json'])
        parsed = endpoint(resource.get('uri') or '')
        host, port, user, password = parsed.hostname, parsed.port or 22, resource.get('username'), resource.get('password')
        if not host or not user or not isinstance(password, str) or not password:
            raise RuntimeError('Selected resource lacks SSH fields')
        if not re.fullmatch(r'[a-zA-Z0-9_.-]+', user) or host.startswith('-'):
            raise RuntimeError('Invalid SSH endpoint')
        emit(f'Approved target: {host}:{port}; Passbolt resource: {rid}')
        env = os.environ.copy()
        env['SSHPASS'] = password.rstrip('\r\n')
        remote = '''set -eu
printf 'hostname='; hostname
printf 'user='; id -un
printf 'cpus='; nproc
grep -E '^(NAME|VERSION_ID|PRETTY_NAME)=' /etc/os-release
free -m
df -h / /var
cat /proc/loadavg
swapon --show --noheadings --output TYPE,SIZE,USED
for unit in docker nginx apache2 caddy postgresql xray; do
printf '%s=' "$unit"
systemctl is-active "$unit" 2>/dev/null || true
done
'''
        emit('Host key policy: accept-new (TOFU); changed keys rejected; independent provider verification pending')
        result = subprocess.run(['sshpass', '-e', 'ssh', '-p', str(port), '-o', 'ConnectTimeout=12', '-o', 'StrictHostKeyChecking=accept-new', '-o', 'PreferredAuthentications=password,keyboard-interactive', '-o', 'PubkeyAuthentication=no', f'{user}@{host}', 'bash -s'], input=remote, env=env, capture_output=True, text=True, timeout=50)
        emit(result.stdout.replace(password, '<redacted>'))
        emit(result.stderr.replace(password, '<redacted>'))
        lookup = subprocess.run(['ssh-keygen', '-F', host if port == 22 else f'[{host}]:{port}'], capture_output=True, text=True)
        fingerprint = subprocess.run(['ssh-keygen', '-lf', '-'], input=lookup.stdout, capture_output=True, text=True)
        emit('Saved VPS host fingerprint: ' + fingerprint.stdout.strip())
        if result.returncode:
            raise RuntimeError(f'SSH check failed with exit code {result.returncode}')
    code = 0
except Exception as error:
    emit(f'Failure: {type(error).__name__}: {error}')
finally:
    emit(f'Validation: exit_code={code}; change=false; reboot=false; secrets_logged=false')
    emit(f'Runner audit log: {log}')
sys.exit(code)
