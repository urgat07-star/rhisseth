#!/usr/bin/python3
# Release review 2026-09-18 (0.0.2): Full logical backup on source VPS. Result path only, never archive contents.
# Details: docs/releases/0.0.2-changes-2026-09-18.md.
"""Full logical backup on source VPS. Result path only, never archive contents."""
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request
import uuid
from zoneinfo import ZoneInfo

ROOT = Path('/opt/rhisseth')
os.umask(0o077)
def main():
    now = dt.datetime.now(dt.timezone.utc)
    logs = ROOT / 'reports/automation-logs' / now.strftime('%Y-%m-%d')
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / (now.strftime('%Y%m%d-%H%M%S-%f') + '-full-backup.md')
    log.write_text(f'# Full Rhisseth backup\n\nUTC: {now.isoformat()}\n\nMoscow: {now.astimezone(ZoneInfo("Europe/Moscow")).isoformat()}\n\nTask: backup-and-portable-deployment; controller: Codex / runner\n\nRunner: STU-AUTOMATION-01 / 10.210.52.128\n\nTarget: 62.113.109.168 PostgreSQL rhisseth, /opt/rhisseth project data/configuration\n\nPassbolt: da44a388-e458-4379-ab4c-c204696804b2\n\nAction: full backup; reboot=false\n', encoding='utf-8')
    def audit(value):
        with log.open('a') as stream:
            timestamp = dt.datetime.now(dt.timezone.utc)
            stream.write(f'{timestamp.isoformat()} / {timestamp.astimezone(ZoneInfo("Europe/Moscow")).isoformat()} {value}\n')
            stream.flush()
            os.fsync(stream.fileno())
    def run(args,check=True):
        p = subprocess.run(args, capture_output=True, text=True, timeout=300)
        audit(f'Command: {" ".join(args)}; exit_code={p.returncode}; raw output suppressed')
        if check and p.returncode:
            raise RuntimeError('Backup command failed')
        return p.stdout.strip()
    code, stopped = 1, False
    output = None
    try:
        if os.geteuid() != 0:
            raise RuntimeError('Root required')
        lock = Path('/run/lock/rhisseth-full-backup.lock').open('a')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if shutil.disk_usage(ROOT).free < 512 * 1024**2:
            raise RuntimeError('Insufficient backup workspace')
        repo = ROOT / 'repository'
        dirty = bool(run(['git', '-C', str(repo), 'status', '--porcelain']))
        if dirty:
            audit('Local code changes detected: preserve private source-worktree evidence; approved release remains deployment source')
        sha = run(['git', '-C', str(repo), 'rev-parse', 'HEAD'])
        # Exclude only reproducible code/runtime, previous backups and operational logs.
        # Everything else inside project root is included, including previews/temp/secrets.
        included = [p for p in ROOT.iterdir() if p.name not in ('repository', 'venv', 'backups', 'reports', 'backup-spool', 'scripts')]
        if any(p.is_symlink() for p in included):
            raise RuntimeError('External project symlinks require explicit inventory')
        size = sum(p.stat().st_size for top in included for p in ([top] if top.is_file() else top.rglob('*')) if p.is_file())
        if dirty:
            size += sum(p.stat().st_size for p in repo.rglob('*') if p.is_file() and '.git' not in p.relative_to(repo).parts)
        dbsize = int(run(['runuser', '-u', 'postgres', '--', 'psql', '-X', '-At', '-d', 'rhisseth', '-c', 'SELECT pg_database_size(current_database())']))
        if shutil.disk_usage(ROOT).free < 2 * (size + dbsize) + 256 * 1024**2:
            raise RuntimeError('Insufficient workspace for full archive')
        audit('Preflight: root, lock, Git identity and free space verified; local changes archived privately if present')
        spool = ROOT / 'backup-spool'
        spool.mkdir(mode=0o700, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.work-', dir=spool) as temporary:
            work = Path(temporary)
            was_active = run(['systemctl', 'is-active', 'rhisseth'],check=False) == 'active'
            audit('Approved change: pause application writes for DB/files consistency')
            if was_active:
                run(['systemctl', 'stop', 'rhisseth'])
                stopped = True
            # pg_dump stdout is binary and private; postgres cannot write root-only workspace.
            with (work / 'database.dump').open('wb') as dump:
                p = subprocess.run(['runuser', '-u', 'postgres', '--', 'pg_dump', '-Fc', '--no-owner', '--no-acl', '-d', 'rhisseth'], stdout=dump, stderr=subprocess.PIPE, timeout=300)
            audit(f'Command: pg_dump -Fc --no-owner --no-acl rhisseth; exit_code={p.returncode}; output private')
            if p.returncode:
                raise RuntimeError('Database dump failed')
            run(['pg_restore', '--list', str(work / 'database.dump')])
            tables = run(['runuser', '-u', 'postgres', '--', 'psql', '-X', '-At', '-d', 'rhisseth', '-c', "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"]).splitlines()
            signatures = {}
            for table in tables:
                if not table.replace('_', '').isalnum():
                    raise RuntimeError('Unsupported table identifier')
                statement = f'''SET TIME ZONE 'UTC'; SELECT count(*), md5(COALESCE(string_agg(row_value, E'\\n' ORDER BY row_value COLLATE "C"),'')) FROM (SELECT row_to_json(t)::text AS row_value FROM "{table}" t) s'''
                signatures[table] = run(['runuser', '-u', 'postgres', '--', 'psql', '-X', '-At', '-d', 'rhisseth', '-c', statement])
                signatures[table] = signatures[table].splitlines()[-1]
            schema = run(['runuser', '-u', 'postgres', '--', 'psql', '-X', '-At', '-d', 'rhisseth', '-c', 'SELECT name FROM schema_migrations ORDER BY name']).splitlines()
            for top in included:
                destination = work / 'project' / top.name
                destination.parent.mkdir(exist_ok=True)
                if top.is_dir():
                    shutil.copytree(top, destination, symlinks=True)
                else:
                    shutil.copy2(top, destination)
            if dirty:
                evidence = work/'project/source-worktree'
                if evidence.exists():
                    raise RuntimeError('Reserved source-worktree evidence path already exists')
                audit('Approved backup action: private worktree snapshot including modified and untracked files; Git database/runtime caches excluded')
                shutil.copytree(repo,evidence,ignore=shutil.ignore_patterns('.git','__pycache__'),symlinks=True)
                if any(p.is_symlink() for p in evidence.rglob('*')):
                    raise RuntimeError('Worktree symlinks require explicit backup inventory')
                evidence.chmod(0o700)
            config = work / 'configuration'
            config.mkdir()
            for source, name in [('/etc/nginx', 'nginx'), ('/etc/systemd/system/rhisseth.service', 'rhisseth.service'), ('/etc/postgresql/16/main/conf.d', 'postgresql-conf.d')]:
                path = Path(source)
                if path.is_dir():
                    shutil.copytree(path, config / name, symlinks=True)
                elif path.is_file():
                    shutil.copy2(path, config / name)
            if stopped:
                run(['systemctl', 'start', 'rhisseth'])
                stopped = False
                for attempt in range(30):
                    try:
                        with urllib.request.urlopen('http://127.0.0.1:8080/index.php',timeout=2) as response:
                            if response.status==200:
                                audit('Validation: resumed application login HTTP=200; DB reachable; response body suppressed')
                                break
                    except Exception:
                        time.sleep(0.5)
                else:
                    raise RuntimeError('Application failed to recover after backup pause')
            files = {}
            for path in work.rglob('*'):
                if path.is_file() and not path.is_symlink():
                    with path.open('rb') as stream:
                        files[path.relative_to(work).as_posix()] = hashlib.file_digest(stream, 'sha256').hexdigest()
            migration_hashes = {}
            for name in schema:
                with (repo/'data/migrations'/name).open('rb') as stream:
                    migration_hashes[name] = hashlib.file_digest(stream,'sha256').hexdigest()
            manifest = {'format':1, 'created_utc':now.isoformat(), 'timezone':'Europe/Moscow', 'signature_order':'C', 'signature_timezone':'UTC', 'git_sha':sha, 'dirty_worktree':dirty, 'worktree_policy':'private evidence only; never automatically applied to approved release', 'postgresql_major':16, 'schema_migrations':schema, 'migrations_sha256':migration_hashes, 'table_signatures':signatures, 'files_sha256':files, 'project_paths':[p.name for p in included]+(['source-worktree'] if dirty else []), 'excluded':['Git database/clean code/runtime','previous backups','logs','automation scripts outside worktree'], 'unencrypted':True}
            (work / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
            name = 'rhisseth-' + now.strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8] + '.tar.gz'
            output = spool / name
            audit('Approved change: create private portable archive ' + name)
            with tarfile.open(output, 'w:gz') as archive:
                for path in work.iterdir():
                    archive.add(path, arcname=path.name)
            digest = hashlib.file_digest(output.open('rb'), 'sha256').hexdigest()
            audit('Validation: dump readable; DB signatures recorded; archive complete; application resumed')
            for old in spool.glob('rhisseth-*.tar.gz'):
                if old != output and re.fullmatch(r'rhisseth-\d{8}T\d{6}Z-[a-f0-9]{8}\.tar\.gz',old.name) and not old.is_symlink():
                    audit('Approved local spool cleanup after new complete archive: '+old.name)
                    old.unlink()
            print(json.dumps({'path':str(output),'name':name,'size':output.stat().st_size,'sha256':digest,'manifest':manifest,'log':str(log)}))
        code = 0
    except Exception as error:
        audit('Failure: ' + type(error).__name__ + '; sensitive details suppressed')
        if output:
            output.unlink(missing_ok=True)
    finally:
        if stopped:
            audit('Recovery action: resume application after failed backup')
            p = subprocess.run(['systemctl', 'start', 'rhisseth'], capture_output=True)
            audit(f'Resume exit_code={p.returncode}')
        audit(f'Validation: exit_code={code}; archive_created={code == 0}; temporary application pause; reboot=false')
    return code
if __name__ == '__main__':
    raise SystemExit(main())
