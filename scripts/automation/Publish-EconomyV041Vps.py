#!/usr/bin/python3
"""Publish Economy v0.4.1 with restored-copy migration test and one safe backfill."""
import datetime as dt, hashlib, os, shutil, subprocess, sys, tarfile, time, secrets
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path('/opt/rhisseth'); ARCHIVE=ROOT/'temp/rhisseth-publish.tgz'; REPO=ROOT/'repository'
NOW=dt.datetime.now(dt.timezone.utc); STAMP=NOW.strftime('%Y%m%d%H%M%S')
LOGDIR=ROOT/'reports/automation-logs'/NOW.strftime('%Y-%m-%d'); LOGDIR.mkdir(parents=True,exist_ok=True)
LOG=LOGDIR/(STAMP+'-economy-v041-publish.md')
LOG.write_text(f'''# Rhisseth Economy v0.4.1 publication

- UTC: {NOW.isoformat()}
- Europe/Moscow: {NOW.astimezone(ZoneInfo('Europe/Moscow')).isoformat()}
- Controller: Codex through STU-AUTOMATION-01 / 10.210.52.128
- Target: Rhisseth VDS 62.113.109.168; PostgreSQL rhisseth; rhisseth service
- Action: verified backup, restored-copy migration, code deployment, one missed population/tax year
- Passbolt resource: da44a388-e458-4379-ab4c-c204696804b2
- Player reset: none; host reboot: none

''',encoding='utf-8')

def emit(value):
    with LOG.open('a',encoding='utf-8') as stream:
        stream.write(str(value)+'\n');stream.flush();os.fsync(stream.fileno())
    print(value,flush=True)

def run(args,env=None,timeout=300,quiet=False):
    result=subprocess.run(args,env=env,capture_output=True,text=True,timeout=timeout)
    emit(f'Command: {" ".join(map(str,args))}; exit_code={result.returncode}')
    if not quiet:
        for line in (result.stdout+result.stderr).splitlines():emit(line)
    if result.returncode:raise RuntimeError(f'Command failed: {args[0]}')
    return result

def psql(database,statement):
    return run(['runuser','-u','postgres','--','psql','-X','-v','ON_ERROR_STOP=1','-At','-d',database,'-c',statement],quiet=True).stdout.strip()

