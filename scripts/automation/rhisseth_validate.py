#!/usr/bin/python3
# Release review 2026-09-18 (0.0.2): Meaningful recovery verification using synthetic accounts, private secrets.
# Details: docs/releases/0.0.2-changes-2026-09-18.md.
"""Meaningful recovery verification using synthetic accounts, private secrets."""
import argparse
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import re
import secrets
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path('/opt/rhisseth')
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config',default='/etc/rhisseth/instance.json')
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    sys.path.insert(0,str(ROOT/'repository/app/backend'))
    os.environ.update(DB_HOST='127.0.0.1',DB_PASSWORD_FILE=str(ROOT/'secrets/db-password.txt'))
    from db import connect
    import bcrypt
    context = ssl.create_default_context(cafile=str(ROOT/'secrets/tls.crt')) if config['tls_mode']=='test' else ssl.create_default_context()
    # Test certificate includes target IP; hostname verification stays enabled.
    base = 'https://'+(config['test_ip'] if config['tls_mode']=='test' else config['domain'])
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):
            return None
    def client():
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context),urllib.request.HTTPCookieProcessor(jar),NoRedirect())
        def request(path,payload=None,method=None,csrf=None):
            headers = {'Host':config['domain']}
            data = None
            if payload is not None:
                if path.startswith('/api/'):
                    data = json.dumps(payload,ensure_ascii=False).encode()
                    headers['Content-Type']='application/json'
                else:
                    data = urllib.parse.urlencode(payload).encode()
                    headers['Content-Type']='application/x-www-form-urlencoded'
            if csrf:
                headers['X-CSRF-Token']=csrf
            req = urllib.request.Request(base+path,data=data,headers=headers,method=method)
            try:
                with opener.open(req,timeout=15) as response:
                    return response.status,response.read(),response.headers
            except urllib.error.HTTPError as error:
                return error.code,error.read(),error.headers
        return request,jar
    def require(condition,label):
        if not condition:
            raise RuntimeError(label)
    anonymous,_ = client()
    require(anonymous('/api/hexes')[0]==401,'Anonymous API access must be denied')
    require(anonymous('/interactive-map/')[0]==303,'Anonymous map must redirect')
    for path in ('/index.php','/register.php','/site/css/style.css','/site/img/logo.webp'):
        require(anonymous(path)[0]==200,'Public page/static asset '+path)
    for path in ('/secrets/app.env','/temp/sql-bkp.zip','/data/import/hex-initial-parameters.csv','/conn.php'):
        require(anonymous(path)[0]==404,'Private path exposed')
    metadata = json.loads((ROOT/'recovery.json').read_text())
    with connect() as conn:
        if metadata['source_manifest'].get('signature_timezone')=='UTC':
            conn.execute("SET LOCAL TIME ZONE 'UTC'")
        actual_sha = __import__('subprocess').check_output(['git','-C',str(ROOT/'repository'),'rev-parse','HEAD'],text=True).strip()
        require(actual_sha==metadata['release']['sha'],'Application SHA differs')
        # Expired/session rows can change on page visits; all durable tables stay comparable.
        for table,expected in metadata['source_manifest']['table_signatures'].items():
            if table in ('user_sessions','schema_migrations'):
                continue
            require(bool(re.fullmatch('[a-zA-Z_][a-zA-Z0-9_]*',table)),'Invalid table')
            ordering = 'row_value COLLATE "C"' if metadata['source_manifest'].get('signature_order')=='C' else 'row_value'
            statement = f'''SELECT count(*), md5(COALESCE(string_agg(row_value, E'\\n' ORDER BY {ordering}),'')) FROM (SELECT row_to_json(t)::text AS row_value FROM "{table}" t) s'''
            count,checksum = conn.execute(statement).fetchone()
            require(f'{count}|{checksum}'==expected,'Durable table signature '+table)
        durable_before = {table:conn.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('hexes','users','roles')}
    prefix = 'recoverycheck_'+secrets.token_hex(6)
    password = secrets.token_urlsafe(24)
    stored = bcrypt.hashpw(password.encode(),bcrypt.gensalt(rounds=12)).decode()
    names = []
    original_hex = None
    try:
        with connect() as conn:
            for alias in ('admin','moderator','user'):
                role = conn.execute('SELECT role_id FROM roles WHERE role_alias=%s',(alias,)).fetchone()
                require(role is not None,'Missing role '+alias)
                name = prefix+'_'+alias
                names.append(name)
                conn.execute('INSERT INTO users(user_login,user_pass,user_email,role_id) VALUES (%s,%s,%s,%s)',(name,stored,name+'@invalid.test',role[0]))
            row = conn.execute('SELECT q,r,data,updated_at FROM hexes WHERE q=0 AND r=0').fetchone()
            require(row is not None,'No map data')
            original_hex = row
        for alias,name in zip(('admin','moderator','user'),names):
            request,jar = client()
            csrf = re.search(rb'name="csrf" value="([a-f0-9]+)"',request('/index.php')[1])[1].decode()
            require(request('/index.php',{'login':name,'password':password,'csrf':csrf})[0]==303,'Login '+alias)
            identity = json.loads(request('/api/me')[1])
            require(identity['role']==alias,'Role '+alias)
            require(all(c.secure and c.has_nonstandard_attr('HttpOnly') for c in jar),'Session cookie flags')
            require(request('/health')[0]==200,'Authenticated DB health')
            require(request('/interactive-map/')[0]==200,'Map page')
            for path in ('/interactive-map/app.js','/interactive-map/styles.css'):
                require(request(path)[0]==200,'Map static asset')
            rows = json.loads(request('/api/hexes')[1])
            require(len(rows)==durable_before['hexes'],'API row count')
            endpoint = f'/api/hexes/{original_hex[0]}/{original_hex[1]}'
            require(request(endpoint,{'Комментарий':prefix},method='PUT')[0]==403,'CSRF rejection')
            status = request(endpoint,{'Комментарий':prefix},method='PUT',csrf=identity['csrf'])[0]
            require(status==(403 if alias=='user' else 200),'Write permissions '+alias+'; HTTP='+str(status))
            if alias!='user':
                with connect() as conn:
                    require(conn.execute('SELECT data->>\'Комментарий\' FROM hexes WHERE q=%s AND r=%s',original_hex[:2]).fetchone()[0]==prefix,'Saved map change')
                    from psycopg.types.json import Jsonb
                    conn.execute('UPDATE hexes SET data=%s,updated_at=%s WHERE q=%s AND r=%s',(Jsonb(original_hex[2]),original_hex[3],*original_hex[:2]))
            require(request('/logout',{'csrf':identity['csrf']})[0]==303,'Logout')
            require(request('/api/me')[0]==401,'Session removed')
            print('PASS: login/map/API/CSRF/permissions/logout '+alias,flush=True)
        request,_ = client()
        csrf = re.search(rb'name="csrf" value="([a-f0-9]+)"',request('/register.php')[1])[1].decode()
        registered = prefix+'_registered'
        names.append(registered)
        form = {'login':registered,'email':registered+'@invalid.test','password':password,'password_confirm':password,'csrf':csrf,'role_id':'1'}
        require(request('/register.php',form)[0]==200,'Registration')
        require(request('/register.php',form)[0]==409,'Duplicate registration')
        require(request('/index.php',{'login':registered,'password':password,'csrf':csrf})[0]==303,'Registered user login')
        require(json.loads(request('/api/me')[1])['role']=='user','Registration cannot elevate role')
        print('PASS: registration/duplicate rejection/no role escalation',flush=True)
    finally:
        with connect() as conn:
            if original_hex:
                from psycopg.types.json import Jsonb
                conn.execute('UPDATE hexes SET data=%s,updated_at=%s WHERE q=%s AND r=%s',(Jsonb(original_hex[2]),original_hex[3],*original_hex[:2]))
            conn.execute('DELETE FROM users WHERE user_login=ANY(%s)',(names,))
        print('Cleanup: synthetic accounts removed; tested hex restored including timestamp',flush=True)
    with connect() as conn:
        for table,count in durable_before.items():
            require(conn.execute('SELECT count(*) FROM '+table).fetchone()[0]==count,'Final row count '+table)
    print('PASS: durable data matches backup; HTTPS certificate verified; private paths denied; counts unchanged',flush=True)
    print('Verified durable counts: '+json.dumps(durable_before),flush=True)
if __name__=='__main__':
    try:
        main()
    except Exception as error:
        print('FAIL: '+str(error) if isinstance(error,RuntimeError) else 'FAIL: '+type(error).__name__+'; private details suppressed',flush=True)
        raise SystemExit(1)
