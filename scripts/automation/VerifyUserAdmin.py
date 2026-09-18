"""Check administration on an isolated restored database only."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

stage=Path(sys.argv[1]); database=sys.argv[2]
if database!='rhisseth_user_admin_check': raise SystemExit('Disposable database required')
os.environ['DB_NAME']=database
sys.path.insert(0,str(stage/'app/backend'))
import json
import subprocess
import time
import urllib.request
import urllib.error
import atexit
process=subprocess.Popen([sys.executable,'-m','uvicorn','main:app','--host','127.0.0.1','--port','18081','--app-dir',str(stage/'app/backend')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=os.environ.copy())
atexit.register(lambda: (process.terminate(),process.wait(timeout=10)))
for attempt in range(40):
    try:
        urllib.request.urlopen('http://127.0.0.1:18081/index.php',timeout=1).close();break
    except OSError: time.sleep(.25)
else: raise RuntimeError('Isolated server did not start')
class Cookies:
    def set(self,name,value): self.value=name+'='+value
class Result:
    def __init__(self,response):
        self.status_code=response.code;self.body=response.read()
    def json(self): return json.loads(self.body)
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args): return None
class TestClient:
    def __init__(self,*args,**kwargs):
        self.cookies=Cookies();self.opener=urllib.request.build_opener(NoRedirect())
    def call(self,path,method='GET',json=None,headers=None):
        headers={**(headers or {}),'Cookie':self.cookies.value,'Content-Type':'application/json'}
        req=urllib.request.Request('http://127.0.0.1:18081'+path,data=__import__('json').dumps(json).encode() if json is not None else None,headers=headers,method=method)
        try: response=self.opener.open(req,timeout=10)
        except urllib.error.HTTPError as error: response=error
        return Result(response)
    def get(self,path): return self.call(path)
    def patch(self,path,**kwargs): return self.call(path,'PATCH',**kwargs)

from main import app
from db import connect
from site_auth import new_session, COOKIE

with connect() as conn:
    roles=dict(conn.execute('SELECT role_alias,role_id FROM roles').fetchall())
    ids={}
    for role in ('admin','moderator','user'):
        ids[role]=conn.execute('INSERT INTO users(user_login,user_pass,user_email,role_id) VALUES (%s,%s,%s,%s) RETURNING user_id',('admin-check-'+role,'unused',role+'@check.invalid',roles[role])).fetchone()[0]
client=TestClient(app,base_url='https://testserver')
for role in ('moderator','user'):
    token,csrf=new_session(ids[role]);client.cookies.set(COOKIE,token)
    for path in ('/admin','/admin/','/admin/users','/api/admin/users'):
        assert client.get(path).status_code==403, (role,path)
    assert client.patch('/api/admin/users/'+str(ids['user']),json={},headers={'X-CSRF-Token':csrf}).status_code==403
    assert client.get('/admin/hexes').status_code==(200 if role=='moderator' else 403)
token,csrf=new_session(ids['admin']);client.cookies.set(COOKIE,token)
assert client.get('/admin/users').status_code==200
data=client.get('/api/admin/users?q=admin-check-user').json();assert data['total']==1
u=data['users'][0];expected={k:u[k] for k in ('login','email','role')}
payload={**expected,'login':'admin-check-renamed','role':'moderator','expected':expected}
url='/api/admin/users/'+str(u['id'])
assert client.patch(url,json=payload).status_code==403
assert client.patch(url,json=payload,headers={'X-CSRF-Token':csrf}).status_code==200
assert client.patch(url,json=payload,headers={'X-CSRF-Token':csrf}).status_code==409
with connect() as conn:
    assert conn.execute('SELECT count(*) FROM user_admin_audit WHERE target_id=%s',(u['id'],)).fetchone()[0]==1
    assert conn.execute('SELECT count(*) FROM user_sessions WHERE user_id=%s',(u['id'],)).fetchone()[0]==0
own=client.get('/api/admin/users?q=admin-check-admin').json()['users'][0]
expected={k:own[k] for k in ('login','email','role')}
assert client.patch('/api/admin/users/'+str(own['id']),json={**expected,'role':'user','expected':expected},headers={'X-CSRF-Token':csrf}).status_code==409
assert client.patch(url,json={'login':'x','email':'bad','role':'owner','expected':{}},headers={'X-CSRF-Token':csrf}).status_code==400
# Password reset is tested only with disposable synthetic accounts.
from site_auth import verify_password, token_hash
current=client.get('/api/admin/users?q=admin-check-renamed').json()['users'][0]
expected={k:current[k] for k in ('login','email','role')}
payload={**expected,'expected':expected,'password':'synthetic-new-password','password_confirm':'different'}
assert client.patch(url,json=payload,headers={'X-CSRF-Token':csrf}).status_code==400
payload['password_confirm']=payload['password']
assert client.patch(url,json=payload).status_code==403
with connect() as conn:
    original=conn.execute('SELECT user_pass FROM users WHERE user_id=%s',(u['id'],)).fetchone()[0]
assert original=='unused'
user_token,_=new_session(u['id'])
assert client.patch(url,json=payload,headers={'X-CSRF-Token':csrf}).status_code==200
with connect() as conn:
    stored=conn.execute('SELECT user_pass FROM users WHERE user_id=%s',(u['id'],)).fetchone()[0]
    assert verify_password(payload['password'],stored)
    assert not verify_password('incorrect',stored)
    assert conn.execute('SELECT count(*) FROM user_sessions WHERE user_id=%s',(u['id'],)).fetchone()[0]==0
    fields=conn.execute('SELECT changed_fields FROM user_admin_audit WHERE target_id=%s ORDER BY id DESC LIMIT 1',(u['id'],)).fetchone()[0]
    assert fields==['password']
empty={**expected,'expected':expected,'password':'','password_confirm':''}
assert client.patch(url,json=empty,headers={'X-CSRF-Token':csrf}).status_code==200
with connect() as conn: assert conn.execute('SELECT user_pass FROM users WHERE user_id=%s',(u['id'],)).fetchone()[0]==stored
for password in ('short','я'*37):
    assert client.patch(url,json={**empty,'password':password,'password_confirm':password},headers={'X-CSRF-Token':csrf}).status_code==400
own=client.get('/api/admin/users?q=admin-check-admin').json()['users'][0]
expected={k:own[k] for k in ('login','email','role')}
response=client.patch('/api/admin/users/'+str(own['id']),json={**expected,'expected':expected,'password':'synthetic-own-password','password_confirm':'synthetic-own-password'},headers={'X-CSRF-Token':csrf})
assert response.status_code==200 and response.json()['reauthenticate']
assert client.get('/api/admin/users').status_code==401
# A deletion releases ownership, removes the one starting barony and preserves a sanitized audit event.
token,csrf=new_session(ids['admin']);client.cookies.set(COOKIE,token)
with connect() as conn:
    from psycopg.types.json import Jsonb
    barony=conn.execute("INSERT INTO player_baronies(user_id,name) VALUES (%s,%s) RETURNING id",(u['id'],'Synthetic barony')).fetchone()[0]
    conn.execute("INSERT INTO hexes(q,r,data) VALUES (901,901,%s)", (Jsonb({'Q':'901','R':'901','Тип владельца':'Игрок','Владелец':str(u['id']),'Название территории':'Synthetic barony','ID территории':str(barony)}),))
deleted=client.call(url,'DELETE',headers={'X-CSRF-Token':csrf})
assert deleted.status_code==200 and deleted.json()['released_hexes']==1
with connect() as conn:
    assert not conn.execute('SELECT 1 FROM users WHERE user_id=%s',(u['id'],)).fetchone()
    assert not conn.execute('SELECT 1 FROM player_baronies WHERE user_id=%s',(u['id'],)).fetchone()
    row=conn.execute('SELECT data FROM hexes WHERE q=901 AND r=901').fetchone()[0]
    assert row['Тип владельца']=='Ничейная территория' and row['Владелец']=='' and row['ID территории']==''
    audit=conn.execute("SELECT actor_id,target_id,target_login,changed_fields FROM user_admin_audit WHERE changed_fields=%s",(Jsonb(['deleted']),)).fetchone()
    assert audit[0]==ids['admin'] and audit[1] is None and audit[2]=='admin-check-renamed' and audit[3]==['deleted']
assert client.call('/api/admin/users/'+str(ids['admin']),'DELETE',headers={'X-CSRF-Token':csrf}).status_code==409
print('PASS: account deletion; sessions/barony removed; player hexes neutralized; retained sanitized audit; own-account deletion denied')
print('PASS: password hash and verification; confirmation; length including UTF-8 bytes; CSRF; empty preserves hash; password-only audit; all sessions revoked; own reset requires login')
print('PASS: roles; moderator map access; admin-only accounts; search; CSRF; edit; stale conflict; session revocation; audit; self-demotion; validation')
