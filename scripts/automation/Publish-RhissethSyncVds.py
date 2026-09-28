#!/usr/bin/python3
"""Deploy one reviewed Git archive to the Rhisseth VDS without changing game data."""
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
REPO = ROOT / 'repository'
ARCHIVE = ROOT / 'temp/rhisseth-sync.tgz'
now = dt.datetime.now(dt.timezone.utc)
stamp = now.strftime('%Y%m%d-%H%M%S')
logdir = ROOT / 'reports/automation-logs' / now.strftime('%Y-%m-%d')
logdir.mkdir(parents=True, exist_ok=True)
log = logdir / (stamp + '-rhisseth-sync.md')
log.write_text(
    '# Rhisseth VDS synchronization\n\n'
    f'- UTC: {now.isoformat()}\n'
    f'- Europe/Moscow: {now.astimezone(ZoneInfo("Europe/Moscow")).isoformat()}\n'
    '- Task: rhisseth-git-vds-sync; operator/controller: Codex / operator workstation\n'
    '- Runner: not used (Rhisseth VDS exception)\n'
    '- Target: 62.113.109.168, /opt/rhisseth/repository and PostgreSQL rhisseth\n'
    '- Action: verified backup, staged Git archive, service restart\n'
    '- Passbolt resource: not used; pinned SSH key\n'
    '- Change/reboot: pending / no reboot\n\n', encoding='utf-8')


def emit(message):
    with log.open('a', encoding='utf-8') as stream:
        stream.write(str(message) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    print(message, flush=True)


def run(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=120)
    emit(f'Command: {" ".join(args)}; exit_code={result.returncode}')
    if result.returncode:
        emit(result.stderr.strip())
        raise RuntimeError(f'Command failed: {args[0]}')
    return result.stdout.strip()


def main():
    if len(sys.argv) != 2 or len(sys.argv[1]) != 64 or not all(c in '0123456789abcdef' for c in sys.argv[1]):
        raise RuntimeError('Expected SHA256 argument')
    if os.geteuid() != 0 or not REPO.is_dir() or not ARCHIVE.is_file():
        raise RuntimeError('VDS identity, repository or archive invalid')
    with ARCHIVE.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != sys.argv[1]:
        raise RuntimeError('Archive SHA256 mismatch')
    emit(f'Preflight: archive SHA256 verified: {digest}; live repository exists')
    backup = ROOT / 'backups' / ('sync-' + stamp)
    stage = ROOT / ('repository.sync-staging-' + stamp)
    if backup.exists() or stage.exists():
        raise RuntimeError('Backup or staging path already exists')
    backup.mkdir(mode=0o700)
    dump = backup / 'rhisseth.dump'
    with dump.open('wb') as stream:
        result = subprocess.run(['runuser', '-u', 'postgres', '--', 'pg_dump', '-Fc', '-d', 'rhisseth'],
                                stdout=stream, stderr=subprocess.PIPE, timeout=300)
    emit(f'pg_dump: exit_code={result.returncode}; output suppressed')
    if result.returncode or dump.stat().st_size < 1024:
        raise RuntimeError('Database backup failed')
    dump.chmod(0o600)
    run(['pg_restore', '--list', str(dump)])
    emit(f'Backup verified: {dump}; bytes={dump.stat().st_size}')
    previous = backup / 'repository-before'
    shutil.copytree(REPO, previous, symlinks=True)
    emit(f'File backup verified: {previous}')
    stage.mkdir(mode=0o755)
    with tarfile.open(ARCHIVE, 'r:gz') as tar:
        members = tar.getmembers()
        if not members or any(m.name.startswith('/') or '..' in Path(m.name).parts or
                              not (m.isfile() or m.isdir()) for m in members):
            raise RuntimeError('Unsafe archive content')
        tar.extractall(stage, filter='data')
    for required in ('app/frontend/index.html', 'app/frontend/app.js',
                     'data/import/hex-initial-parameters.csv', 'app/backend/main.py'):
        if not (stage / required).is_file():
            raise RuntimeError(f'Archive missing {required}')
    emit('Preflight: staged archive verified; database unchanged')
    moved = False
    swapped = False
    stopped = False
    try:
        run(['systemctl', 'stop', 'rhisseth'])
        stopped = True
        REPO.rename(backup / 'repository-live')
        moved = True
        stage.rename(REPO)
        swapped = True
        run(['systemctl', 'start', 'rhisseth'])
        stopped = False
        for _ in range(30):
            health = subprocess.run(['curl', '--max-time', '2', '-sS', '-o', '/dev/null',
                                     '-w', '%{http_code}', 'http://127.0.0.1:8080/health'],
                                    capture_output=True, text=True)
            if health.returncode == 0 and health.stdout == '200':
                emit('Command: curl local /health; exit_code=0; HTTP 200')
                break
            time.sleep(1)
        else:
            raise RuntimeError('Application health check failed after 30 attempts')
        run(['systemctl', 'is-active', 'rhisseth'])
        run(['nginx', '-t'])
        emit('Validation: application /health HTTP 200, service active, nginx config valid')
        emit(f'Change/reboot: repository deployed / no reboot; backup={backup}')
    except Exception:
        if moved:
            run(['systemctl', 'stop', 'rhisseth'])
            if swapped:
                failed = backup / 'repository-failed'
                REPO.rename(failed)
            (backup / 'repository-live').rename(REPO)
            emit('Rollback: previous repository restored')
        if stopped or moved:
            run(['systemctl', 'start', 'rhisseth'])
        raise


try:
    main()
    code = 0
except Exception as error:
    emit(f'Failure: {type(error).__name__}: {error}')
    code = 1
finally:
    emit(f'Exit code: {code}; reboot: no; log: {log}')
sys.exit(code)
