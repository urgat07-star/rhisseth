#!/usr/bin/python3
"""Deploy the reviewed v0.3.4 archive without resetting player state."""
import datetime as dt
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time
from zoneinfo import ZoneInfo

ROOT = Path('/opt/rhisseth')
ARCHIVE = ROOT / 'temp/rhisseth-publish.tgz'
REPO = ROOT / 'repository'
NOW = dt.datetime.now(dt.timezone.utc)
STAMP = NOW.strftime('%Y%m%d%H%M%S')
LOG_DIR = ROOT / 'reports/automation-logs' / NOW.strftime('%Y-%m-%d')
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG = LOG_DIR / (STAMP + '-batell-v034-publish.md')
LOG.write_text(f'''# Rhisseth batell v0.3.4 publication

- UTC: {NOW.isoformat()}
- Europe/Moscow: {NOW.astimezone(ZoneInfo('Europe/Moscow')).isoformat()}
- Task: batell-v0.3.4-live-test; operator/controller: Codex
- Runner: STU-AUTOMATION-01 / 10.210.52.128
- Target: Rhisseth VDS 62.113.109.168, PostgreSQL rhisseth, rhisseth service
- Action: verified current backup, v0.3.2 schema validation, tagged-code deployment, validation
- Passbolt resource: da44a388-e458-4379-ab4c-c204696804b2
- Player reset: none; host reboot: none

''', encoding='utf-8')


def emit(message):
    with LOG.open('a', encoding='utf-8') as stream:
        stream.write(str(message) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    print(message, flush=True)


def run(args, *, env=None, timeout=300, quiet=False):
    result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=timeout)
    emit(f'Command: {" ".join(args)}; exit_code={result.returncode}')
    if not quiet:
        for line in (result.stdout + result.stderr).splitlines():
            emit(line)
    if result.returncode:
        raise RuntimeError(f'Command failed: {args[0]}')
    return result


def main():
    if len(sys.argv) != 2 or sys.argv[1] != 'publish-v034' or os.geteuid() != 0:
        raise RuntimeError('Invalid operation or identity')
    if not ARCHIVE.is_file() or ARCHIVE.stat().st_size < 1024 or not REPO.is_dir():
        raise RuntimeError('Archive or live repository missing')
    python = ROOT / 'venv/bin/python'
    if not python.is_file():
        raise RuntimeError('Application Python environment missing')
    stage = ROOT / ('repository.v034-staging-' + STAMP)
    backup = ROOT / 'backups' / ('v034-publish-' + STAMP)
    old_repo = backup / 'repository-before'
    if stage.exists() or backup.exists():
        raise RuntimeError('Publication stage or backup already exists')
    stage.mkdir(mode=0o755)
    digest = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    emit(f'Preflight: reviewed v0.3.4 archive bytes={ARCHIVE.stat().st_size}; SHA256={digest}')
    with tarfile.open(ARCHIVE, 'r:gz') as archive:
        members = archive.getmembers()
        if not members or any(member.name.startswith('/') or '..' in Path(member.name).parts
                              or not (member.isfile() or member.isdir()) for member in members):
            raise RuntimeError('Unexpected archive member')
        archive.extractall(stage, filter='data')
    required = [stage / 'app/backend/migrate.py', stage / 'data/migrations/035_batell_v032.sql',
                stage / 'app/frontend/index.html', stage / 'docs/releases/batell-v0.3.4.md']
    if any(not item.is_file() for item in required):
        raise RuntimeError('v0.3.4 archive incomplete')
    existing = run(['runuser', '-u', 'postgres', '--', 'psql', '-At', '-d', 'rhisseth',
                    '-c', "SELECT count(*) FROM schema_migrations WHERE name='034_test_skip.sql'"], quiet=True)
    if existing.stdout.strip() != '1':
        raise RuntimeError('Expected v0.3.1 database baseline missing')
    emit('Preflight: v0.3.2 database baseline confirmed; v0.3.4 files staged')

    backup.mkdir(mode=0o700)
    dump = backup / 'rhisseth.dump'
    with dump.open('wb') as stream:
        result = subprocess.run(['runuser', '-u', 'postgres', '--', 'pg_dump', '-Fc', '-d', 'rhisseth'],
                                stdout=stream, stderr=subprocess.PIPE, timeout=300)
    emit(f'pg_dump: exit_code={result.returncode}; output suppressed')
    if result.returncode or dump.stat().st_size < 1024:
        raise RuntimeError('Production database backup failed')
    dump.chmod(0o600)
    run(['pg_restore', '--list', str(dump)], quiet=True)
    shutil.copytree(REPO, old_repo, symlinks=True)
    emit(f'Backup verified: {dump}; bytes={dump.stat().st_size}; previous code={old_repo}')

    app_env = {**os.environ, 'DB_HOST': '127.0.0.1',
               'DB_PASSWORD_FILE': str(ROOT / 'secrets/db-password.txt')}
    stopped = False
    swapped = False
    try:
        run(['systemctl', 'stop', 'rhisseth'])
        stopped = True
        run([str(python), str(stage / 'app/backend/migrate.py')], env=app_env)
        migrated = run(['runuser', '-u', 'postgres', '--', 'psql', '-At', '-d', 'rhisseth',
                        '-c', "SELECT count(*) FROM schema_migrations WHERE name='035_batell_v032.sql'"], quiet=True)
        if migrated.stdout.strip() != '1':
            raise RuntimeError('Migration 035 not recorded')
        REPO.rename(backup / 'repository-swapped')
        try:
            stage.rename(REPO)
            swapped = True
        except Exception:
            (backup / 'repository-swapped').rename(REPO)
            raise
        run(['systemctl', 'start', 'rhisseth'])
        stopped = False
        for _ in range(30):
            health = subprocess.run(['curl', '--max-time', '2', '-sS', '-o', '/dev/null',
                                     '-w', '%{http_code}', 'http://127.0.0.1:8080/health'],
                                    capture_output=True, text=True)
            if health.returncode == 0 and health.stdout == '200':
                break
            time.sleep(1)
        else:
            raise RuntimeError('Application health check failed')
        emit('Validation: local /health HTTP 200')
        run(['nginx', '-t'])
        run(['systemctl', 'is-active', 'rhisseth'])
        run(['curl', '--insecure', '--max-time', '15', '-sS', '-o', '/dev/null',
             '-w', 'HTTPS %{http_code}', 'https://62.113.109.168/'])
        emit(f'Validation: v0.3.4 live; migration 035 remains applied; backup={dump}; '
             'player reset=false; host reboot=false')
    except Exception:
        if swapped:
            try:
                run(['systemctl', 'stop', 'rhisseth'])
                stopped = True
                failed = ROOT / ('repository.v034-failed-' + STAMP)
                REPO.rename(failed)
                (backup / 'repository-swapped').rename(REPO)
                emit(f'Code rollback: previous repository restored; failed code retained at {failed}')
            except Exception as error:
                emit(f'Code rollback failed: {type(error).__name__}: {error}')
        if stopped:
            try:
                run(['systemctl', 'start', 'rhisseth'])
            except Exception as error:
                emit(f'Service restart failed: {type(error).__name__}: {error}')
        emit(f'Failure recovery: database backup retained at {dump}; '
             'migration is additive; no automatic database restore')
        raise


try:
    main()
    code = 0
except Exception as error:
    emit(f'Failure: {type(error).__name__}: {error}')
    code = 1
finally:
    emit(f'Final exit_code={code}; host_reboot=false; player_reset=false')
sys.exit(code)