def main():
    if sys.argv[1:]!=['publish-economy-v041'] or os.geteuid()!=0:raise RuntimeError('Invalid operation or identity')
    if not ARCHIVE.is_file() or ARCHIVE.stat().st_size<1024 or not REPO.is_dir():raise RuntimeError('Archive or repository missing')
    python=ROOT/'venv/bin/python';stage=ROOT/('repository.economy-v041-staging-'+STAMP)
    backup=ROOT/'backups'/('economy-v041-'+STAMP);old=backup/'repository-before'
    stage.mkdir(mode=0o755);digest=hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    emit(f'Preflight: archive bytes={ARCHIVE.stat().st_size}; SHA256={digest}; audit writable')
    with tarfile.open(ARCHIVE,'r:gz') as archive:
        members=archive.getmembers()
        if not members or any(m.name.startswith('/') or '..' in Path(m.name).parts or not(m.isfile() or m.isdir()) for m in members):raise RuntimeError('Unsafe archive')
        archive.extractall(stage,filter='data')
    required=[stage/'app/backend/migrate.py',stage/'app/backend/game_clock.py',stage/'data/migrations/046_population_tax_history.sql',stage/'docs/releases/economy-v0.4.1.md']
    if any(not path.is_file() for path in required):raise RuntimeError('Release archive incomplete')
    backup.mkdir(mode=0o700);dump=backup/'rhisseth.dump'
    with dump.open('wb') as stream:
        result=subprocess.run(['runuser','-u','postgres','--','pg_dump','-Fc','-d','rhisseth'],stdout=stream,stderr=subprocess.PIPE,timeout=300)
    emit(f'pg_dump: exit_code={result.returncode}; bytes={dump.stat().st_size if dump.exists() else 0}; output suppressed')
    if result.returncode or dump.stat().st_size<1024:raise RuntimeError('Production backup failed')
    dump.chmod(0o600);run(['pg_restore','--list',str(dump)],quiet=True);shutil.copytree(REPO,old,symlinks=True)
    testdb='rhisseth_e041_'+secrets.token_hex(4)
    appenv={**os.environ,'DB_HOST':'127.0.0.1','DB_PASSWORD_FILE':str(ROOT/'secrets/db-password.txt')}
    try:
        run(['runuser','-u','postgres','--','createdb',testdb])
        run(['runuser','-u','postgres','--','pg_restore','-d',testdb,str(dump)],timeout=300)
        run([str(python),str(stage/'app/backend/migrate.py')],env={**appenv,'DB_NAME':testdb})
        if psql(testdb,"SELECT count(*) FROM schema_migrations WHERE name='046_population_tax_history.sql'")!='1':raise RuntimeError('Migration 046 missing in restored copy')
        if psql(testdb,"SELECT count(*) FROM information_schema.tables WHERE table_name IN ('hex_economy_history','hex_population_events','hex_economy_state','game_population_years')")!='4':raise RuntimeError('Economy tables missing in restored copy')
        emit('Restored-copy validation: migration 046 and four tables verified')
    finally:
        run(['runuser','-u','postgres','--','dropdb','--if-exists',testdb])
    stopped=False;swapped=False
    try:
        run(['systemctl','stop','rhisseth']);stopped=True
        run([str(python),str(stage/'app/backend/migrate.py')],env=appenv)
        if psql('rhisseth',"SELECT count(*) FROM schema_migrations WHERE name='046_population_tax_history.sql'")!='1':raise RuntimeError('Production migration 046 missing')
        turn=int(psql('rhisseth','SELECT turn_number FROM game_clock WHERE id=true'))
        last_year=(turn-3)//4 if turn>=3 else None
        if last_year is not None and psql('rhisseth',f'SELECT count(*) FROM game_population_years WHERE year={last_year}')=='0':
            code=("import sys;sys.path.insert(0,"+repr(str(stage/'app/backend'))+");"
                  "from db import connect;from game_clock import _annual_population_and_tax;"
                  f"c=connect();c.execute('INSERT INTO game_population_years(year) VALUES (%s)',({last_year},));"
                  f"_annual_population_and_tax(c,{last_year});c.commit();c.close();print('backfilled year {last_year}')")
            run([str(python),'-c',code],env=appenv,timeout=300)
        history=int(psql('rhisseth','SELECT count(*) FROM hex_economy_history'))
        if history<1:raise RuntimeError('Population/tax history remains empty')
        REPO.rename(backup/'repository-swapped')
        try:stage.rename(REPO);swapped=True
        except Exception:(backup/'repository-swapped').rename(REPO);raise
        run(['systemctl','start','rhisseth']);stopped=False
        for _ in range(30):
            health=subprocess.run(['curl','--max-time','2','-sS','-o','/dev/null','-w','%{http_code}','http://127.0.0.1:8080/health'],capture_output=True,text=True)
            if health.returncode==0 and health.stdout=='200':break
            time.sleep(1)
        else:raise RuntimeError('Application health failed')
        emit(f'Validation: history_rows={history}; backfill_year={last_year}; health=200; backup={dump}; reboot=false')
    except Exception:
        if swapped:
            run(['systemctl','stop','rhisseth']);stopped=True
            REPO.rename(ROOT/('repository.economy-v041-failed-'+STAMP));(backup/'repository-swapped').rename(REPO)
        if stopped:run(['systemctl','start','rhisseth'])
        emit(f'Failure recovery: verified database backup retained at {dump}; no automatic DB restore')
        raise

try:main();code=0
except Exception as error:emit(f'Failure: {type(error).__name__}: {error}');code=1
finally:emit(f'Final exit_code={code}; host_reboot=false; player_reset=false')
sys.exit(code)
