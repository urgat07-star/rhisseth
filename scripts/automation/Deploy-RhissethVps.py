"""Reviewed first deployment; native PostgreSQL/systemd using existing nginx."""
import datetime as dt
import os
import base64
import csv
import hashlib
import json
from pathlib import Path
import re
import secrets
import shutil
import ssl
import subprocess
import sys
import time
import urllib.request
import urllib.error
from zoneinfo import ZoneInfo

ROOT = Path('/opt/rhisseth')
os.umask(0o077)
operation = sys.argv[1]
now = dt.datetime.now(dt.timezone.utc)
directory = ROOT / 'reports/automation-logs' / now.strftime('%Y-%m-%d')
directory.mkdir(parents=True, exist_ok=True)
log = directory / (now.strftime('%Y%m%d-%H%M%S') + '-' + operation + '.md')
log.write_text(f'# Rhisseth VPS {operation}\n\n- UTC: {now.isoformat()}\n- Europe/Moscow: {now.astimezone(ZoneInfo("Europe/Moscow")).isoformat()}\n- Controller: N7198 / Codex via STU-AUTOMATION-01 10.210.52.128\n- Target: rhisseth 62.113.109.168\n- Action: {operation}\n- Passbolt resource: da44a388-e458-4379-ab4c-c204696804b2 (SSH only)\n\n', encoding='utf-8')
def emit(text):
    with log.open('a', encoding='utf-8') as stream:
        stream.write(str(text) + '\n')
    print(text, flush=True)
def run(args, *, check=True, input=None, env=None, raw=False):
    emit('Command: ' + ' '.join(args))
    result = subprocess.run(args, input=input, env=env, capture_output=True, text=True)
    if not raw:
        emit(result.stdout.strip())
        emit(result.stderr.strip())
    emit('Exit code: ' + str(result.returncode))
    if check and result.returncode:
        raise RuntimeError('Command failed: ' + args[0])
    return result
