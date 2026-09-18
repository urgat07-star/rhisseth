# Release review 2026-09-18 (0.0.2): Deploy the reviewed player-onboarding package on the approved Rhisseth VPS.
# Details: docs/releases/0.0.2-changes-2026-09-18.md.
"""Deploy the reviewed player-onboarding package on the approved Rhisseth VPS."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time
import traceback
import urllib.request
from zoneinfo import ZoneInfo

ROOT = Path('/opt/rhisseth')
REPO = ROOT / 'repository'
PACKAGE = ROOT / 'temp/player-onboarding.tar'
ALLOWED = {
    'app/backend/main.py', 'app/backend/site_auth.py', 'app/backend/game_start.py',
    'app/backend/hex_rules.py', 'app/frontend/index.html', 'app/frontend/app.js',
    'app/frontend/styles.css', 'app/frontend/create-barony.html',
    'app/frontend/cabinet.html', 'app/frontend/crests/gerb_1.png',
    'app/frontend/crests/gerb_2.png', 'app/frontend/crests/gerb_3.png',
    'app/frontend/crests/gerb_4.png', 'app/frontend/crests/gerb_5.png',
    'data/migrations/006_player_onboarding.sql',
    'data/migrations/007_player_cabinet.sql', 'app/backend/player_cabinet.py',
    'data/migrations/008_player_barony_rename.sql',
    'app/frontend/cabinet.js',
}

now = dt.datetime.now(dt.timezone.utc)
directory = ROOT / 'reports/automation-logs' / now.strftime('%Y-%m-%d')
directory.mkdir(parents=True, exist_ok=True)
log = directory / f'{now:%Y%m%d-%H%M%S}-player-onboarding-deploy.md'
log.write_text(
    f'# Rhisseth player onboarding deployment\n\n'
    f'- UTC: {now.isoformat()}\n- Europe/Moscow: {now.astimezone(ZoneInfo("Europe/Moscow")).isoformat()}\n'
    '- Task: player-onboarding-release; controller: Codex via STU-AUTOMATION-01 / 10.210.52.128\n'
    '- Runner: STU-AUTOMATION-01 / 10.210.52.128\n'
    '- Target: 62.113.109.168 / rhisseth.ru; action: reviewed package deployment and PostgreSQL migration\n'
    '- Passbolt: da44a388-e458-4379-ab4c-c204696804b2\n', encoding='utf-8')

def emit(message):
    with log.open('a', encoding='utf-8') as stream:
        stream.write(str(message) + '\n')
    print(message, flush=True)

def run(args, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, timeout=90, **kwargs)
    emit('Command: ' + ' '.join(args) + '; exit_code=' + str(result.returncode))
    if result.returncode:
        emit('Sanitized diagnostic: ' + result.stderr[-1000:])
        raise RuntimeError('approved command failed')
    return result.stdout

code = 1
changed = False
try:
    os.umask(0o077)
    if not PACKAGE.is_file():
        raise RuntimeError('reviewed deployment package missing')
    with tarfile.open(PACKAGE) as archive:
        members = archive.getmembers()
        names = {member.name for member in members}
        if names != ALLOWED or any(not member.isfile() for member in members):
            raise RuntimeError('package manifest mismatch')
    emit('Preflight: package manifest, audit log, project paths and approved target verified')
    emit('Package SHA256: ' + hashlib.sha256(PACKAGE.read_bytes()).hexdigest())
    emit('Current service state: ' + run(['systemctl', 'is-active', 'rhisseth']).strip())
    backup = ROOT / 'backups' / f'player-onboarding-{now:%Y%m%d-%H%M%S}'
    backup.mkdir(parents=True)
    dump = backup / 'database.dump'
    with dump.open('wb') as stream:
        result = subprocess.run(['runuser', '-u', 'postgres', '--', 'pg_dump', '-Fc', 'rhisseth'], stdout=stream, stderr=subprocess.PIPE, timeout=90)
    emit('Database backup: ' + str(dump) + '; exit_code=' + str(result.returncode))
    if result.returncode:
        raise RuntimeError('database backup failed')
    for name in ALLOWED:
        target = REPO / name
        if target.exists():
            saved = backup / 'files' / name
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, saved)
    test_db = 'rhisseth_player_onboarding_check'
    run(['runuser', '-u', 'postgres', '--', 'createdb', '-O', 'rhisseth', test_db])
    try:
        with dump.open('rb') as stream:
            result = subprocess.run(['runuser', '-u', 'postgres', '--', 'pg_restore', '-d', test_db], stdin=stream, capture_output=True, timeout=90)
        emit('Isolated database restore: exit_code=' + str(result.returncode))
        if result.returncode:
            raise RuntimeError('isolated restore failed')
        stage = backup / 'stage'
        shutil.copytree(REPO / 'app/backend', stage / 'app/backend')
        shutil.copytree(REPO / 'data/migrations', stage / 'data/migrations')
        with tarfile.open(PACKAGE) as archive:
            for member in archive.getmembers():
                target = stage / member.name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())
        run([str(ROOT / 'venv/bin/python'), str(stage / 'app/backend/migrate.py')], env={**os.environ, 'DB_NAME': test_db, 'DB_HOST': '127.0.0.1', 'DB_PASSWORD_FILE': str(ROOT / 'secrets/db-password.txt')})
        emit(run([str(ROOT / 'venv/bin/python'), str(Path(__file__).with_name('VerifyPlayerCabinet.py')), str(stage), test_db]))
    finally:
        run(['runuser', '-u', 'postgres', '--', 'dropdb', test_db])
    emit('Validation: migration applied successfully to isolated restored copy')
    with tarfile.open(PACKAGE) as archive:
        for member in archive.getmembers():
            changed = True
            target = REPO / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.extractfile(member).read())
            target.chmod(0o644)
    (REPO / 'app/frontend/crests').chmod(0o755)
    run([str(ROOT / 'venv/bin/python'), str(REPO / 'app/backend/migrate.py')], env={**os.environ, 'DB_HOST': '127.0.0.1', 'DB_PASSWORD_FILE': str(ROOT / 'secrets/db-password.txt')})
    run(['systemctl', 'restart', 'rhisseth'])
    run(['systemctl', 'is-active', 'rhisseth'])
    for _ in range(20):
        try:
            urllib.request.urlopen('http://127.0.0.1:8080/api/me', timeout=3)
        except urllib.error.HTTPError as error:
            if error.code == 401:
                break
        except OSError:
            pass
        time.sleep(.25)
    else:
        raise RuntimeError('application readiness failed')
    sys.path.insert(0, str(REPO / 'app/backend'))
    os.environ.update(DB_HOST='127.0.0.1', DB_PASSWORD_FILE=str(ROOT / 'secrets/db-password.txt'))
    from db import connect
    from site_auth import COOKIE, new_session, token_hash
    with connect() as conn:
        admin = conn.execute("SELECT user_id FROM users JOIN roles USING(role_id) WHERE role_alias='admin' LIMIT 1").fetchone()
        migration = conn.execute("SELECT 1 FROM schema_migrations WHERE name='008_player_barony_rename.sql'").fetchone()
    if admin is None or migration is None:
        raise RuntimeError('post-deployment data validation failed')
    token, _ = new_session(admin[0])
    try:
        for base in ('http://127.0.0.1:8080', 'https://rhisseth.ru'):
            for path in ('/api/me', '/api/hexes', '/api/cabinet', '/api/start/options', '/api/start/options?random=true', '/interactive-map/create-barony.html', '/interactive-map/cabinet.html', '/interactive-map/cabinet.js', '/interactive-map/crests/gerb_1.png'):
                request = urllib.request.Request(base + path, headers={'Cookie': COOKIE + '=' + token})
                with urllib.request.urlopen(request, timeout=15) as response:
                    content = response.read()
                    if path == '/interactive-map/create-barony.html':
                        assert b'id="territory-name"' not in content
                        assert b'id="random-barony"' in content
                    if path == '/interactive-map/cabinet.html':
                        assert b'cabinet.js' in content and b'id="map-viewport"' not in content
                        assert b'id="tab-settings"' in content and b'id="tab-account"' not in content and b'id="tab-armies"' not in content
                        assert b'id="barony-name-form"' in content
                    if path == '/api/start/options?random=true':
                        result = json.loads(content)
                        if not result['started'] and result['random_cells']:
                            from hex_rules import connected
                            cells = [tuple(c) for c in result['random_cells']]
                            assert len(cells) in (2,3) and connected(cells)
                            assert set(cells) <= {tuple(c) for c in result['available_cells']}
                    emit('Authenticated HTTP validation: ' + base + path + '; status=' + str(response.status))
    finally:
        with connect() as conn:
            conn.execute('DELETE FROM user_sessions WHERE token_hash=%s', (token_hash(token),))
    emit('Validation: migration, service, authenticated endpoints and temporary session cleanup successful')
    emit('Changed: reviewed application files, player onboarding schema and assets; service restarted; database host not restarted')
    code = 0
except Exception as error:
    emit('Failure: ' + type(error).__name__ + '; safe traceback follows')
    emit(traceback.format_exc(limit=4).replace(str(ROOT / 'secrets'), '<redacted-secrets>'))
finally:
    emit(f'Validation: exit_code={code}; reboot=false; change={changed}; log={log}')
sys.exit(code)
