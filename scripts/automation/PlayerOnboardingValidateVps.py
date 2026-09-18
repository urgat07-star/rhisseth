"""Validate the deployed release without migration or service restart."""
import datetime as dt
import os
from pathlib import Path
import sys
import urllib.request
import urllib.error
import json
from zoneinfo import ZoneInfo

root = Path('/opt/rhisseth')
now = dt.datetime.now(dt.timezone.utc)
directory = root / 'reports/automation-logs' / now.strftime('%Y-%m-%d')
directory.mkdir(parents=True, exist_ok=True)
log = directory / f'{now:%Y%m%d-%H%M%S}-player-onboarding-validate.md'
log.write_text(f'# Player onboarding validation\nUTC: {now.isoformat()}\nEurope/Moscow: {now.astimezone(ZoneInfo("Europe/Moscow")).isoformat()}\nTask: player-onboarding-release\nController: Codex\nRunner: STU-AUTOMATION-01 / 10.210.52.128\nTargets: 62.113.109.168; https://rhisseth.ru\nAction: read deployed files and HTTP endpoints; temporary validation session cleaned up\nPassbolt: da44a388-e458-4379-ab4c-c204696804b2\n',encoding='utf-8')
def emit(message):
    with log.open('a',encoding='utf-8') as stream: stream.write(message+'\n')
    print(message,flush=True)
os.environ.update(DB_HOST='127.0.0.1',DB_PASSWORD_FILE=str(root/'secrets/db-password.txt'))
sys.path.insert(0,str(root/'repository/app/backend'))
from db import connect
from site_auth import COOKIE,new_session,token_hash
code=0
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):return None
emit('Preflight: audit log writable; existing release only; no migration or restart')
crests=root/'repository/app/frontend/crests'
emit('Crest directory permissions: '+oct(crests.stat().st_mode & 0o777))
if sys.argv[1:] == ['repair-assets']:
    emit('Approved change: set public frontend crest directory permissions to 0755')
    crests.chmod(0o755)
with connect() as conn:
    admin=conn.execute("SELECT user_id FROM users JOIN roles USING(role_id) WHERE role_alias='admin' LIMIT 1").fetchone()
token,_=new_session(admin[0])
try:
    opener=urllib.request.build_opener(NoRedirect())
    for base in ('http://127.0.0.1:8080','https://rhisseth.ru'):
        try:opener.open(urllib.request.Request(base+'/index.php',headers={'Cookie':COOKIE+'='+token}),timeout=15)
        except urllib.error.HTTPError as error:
            emit('Authenticated administrator login redirect: status='+str(error.code)+'; location='+error.headers.get('Location',''))
            assert error.code==303 and error.headers.get('Location')=='/interactive-map/cabinet.html'
    for base in ('http://127.0.0.1:8080','https://rhisseth.ru'):
        for path in ('/api/me','/api/cabinet','/api/start/options','/api/start/options?random=true','/interactive-map/index.html','/interactive-map/create-barony.html','/interactive-map/cabinet.html','/interactive-map/cabinet.js','/interactive-map/crests/gerb_1.png'):
            emit('Checking: '+base+path)
            request=urllib.request.Request(base+path,headers={'Cookie':COOKIE+'='+token})
            try:
                with urllib.request.urlopen(request,timeout=15) as response:
                    content=response.read()
                    if path == '/interactive-map/index.html':
                        assert b'<a id="user-status" href="cabinet.html"' in content
                        assert b'app.js?v=player-onboarding-3' in content
                    if path == '/interactive-map/create-barony.html':
                        assert b'id="territory-name"' not in content
                        assert b'id="random-barony"' in content
                    if path == '/api/start/options?random=true':
                        result=json.loads(content)
                        if not result['started'] and result['random_cells']:
                            from hex_rules import connected
                            cells=[tuple(c) for c in result['random_cells']]
                            assert len(cells) in (2,3) and connected(cells)
                            assert set(cells)<={tuple(c) for c in result['available_cells']}
                    emit(f'HTTP status={response.status}; bytes={len(content)}; final URL={response.url}')
            except urllib.error.HTTPError as error:
                emit(f'HTTP status={error.code}; final URL={error.url}');code=1
            except Exception as error:
                emit('Failure type='+type(error).__name__);code=1
finally:
    with connect() as conn: conn.execute('DELETE FROM user_sessions WHERE token_hash=%s',(token_hash(token),))
emit(f'Validation: exit_code={code}; session cleaned up; reboot=false; application/database schema change=false; log={log}')
sys.exit(code)