def inspect():
    run(['hostname'])
    run(['free', '-m'])
    run(['df', '-h', '/'])
    run(['ss', '-lnt'])
    run(['nginx', '-t'])
    run(['systemctl', 'status', 'postgresql@16-main', '--no-pager'], check=False)
    run(['journalctl', '-u', 'postgresql@16-main', '-n', '15', '--no-pager'], check=False)
    config = run(['nginx', '-T'], raw=True).stdout
    for line in config.splitlines():
        if re.match(r'^# configuration file|^\s*(listen|server_name|root|ssl_certificate|include)\s', line):
            emit(line)
    run(['dpkg-query', '-W', '-f=${Package} ${Version}\n', 'git', 'postgresql', 'python3-venv', 'certbot'], check=False)
    run(['getent', 'ahostsv4', 'rhisseth.ru'], check=False)
    run(['git', 'ls-remote', 'https://github.com/urgat07-star/rhisseth.git', 'refs/heads/main'], env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
    run(['curl', '--max-time', '15', '-sS', '-o', '/dev/null', '-w', 'HTTP %{http_code}\n', '-H', 'Host: rhisseth.ru', 'http://127.0.0.1/'], check=False)
    run(['curl', '--max-time', '15', '-sS', '-o', '/dev/null', '-w', 'HTTPS %{http_code}\n', 'https://rhisseth.ru/'], check=False)

def sql(statement, *, secret=False):
    return run(['runuser', '-u', 'postgres', '--', 'psql', '-X', '-v', 'ON_ERROR_STOP=1', '-At'], input=statement, raw=secret).stdout.strip()

def install():
    emit('Change: package installation, isolated database, systemd API, nginx test virtual host; no reboot')
    if shutil.disk_usage('/').free < 2 * 1024**3:
        raise RuntimeError('Less than 2 GB free disk')
    repo = ROOT / 'repository'
    env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0'}
    if not repo.exists():
        run(['git', 'clone', 'https://github.com/urgat07-star/rhisseth.git', str(repo)], env=env)
    else:
        if run(['git', '-C', str(repo), 'status', '--porcelain'], raw=True).stdout.strip():
            raise RuntimeError('VPS repository has local changes; update refused')
        run(['git', '-C', str(repo), 'fetch', 'origin', 'main'], env=env)
        run(['git', '-C', str(repo), 'merge', '--ff-only', 'origin/main'])
    revision = run(['git', '-C', str(repo), 'rev-parse', 'HEAD']).stdout.strip()
    native = repo / 'deploy/native'
    if not (native / 'rhisseth.service').is_file():
        raise RuntimeError('Native deployment templates missing from Git release')
    backup = ROOT / 'backups' / now.strftime('%Y%m%d-%H%M%S')
    backup.mkdir(parents=True, exist_ok=True)
    backup.chmod(0o700)
    shutil.copytree('/etc/nginx', backup / 'nginx', dirs_exist_ok=True, symlinks=True)
    emit('Backup: original nginx configuration saved inside project')
    apt_env = {**os.environ, 'DEBIAN_FRONTEND': 'noninteractive', 'NEEDRESTART_MODE': 'l'}
    run(['apt-get', 'update'], env=apt_env)
    run(['apt-get', 'install', '-y', '--no-install-recommends', 'postgresql', 'python3-venv', 'apache2-utils', 'openssl', 'ca-certificates'], env=apt_env)
    if not run(['id', 'rhisseth'], check=False, raw=True).returncode == 0:
        run(['useradd', '--system', '--home-dir', str(ROOT), '--shell', '/usr/sbin/nologin', 'rhisseth'])
    secret_dir = ROOT / 'secrets'
    secret_dir.mkdir(exist_ok=True)
    secret_dir.chmod(0o711)
    password_file = secret_dir / 'db-password.txt'
    if not password_file.exists():
        password_file.write_text(secrets.token_urlsafe(36) + '\n')
    password_file.chmod(0o640)
    shutil.chown(password_file, user='root', group='rhisseth')
    password = password_file.read_text().strip()
    pg_config = Path('/etc/postgresql/16/main/conf.d/rhisseth.conf')
    if pg_config.exists():
        pg_config.chmod(0o644)
    run(['systemctl', 'enable', '--now', 'postgresql'])
    run(['systemctl', 'start', 'postgresql@16-main'])
    if sql("SELECT count(*) FROM pg_roles WHERE rolname='rhisseth';") == '0':
        sql('CREATE ROLE rhisseth LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD ' + "'" + password.replace("'", "''") + "';", secret=True)
    if sql("SELECT count(*) FROM pg_database WHERE datname='rhisseth';") == '0':
        sql('CREATE DATABASE rhisseth OWNER rhisseth;')
    version = sql('SHOW server_version;')
    emit('Database role permissions: ' + sql("SELECT rolname,rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname='rhisseth';"))
    if not version.startswith('16.'):
        raise RuntimeError('Expected Ubuntu PostgreSQL 16 for native test deployment')
    shutil.copy2(native / 'postgresql-test.conf', '/etc/postgresql/16/main/conf.d/rhisseth.conf')
    pg_config.chmod(0o644)
    run(['systemctl', 'restart', 'postgresql@16-main'])
    venv = ROOT / 'venv'
    if not (venv / 'bin/python').is_file():
        run(['python3', '-m', 'venv', str(venv)])
    run([str(venv / 'bin/pip'), 'install', '--disable-pip-version-check', '--no-cache-dir', '-r', str(repo / 'app/backend/requirements.lock')])
    # Code/runtime are non-secret and must be readable by the service user.
    # Secret and backup directories retain their separate restrictive modes.
    for tree in (repo, venv):
        for parent, directories, files in os.walk(tree):
            Path(parent).chmod(0o755)
            for name in files:
                file = Path(parent) / name
                if not file.is_symlink():
                    file.chmod(0o755 if file.stat().st_mode & 0o111 else 0o644)
    run(['runuser', '-u', 'rhisseth', '--', str(venv / 'bin/python'), '-c', 'import fastapi, psycopg; print("Service-user runtime access verified")'])
    app_env = {**os.environ, 'DB_HOST': '127.0.0.1', 'DB_PASSWORD_FILE': str(password_file)}
    run([str(venv / 'bin/python'), str(repo / 'app/backend/migrate.py')], env=app_env)
    count = run(['runuser', '-u', 'postgres', '--', 'psql', '-X', '-At', '-d', 'rhisseth', '-c', 'SELECT count(*) FROM hexes']).stdout.strip()
    if count == '0':
        run([str(venv / 'bin/python'), str(repo / 'app/backend/import_csv.py'), str(repo / 'data/import/hex-initial-parameters.csv')], env=app_env)
    else:
        emit('Existing map preserved: initial CSV import skipped')
    env_file = secret_dir / 'app.env'
    env_file.write_text('DB_HOST=127.0.0.1\nDB_PASSWORD_FILE=/opt/rhisseth/secrets/db-password.txt\n')
    env_file.chmod(0o600)
    web_password = secret_dir / 'web-password.txt'
    if not web_password.exists():
        web_password.write_text(secrets.token_urlsafe(24) + '\n')
    web_password.chmod(0o600)
    run(['htpasswd', '-iBc', str(secret_dir / 'web.htpasswd'), 'mapadmin'], input=web_password.read_text(), raw=True)
    (secret_dir / 'web.htpasswd').chmod(0o640)
    shutil.chown(secret_dir / 'web.htpasswd', user='root', group='www-data')
    if not (secret_dir / 'tls.crt').exists():
        run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '30', '-keyout', str(secret_dir / 'tls.key'), '-out', str(secret_dir / 'tls.crt'), '-subj', '/CN=62.113.109.168', '-addext', 'subjectAltName=IP:62.113.109.168,DNS:rhisseth.ru'], raw=True)
    (secret_dir / 'tls.key').chmod(0o600)
    shutil.copy2(native / 'rhisseth.service', '/etc/systemd/system/rhisseth.service')
    Path('/etc/systemd/system/rhisseth.service').chmod(0o644)
    shutil.copy2(native / 'nginx-logrotate.conf', '/etc/logrotate.d/rhisseth')
    run(['systemctl', 'daemon-reload'])
    run(['systemctl', 'enable', '--now', 'rhisseth'])
    run(['systemctl', 'restart', 'rhisseth'])
    for attempt in range(20):
        try:
            if urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3).status == 200:
                break
        except Exception:
            time.sleep(1)
    else:
        raise RuntimeError('API startup health failed')
    site = Path('/etc/nginx/sites-available/rhisseth')
    old_site = site.read_bytes() if site.exists() else None
    enabled = Path('/etc/nginx/sites-enabled/rhisseth')
    site.write_bytes((native / 'nginx.conf').read_bytes())
    if not enabled.exists():
        enabled.symlink_to(site)
    test = run(['nginx', '-t'], check=False)
    if test.returncode:
        if old_site is None:
            enabled.unlink(missing_ok=True)
            site.unlink(missing_ok=True)
        else:
            site.write_bytes(old_site)
        raise RuntimeError('nginx test failed; project vhost restored')
    run(['systemctl', 'reload', 'nginx'])
    (ROOT / 'release.json').write_text(json.dumps({'git_commit': revision, 'postgresql': version, 'deployed_utc': now.isoformat()}, indent=2))
    emit('Web access: HTTPS IP, username mapadmin; password retained in root-only /opt/rhisseth/secrets/web-password.txt (not logged)')
    validate()

