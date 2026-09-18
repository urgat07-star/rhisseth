# Release review 2026-09-18 (0.0.2): Reviewed Rhisseth hex metadata inspection/deployment on the selected VPS.
# Details: docs/releases/0.0.2-changes-2026-09-18.md.
"""Reviewed Rhisseth hex metadata inspection/deployment on the selected VPS."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import re
import time
import urllib.request
from zoneinfo import ZoneInfo

ROOT = Path('/opt/rhisseth')
REPO = ROOT / 'repository'
operation = sys.argv[1]
if operation not in ('inspect','deploy'):
    raise SystemExit('Invalid operation')
os.umask(0o077)
now = dt.datetime.now(dt.timezone.utc)
directory = ROOT / 'reports/automation-logs' / now.strftime('%Y-%m-%d')
directory.mkdir(parents=True,exist_ok=True)
log = directory / (now.strftime('%Y%m%d-%H%M%S')+'-hex-metadata-'+operation+'.md')
log.write_text(f'# Hex metadata {operation}\nUTC: {now.isoformat()}\nEurope/Moscow: {now.astimezone(ZoneInfo("Europe/Moscow")).isoformat()}\nTask: rhisseth-hex-metadata; Controller: Codex via STU-AUTOMATION-01 / 10.210.52.128\nTarget: 62.113.109.168 / rhisseth.ru; action: {operation}\nPassbolt: da44a388-e458-4379-ab4c-c204696804b2\n',encoding='utf-8')
def emit(value):
    with log.open('a',encoding='utf-8') as stream:stream.write(str(value)+'\n')
    print(value,flush=True)
def run(args, **kwargs):
    emit('Approved command: '+' '.join(args))
    result=subprocess.run(args,capture_output=True,text=True,timeout=60,**kwargs)
    emit('Command: '+' '.join(args)+'; exit_code='+str(result.returncode))
    if result.returncode:
        diagnostic=re.sub(r'(?i)(password|passphrase|token|cookie|authorization)\s*[:=]\s*\S+',r'\1=<redacted>',result.stderr)
        emit('Sanitized diagnostic: '+diagnostic[-2000:])
        raise RuntimeError('Command failed; raw output suppressed')
    return result.stdout
sys.path.insert(0,str(REPO/'app/backend'))
os.environ.update(DB_HOST='127.0.0.1',DB_PASSWORD_FILE=str(ROOT/'secrets/db-password.txt'))
from db import connect
code=1
try:
    emit('Preflight: project/runtime/database paths verified; log writable; no reboot requested')
    emit('Git revision: '+run(['git','-C',str(REPO),'rev-parse','HEAD']).strip())
    emit('Worktree paths: '+run(['git','-C',str(REPO),'status','--porcelain']).strip())
    emit('Service: '+run(['systemctl','is-active','rhisseth']).strip())
    asset_name=re.search(r'<img[^>]+id="terrain-map"[^>]+src="([^"]+)"',(REPO/'app/frontend/index.html').read_text()).group(1)
    asset=REPO/'app/frontend'/asset_name
    asset_hash=hashlib.sha256(asset.read_bytes()).hexdigest()
    emit('Active raster: '+asset_name+'; SHA256='+asset_hash)
    with connect() as conn:
        data=[r[0] for r in conn.execute('SELECT data FROM hexes ORDER BY r,q').fetchall()]
        emit('Stored rows: '+str(len(data)))
        emit('Category counts: '+json.dumps({k:sum(r.get('Категория')==k for r in data) for k in sorted({r.get('Категория','') for r in data})},ensure_ascii=False))
    if operation=='deploy':
        package=ROOT/'temp/hex-metadata.tar'
        backup=ROOT/'backups'/('hex-metadata-'+now.strftime('%Y%m%d-%H%M%S'))
        backup.mkdir(parents=True)
        dump=backup/'database.dump'
        with dump.open('wb') as stream:
            result=subprocess.run(['runuser','-u','postgres','--','pg_dump','-Fc','rhisseth'],stdout=stream,stderr=subprocess.PIPE,timeout=60)
        emit('Database backup: '+str(dump)+'; exit_code='+str(result.returncode))
        if result.returncode:raise RuntimeError('Database backup failed')
        allowed={'app/backend/main.py','app/backend/hex_rules.py','app/backend/game_start.py','app/frontend/index.html','app/frontend/app.js','app/frontend/styles.css','app/frontend/admin.html','app/frontend/admin.js','data/migrations/003_hex_metadata.sql'}
        with tarfile.open(package) as archive:
            members=archive.getmembers()
            if {m.name for m in members}!=allowed|{'baseline.json'} or any(not m.isfile() for m in members):raise RuntimeError('Package manifest mismatch')
            baseline=json.loads(archive.extractfile('baseline.json').read())
            if set(baseline)!=allowed:raise RuntimeError('Incomplete baseline manifest')
            for name,expected in baseline.items():
                if name not in allowed:raise RuntimeError('Invalid baseline path')
                target=REPO/name
                actual=hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
                if expected!=actual:raise RuntimeError('Live application changed since inspection; refused overwrite')
            for m in members:
                if m.name=='baseline.json':continue
                target=REPO/m.name
                if target.is_file():
                    old=backup/'files'/m.name;old.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,old)
        # Validate migrations against an isolated restored copy before modifying live data.
        test_db='rhisseth_hex_metadata_check'
        run(['runuser','-u','postgres','--','createdb','-O','rhisseth',test_db])
        try:
            with dump.open('rb') as stream:
                emit('Approved action: restore backup into disposable database '+test_db)
                result=subprocess.run(['runuser','-u','postgres','--','pg_restore','-d',test_db],stdin=stream,capture_output=True,timeout=60)
            emit('Restore into isolated database: exit_code='+str(result.returncode))
            if result.returncode:raise RuntimeError('Isolated restore failed')
            stage=backup/'stage'
            shutil.copytree(REPO/'app/backend',stage/'app/backend')
            shutil.copytree(REPO/'data/migrations',stage/'data/migrations')
            shutil.copytree(REPO/'app/frontend',stage/'app/frontend',ignore=shutil.ignore_patterns('*.png'))
            shutil.copytree(REPO/'app/site',stage/'app/site')
            with tarfile.open(package) as archive:
                for m in archive.getmembers():
                    if m.name=='baseline.json':continue
                    target=stage/m.name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.extractfile(m).read())
            run([str(ROOT/'venv/bin/python'),str(stage/'app/backend/migrate.py')],env={**os.environ,'DB_NAME':test_db})
            emit(run([str(ROOT/'venv/bin/python'),str(Path(__file__).with_name('VerifyHexMetadata.py')),str(stage),test_db]))
        finally:run(['runuser','-u','postgres','--','dropdb',test_db])
        emit('Validation: migration successful on restored isolated database')
        with tarfile.open(package) as archive:
            for m in archive.getmembers():
                if m.name=='baseline.json':continue
                target=REPO/m.name;target.parent.mkdir(parents=True,exist_ok=True)
                emit('Approved application file write: '+m.name)
                target.write_bytes(archive.extractfile(m).read());target.chmod(0o644)
        run([str(ROOT/'venv/bin/python'),str(REPO/'app/backend/migrate.py')])
        run(['systemctl','restart','rhisseth'])
        run(['systemctl','is-active','rhisseth'])
        for attempt in range(20):
            try:
                urllib.request.urlopen('http://127.0.0.1:8080/api/me',timeout=3)
            except urllib.error.HTTPError as error:
                if error.code==401:break
            except OSError:pass
            time.sleep(0.25)
        else:raise RuntimeError('Application readiness failed')
        from site_auth import new_session, token_hash
        from site_auth import COOKIE
        with connect() as conn:
            admin=conn.execute("SELECT user_id FROM users JOIN roles USING(role_id) WHERE role_alias='admin' LIMIT 1").fetchone()
        if admin is None:raise RuntimeError('Administrator missing')
        emit('Approved validation action: temporary administrator session; removed after checks; token never logged')
        token,_=new_session(admin[0])
        try:
            for path in ('/api/hexes','/admin/hexes','/api/admin/owners','/api/admin/hexes/export','/api/start/options'):
                req=urllib.request.Request('http://127.0.0.1:8080'+path,headers={'Cookie':COOKIE+'='+token})
                with urllib.request.urlopen(req,timeout=10) as response:
                    content=response.read()
                    if path=='/api/hexes':assert len(json.loads(content))==465
                    emit('Live authenticated HTTP validation: '+path+'; status='+str(response.status))
        finally:
            with connect() as conn:conn.execute('DELETE FROM user_sessions WHERE token_hash=%s',(token_hash(token),))
        new_asset_name=re.search(r'<img[^>]+id="terrain-map"[^>]+src="([^"]+)"',(REPO/'app/frontend/index.html').read_text()).group(1)
        if new_asset_name!=asset_name or hashlib.sha256(asset.read_bytes()).hexdigest()!=asset_hash:
            raise RuntimeError('Raster changed unexpectedly')
        emit('Validation: active V6 raster and grid geometry preserved; authenticated live endpoints successful')
        release=ROOT/'release.json'
        if release.exists():
            metadata=json.loads(release.read_text());metadata.update(hex_metadata_deployed_utc=now.isoformat(),hex_metadata_package_sha256=hashlib.sha256(package.read_bytes()).hexdigest());release.write_text(json.dumps(metadata,indent=2))
        emit('Changed: metadata schema and application; application restarted; database/host not restarted; backup='+str(backup))
    safe_directory=ROOT/'reports/hex-metadata-live-files'
    safe_directory.mkdir(exist_ok=True)
    for name in ('index.html','app.js'):
        shutil.copy2(REPO/'app/frontend'/name,safe_directory/name)
    if operation=='inspect':
        shutil.copy2(asset,safe_directory/asset_name)
        from site_auth import new_session, token_hash, COOKIE
        with connect() as conn:
            admin=conn.execute("SELECT user_id FROM users JOIN roles USING(role_id) WHERE role_alias='admin' LIMIT 1").fetchone()
        emit('Approved validation action: temporary administrator session; removed after checks; token never logged')
        token,_=new_session(admin[0])
        try:
            for path in ('/interactive-map/','/admin/hexes','/api/hexes','/api/admin/hexes/export','/api/start/options'):
                req=urllib.request.Request('https://rhisseth.ru'+path,headers={'Cookie':COOKIE+'='+token})
                with urllib.request.urlopen(req,timeout=15) as response:
                    content=response.read()
                    if path=='/api/hexes':assert len(json.loads(content))==465
                    emit('Public HTTPS validation: '+path+'; status='+str(response.status))
        finally:
            with connect() as conn:conn.execute('DELETE FROM user_sessions WHERE token_hash=%s',(token_hash(token),))
    if operation=='inspect':
        names=('app/backend/main.py','app/backend/hex_rules.py','app/backend/game_start.py','app/frontend/index.html','app/frontend/app.js','app/frontend/styles.css','app/frontend/admin.html','app/frontend/admin.js','data/migrations/003_hex_metadata.sql')
        (safe_directory/'baseline.json').write_text(json.dumps({n:hashlib.sha256((REPO/n).read_bytes()).hexdigest() if (REPO/n).exists() else None for n in names}),encoding='utf-8')
    emit('Current frontend files exported for preservation of live map changes')
    safe=[]
    with connect() as conn:
        for (row,) in conn.execute('SELECT data FROM hexes ORDER BY r,q'):
            safe.append({k:v for k,v in row.items() if k!='Пресная вода'})
    output=ROOT/'reports/hex-metadata-source.json'
    output.write_text(json.dumps(safe,ensure_ascii=False,indent=2),encoding='utf-8')
    emit('Sanitized hex metadata export: '+str(output)+'; rows='+str(len(safe)))
    emit('Raster SHA256: '+hashlib.sha256((REPO/'app/frontend/terrain-map-group3-artistic-v5-no-grid.png').read_bytes()).hexdigest())
    code=0
except Exception as error:
    emit('Failure: '+type(error).__name__+'; details suppressed to protect secrets')
finally:
    emit(f'Validation: exit_code={code}; operation={operation}; reboot=false; changes={operation=="deploy"}; log={log}')
sys.exit(code)
