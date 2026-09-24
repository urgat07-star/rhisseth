"""Reviewed VDS-side publication with PostgreSQL backup and staged replacement."""
import datetime as dt, shutil, subprocess, sys, tarfile
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT = Path('/opt/rhisseth')
now = dt.datetime.now(dt.timezone.utc)
logdir = ROOT / 'reports/automation-logs' / now.strftime('%Y-%m-%d')
logdir.mkdir(parents=True, exist_ok=True)
log = logdir / (now.strftime('%Y%m%d-%H%M%S') + '-publish.md')
def emit(value):
    with log.open('a', encoding='utf-8') as stream: stream.write(str(value) + '\n')
    print(value, flush=True)
def run(args):
    result = subprocess.run(args, capture_output=True, text=True)
    emit('Command: ' + ' '.join(args)); emit(result.stdout.strip()); emit(result.stderr.strip()); emit('Exit code: ' + str(result.returncode))
    if result.returncode: raise RuntimeError('command failed: ' + args[0])
    return result
def main():
    archive = ROOT / 'temp/rhisseth-publish.tgz'; repo = ROOT / 'repository'
    backup = ROOT / 'backups' / now.strftime('%Y%m%d-%H%M%S'); backup.mkdir(parents=True, exist_ok=True); backup.chmod(0o700)
    if not archive.is_file() or archive.stat().st_size == 0: raise RuntimeError('archive missing')
    dump = backup / 'rhisseth.dump'
    with dump.open('wb') as stream:
        result = subprocess.run(['runuser', '-u', 'postgres', '--', 'pg_dump', '-Fc', '-d', 'rhisseth'], stdout=stream, stderr=subprocess.PIPE)
    if result.returncode: raise RuntimeError('database backup failed')
    shutil.chown(dump, user='postgres', group='postgres'); dump.chmod(0o600)
    run(['runuser', '-u', 'postgres', '--', 'pg_restore', '--list', str(dump)])
    staging = ROOT / 'repository.publish-staging'
    if staging.exists(): shutil.rmtree(staging)
    staging.mkdir()
    with tarfile.open(archive, 'r:gz') as tar: tar.extractall(staging)
    old_backup = backup / 'repository-before'; shutil.copytree(repo, old_backup, symlinks=True)
    shutil.rmtree(repo); staging.rename(repo)
    run(['systemctl', 'restart', 'rhisseth']); run(['systemctl', 'is-active', 'rhisseth']); run(['nginx', '-t'])
    run(['curl', '--max-time', '15', '-sS', '-o', '/dev/null', '-w', 'HTTP %{http_code}\\n', 'https://62.113.109.168/'])
    emit(f'Backup: {dump}; previous repository: {old_backup}; change/reboot: deployed/no reboot')
try:
    main(); emit('Validation: publication success'); sys.exit(0)
except Exception as error:
    emit(f'Failure: {type(error).__name__}: {error}'); sys.exit(1)
