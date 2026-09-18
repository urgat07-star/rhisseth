# Release review 2026-09-18 (0.0.2): Read-only inventory on approved runner; never print resource secrets.
# Details: docs/releases/0.0.2-changes-2026-09-18.md.
"""Read-only inventory on approved runner; never print resource secrets."""
import datetime as dt
import json
import os
from pathlib import Path
import socket
import subprocess
import urllib.request
from zoneinfo import ZoneInfo

os.umask(0o077)
now = dt.datetime.now(dt.timezone.utc)
directory = Path.home() / 'rhisseth.ru/reports/automation-logs' / now.strftime('%Y-%m-%d')
directory.mkdir(parents=True, exist_ok=True)
log = directory / (now.strftime('%Y%m%d-%H%M%S') + '-recovery-inventory.md')
log.write_text(f'# Rhisseth recovery inventory\n\nUTC: {now.isoformat()}\n\nMoscow: {now.astimezone(ZoneInfo("Europe/Moscow")).isoformat()}\n\nTask: backup-and-portable-deployment; controller: Codex\n\nRunner: STU-AUTOMATION-01 / 10.210.52.128\n\nTargets: 62.113.109.168, 185.216.87.44, 10.210.52.56, Passbolt metadata for these addresses, GitHub urgat07-star/rhisseth\n\nAction: read-only inventory; changes/reboot: none\n', encoding='utf-8')
def emit(value):
    with log.open('a', encoding='utf-8') as stream:
        stream.write(str(value) + '\n')
    print(value, flush=True)
def cli(args):
    env = os.environ.copy()
    phrase = Path('/etc/avalon-runner/passbolt/passphrase').read_text().rstrip('\r\n')
    env.update(USERPASSWORD=phrase, userPassword=phrase)
    p = subprocess.run(['passbolt', '--config', '/etc/avalon-runner/passbolt/passbolt-cli.yaml', *args], env=env, capture_output=True, text=True, timeout=60)
    if p.returncode:
        raise RuntimeError('Passbolt request failed; details suppressed')
    return json.loads(p.stdout)
code = 1
try:
    if socket.gethostname().lower().split('.')[0] != 'stu-automation-01':
        raise RuntimeError('Runner identity mismatch')
    emit('Preflight: runner identity and writable audit log verified')
    rows = cli(['list', 'resource', '--column', 'id', '--column', 'name', '--column', 'username', '--column', 'uri', '--json'])
    for host in ('62.113.109.168', '185.216.87.44', '10.210.52.56'):
        matches = [r for r in rows if host in (r.get('uri') or '')]
        emit(f'Target {host}: matching resources={len(matches)}')
        for row in matches:
            emit(json.dumps({k: row.get(k) for k in ('id', 'name', 'username')}, ensure_ascii=False))
        if len(matches) != 1:
            continue
        resource = cli(['get', 'resource', '--id', matches[0]['id'], '--json'])
        password = resource.get('password', '').rstrip('\r\n')
        user = resource.get('username')
        if not password or not user or not all(c.isalnum() or c in '_.-' for c in user):
            emit('SSH credentials unsuitable; no connection attempted')
            continue
        script = '''set -eu
hostname
id -un
grep -E '^(NAME|VERSION_ID)=' /etc/os-release
uname -m
nproc
free -m
df -B1 /
sudo -n true 2>/dev/null && printf 'sudo_noninteractive=yes\\n' || true
ss -lnt
for unit in nginx apache2 caddy postgresql postgresql@16-main rhisseth; do systemctl is-active "$unit" 2>/dev/null || true; done
dpkg-query -W -f='${Package} ${Version}\\n' git nginx postgresql-16 python3-venv certbot 2>/dev/null || true
'''
        if host == '62.113.109.168':
            script += '''
git -C /opt/rhisseth/repository rev-parse HEAD
git -C /opt/rhisseth/repository status --porcelain
du -sm /opt/rhisseth/* 2>/dev/null
find /opt/rhisseth -maxdepth 2 -type d
runuser -u postgres -- psql -X -At -d rhisseth -c "SELECT name FROM schema_migrations ORDER BY name"
runuser -u postgres -- psql -X -At -d rhisseth -c "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
runuser -u postgres -- psql -X -At -d rhisseth -c "SELECT pg_database_size(current_database())"
getent ahostsv4 rhisseth.ru || true
'''
        env = {**os.environ, 'SSHPASS': password}
        lookup = subprocess.run(['ssh-keygen', '-F', host], capture_output=True, text=True)
        # First contact is inventory only; pin recorded TOFU key for subsequent operations.
        policy = 'yes' if lookup.returncode == 0 else 'accept-new'
        emit(f'Host key policy: {policy}; first-contact TOFU if new; changed keys rejected')
        p = subprocess.run(['sshpass', '-e', 'ssh', '-o', f'StrictHostKeyChecking={policy}', '-o', 'ConnectTimeout=12', '-o', 'PubkeyAuthentication=no', f'{user}@{host}', 'bash -s'], input=script, capture_output=True, text=True, env=env, timeout=80)
        emit((p.stdout + p.stderr).replace(password, '<redacted>'))
        emit(f'Target {host}: exit_code={p.returncode}')
        lookup = subprocess.run(['ssh-keygen', '-F', host], capture_output=True, text=True)
        fingerprint = subprocess.run(['ssh-keygen', '-lf', '-'], input=lookup.stdout, capture_output=True, text=True)
        emit('Saved fingerprint: ' + fingerprint.stdout.strip())
    request = urllib.request.Request('https://api.github.com/repos/urgat07-star/rhisseth/releases', headers={'User-Agent':'rhisseth-recovery'})
    with urllib.request.urlopen(request, timeout=30) as response:
        releases = json.load(response)
    emit('Published stable releases: ' + json.dumps([{'tag':r['tag_name'],'author':r['author']['login'],'published_at':r['published_at']} for r in releases if not r['draft'] and not r['prerelease']]))
    code = 0
except Exception as error:
    emit('Failure: ' + type(error).__name__ + '; sensitive exception details suppressed')
finally:
    emit(f'Validation: exit_code={code}; inventory only; change=false; reboot=false')
    emit(f'Runner audit log: {log}')
raise SystemExit(code)
