#!/usr/bin/python3
"""Publish the reviewed batell v0.3 archive with backup, migration and test reset."""
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

ROOT=Path('/opt/rhisseth')
ARCHIVE=ROOT/'temp/rhisseth-publish.tgz'
REPO=ROOT/'repository'
now=dt.datetime.now(dt.timezone.utc)
stamp=now.strftime('%Y%m%d%H%M%S')
log_dir=ROOT/'reports/automation-logs'/now.strftime('%Y-%m-%d')
log_dir.mkdir(parents=True,exist_ok=True)
log=log_dir/(stamp+'-batell-v03-publish.md')
log.write_text(f'''# Rhisseth batell v0.3 publication

- UTC: {now.isoformat()}
- Europe/Moscow: {now.astimezone(ZoneInfo('Europe/Moscow')).isoformat()}
- Task: batell-v0.3; operator/controller: Codex
- Runner: STU-AUTOMATION-01 / 10.210.52.128
- Target: Rhisseth VDS 62.113.109.168, PostgreSQL rhisseth, application service
- Action: verified backup, staged code, migrations 015–033, full tester reset, service restart
- Passbolt resource: da44a388-e458-4379-ab4c-c204696804b2
- Reboot: none

''',encoding='utf-8')


def emit(message):
    with log.open('a',encoding='utf-8') as stream:
        stream.write(str(message)+'\n');stream.flush();os.fsync(stream.fileno())
    print(message,flush=True)


def run(args,env=None,timeout=300,quiet=False):
    result=subprocess.run(args,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,text=True)
    emit(f'Command: {" ".join(args)}; exit_code={result.returncode}')
    if not quiet:
        for line in (result.stdout+result.stderr).splitlines():emit(line)
    if result.returncode:raise RuntimeError(f'Command failed: {args[0]}')
    return result


def main():
    if len(sys.argv)!=2 or sys.argv[1]!='publish-v03' or os.geteuid()!=0:
        raise RuntimeError('Invalid operation or identity')
    if not ARCHIVE.is_file() or ARCHIVE.stat().st_size<1024 or not REPO.is_dir():
        raise RuntimeError('Archive or live repository missing')
    if not (ROOT/'venv/bin/python').is_file():
        raise RuntimeError('Application Python environment missing')
    stage=ROOT/('repository.v03-staging-'+stamp)
    backup=ROOT/'backups'/('v03-publish-'+stamp)
    old_repo=backup/'repository-before'
    if stage.exists() or backup.exists():raise RuntimeError('Publication stage or backup already exists')
    backup.mkdir(mode=0o700)
    digest=hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    emit(f'Preflight: reviewed archive bytes={ARCHIVE.stat().st_size}; SHA256={digest}; backup directory ready')
    dump=backup/'rhisseth.dump'
    with dump.open('wb') as stream:
        result=subprocess.run(['runuser','-u','postgres','--','pg_dump','-Fc','-d','rhisseth'],
                              stdout=stream,stderr=subprocess.PIPE,timeout=300)
    emit(f'pg_dump: exit_code={result.returncode}; output suppressed')
    if result.returncode or dump.stat().st_size<1024:raise RuntimeError('Production database backup failed')
    dump.chmod(0o600)
    run(['pg_restore','--list',str(dump)],quiet=True)
    emit(f'Backup verified: {dump}; bytes={dump.stat().st_size}')
    stage.mkdir(mode=0o755)
    with tarfile.open(ARCHIVE,'r:gz') as archive:
        members=archive.getmembers()
        if not members or any(member.name.startswith('/') or '..' in Path(member.name).parts
                              or not(member.isfile() or member.isdir()) for member in members):
            raise RuntimeError('Unexpected archive member')
        archive.extractall(stage,filter='data')
    required=[stage/'app/backend/migrate.py',stage/'scripts/automation/Reset-BatellV03.py',
              stage/'data/migrations/033_siege_wall.sql',stage/'app/frontend/index.html']
    if any(not path.is_file() for path in required):raise RuntimeError('v0.3 archive incomplete')
    emit('Preflight: staged code and required v0.3 release files verified')
    app_env={**os.environ,'DB_HOST':'127.0.0.1','DB_PASSWORD_FILE':str(ROOT/'secrets/db-password.txt')}
    stopped=False;swapped=False
    try:
        run(['systemctl','stop','rhisseth']);stopped=True
        run([str(ROOT/'venv/bin/python'),str(stage/'app/backend/migrate.py')],env=app_env)
        run([str(ROOT/'venv/bin/python'),str(stage/'scripts/automation/Reset-BatellV03.py')],env=app_env)
        REPO.rename(old_repo)
        try:
            stage.rename(REPO);swapped=True
        except Exception:
            old_repo.rename(REPO)
            raise
        run(['systemctl','start','rhisseth']);stopped=False
        for _ in range(30):
            result=subprocess.run(['curl','--max-time','2','-sS','-o','/dev/null','-w','%{http_code}',
                                   'http://127.0.0.1:8080/health'],capture_output=True,text=True)
            if result.returncode==0 and result.stdout=='200':break
            time.sleep(1)
        else:raise RuntimeError('Application health check failed')
        emit('Validation: local /health HTTP 200')
        run(['nginx','-t'])
        run(['systemctl','is-active','rhisseth'])
        run(['curl','--insecure','--max-time','15','-sS','-o','/dev/null','-w','HTTPS %{http_code}',
             'https://62.113.109.168/'])
        emit(f'Validation: v0.3 published; backup={dump}; previous repository={old_repo}; reboot=false')
    except Exception:
        if swapped:
            try:
                run(['systemctl','stop','rhisseth']);stopped=True
                failed=ROOT/('repository.v03-failed-'+stamp)
                REPO.rename(failed)
                old_repo.rename(REPO)
                emit(f'Code rollback: previous repository restored; failed code retained at {failed}')
            except Exception as error:
                emit(f'Code rollback failed: {type(error).__name__}: {error}')
        if stopped:
            try:run(['systemctl','start','rhisseth'])
            except Exception as error:emit(f'Service restart failed: {type(error).__name__}: {error}')
        emit(f'Failure recovery: database backup retained at {dump}; no automatic database restore; reboot=false')
        raise


try:
    main();code=0
except Exception as error:
    emit(f'Failure: {type(error).__name__}: {error}');code=1
finally:
    emit(f'Final exit_code={code}; reboot=false; secrets_logged=false')
sys.exit(code)