def validate():
    context = ssl.create_default_context(cafile=str(ROOT / 'secrets/tls.crt'))
    password = (ROOT / 'secrets/web-password.txt').read_text().strip()
    auth = 'Basic ' + base64.b64encode(('mapadmin:' + password).encode()).decode()
    def request(path, payload=None, authorized=True):
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
        headers = {'Content-Type': 'application/json'}
        if authorized:
            headers['Authorization'] = auth
        req = urllib.request.Request('https://62.113.109.168' + path, data=data, headers=headers, method='GET' if data is None else 'PUT')
        try:
            with urllib.request.urlopen(req, context=context, timeout=15) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()
    for unit in ('postgresql@16-main', 'rhisseth', 'nginx'):
        run(['systemctl', 'is-active', unit])
    assert request('/health', authorized=False)[0] == 401
    assert request('/health')[0] == 200
    for path in ('/interactive-map/', '/interactive-map/app.js', '/interactive-map/styles.css', '/interactive-map/terrain-map-final-v2.png'):
        assert request(path)[0] == 200
    assert request('/data/import/hex-initial-parameters.csv')[0] == 404
    status, data = request('/api/hexes')
    assert status == 200
    rows = json.loads(data)
    with (ROOT / 'repository/data/import/hex-initial-parameters.csv').open(encoding='utf-8-sig', newline='') as stream:
        source = list(csv.DictReader(stream, delimiter=';'))
    assert {(r['Q'], r['R']): r for r in source} == {(r['Q'], r['R']): r for r in rows}
    emit(f'Validation: all {len(rows)} imported rows match every original CSV field')
    row = next(row for row in rows if row['Категория'] != 'Вне полотна')
    endpoint = f'/api/hexes/{row["Q"]}/{row["R"]}'
    original = row['Комментарий']
    marker = 'Rhisseth deployment persistence check ' + now.isoformat()
    try:
        assert request(endpoint, {'Защита': '99'})[0] == 400
        assert request('/api/hexes/99999/99999', {'Комментарий': ''})[0] == 404
        assert request(endpoint, {'Комментарий': marker})[0] == 200
        run(['systemctl', 'restart', 'rhisseth'])
        run(['systemctl', 'restart', 'postgresql@16-main'])
        for attempt in range(20):
            try:
                if request('/health')[0] == 200:
                    break
            except Exception:
                pass
            time.sleep(1)
        updated = json.loads(request('/api/hexes')[1])
        assert next(r for r in updated if (r['Q'], r['R']) == (row['Q'], row['R']))['Комментарий'] == marker
        emit('Validation: API edit persists after application and PostgreSQL restart')
    finally:
        assert request(endpoint, {'Комментарий': original})[0] == 200
        emit('Validation: temporary test edit restored')
    backups = ROOT / 'backups'
    backups.mkdir(exist_ok=True)
    backups.chmod(0o700)
    dump = backups / (now.strftime('%Y%m%d-%H%M%S') + '-rhisseth.dump')
    emit('Command: pg_dump rhisseth custom format to project backup (peer authentication)')
    with dump.open('wb') as stream:
        result = subprocess.run(['runuser', '-u', 'postgres', '--', 'pg_dump', '-d', 'rhisseth', '-Fc'], stdout=stream, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError('Backup failed; output suppressed')
    emit('Backup SHA256: ' + hashlib.sha256(dump.read_bytes()).hexdigest())
    restored_db = 'rhisseth_restore_' + secrets.token_hex(4)
    run(['runuser', '-u', 'postgres', '--', 'createdb', restored_db])
    try:
        emit('Command: pg_restore project backup into fresh isolated verification database')
        with dump.open('rb') as stream:
            restored = subprocess.run(['runuser', '-u', 'postgres', '--', 'pg_restore', '-d', restored_db, '--no-owner', '--no-acl', '--exit-on-error', '--single-transaction'], stdin=stream, capture_output=True)
        emit('Restore exit code: ' + str(restored.returncode))
        if restored.returncode:
            raise RuntimeError('Isolated backup restore failed')
        checksum_sql = "SELECT count(*), md5(string_agg(data::text, '' ORDER BY r,q)) FROM hexes"
        checksums = []
        for db in ('rhisseth', restored_db):
            checksums.append(run(['runuser', '-u', 'postgres', '--', 'psql', '-X', '-At', '-d', db, '-c', checksum_sql]).stdout.strip())
        assert checksums[0] == checksums[1]
        emit('Validation: backup restored in isolated database; all hex data checksums match')
    finally:
        run(['runuser', '-u', 'postgres', '--', 'dropdb', restored_db])
    run(['ss', '-lnt'])
    run(['free', '-m'])
    run(['df', '-h', '/'])
    run(['systemctl', 'show', 'rhisseth', 'postgresql@16-main', 'nginx', '--property=MemoryCurrent', '--property=NRestarts', '--property=ActiveState'])
    emit('Validation: nginx TLS, auth, static assets, database API, input validation, persistence and backup passed; no reboot')

code = 1
try:
    emit('Preflight: project audit log writable; approved VPS identity required')
    if run(['hostname'], raw=True).stdout.strip() != 'rhisseth' or os.geteuid() != 0:
        raise RuntimeError('VPS identity/privilege mismatch')
    if operation == 'inspect':
        inspect()
    elif operation == 'install':
        install()
    elif operation == 'validate':
        validate()
    else:
        raise RuntimeError('Unknown operation')
    code = 0
except Exception as error:
    emit(f'Failure: {type(error).__name__}: {error}')
finally:
    emit(f'Validation: exit_code={code}; operation={operation}; reboot=false')
    emit(f'VPS audit log: {log}')
sys.exit(code)
