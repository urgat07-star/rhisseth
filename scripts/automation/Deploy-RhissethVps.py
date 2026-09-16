"""Reviewed first deployment; native PostgreSQL/systemd using existing nginx."""
import datetime as dt
import os
import base64
import csv
import hashlib
import json
from pathlib import Path
import re
import secrets
import shutil
import ssl
import subprocess
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
import http.cookiejar
from zoneinfo import ZoneInfo

ROOT = Path('/opt/rhisseth')
os.umask(0o077)
operation = sys.argv[1]
now = dt.datetime.now(dt.timezone.utc)
directory = ROOT / 'reports/automation-logs' / now.strftime('%Y-%m-%d')
directory.mkdir(parents=True, exist_ok=True)
log = directory / (now.strftime('%Y%m%d-%H%M%S') + '-' + operation + '.md')
log.write_text(f'# Rhisseth VPS {operation}\n\n- UTC: {now.isoformat()}\n- Europe/Moscow: {now.astimezone(ZoneInfo("Europe/Moscow")).isoformat()}\n- Controller: N7198 / Codex via STU-AUTOMATION-01 10.210.52.128\n- Target: rhisseth 62.113.109.168\n- Action: {operation}\n- Passbolt resource: da44a388-e458-4379-ab4c-c204696804b2 (SSH only)\n\n', encoding='utf-8')
def emit(text):
    with log.open('a', encoding='utf-8') as stream:
        stream.write(str(text) + '\n')
    print(text, flush=True)
def run(args, *, check=True, input=None, env=None, raw=False):
    emit('Command: ' + ' '.join(args))
    result = subprocess.run(args, input=input, env=env, capture_output=True, text=True)
    if not raw:
        emit(result.stdout.strip())
        emit(result.stderr.strip())
    emit('Exit code: ' + str(result.returncode))
    if check and result.returncode:
        raise RuntimeError('Command failed: ' + args[0])
    return result
def inspect():
    run(['hostname'])
    run(['free', '-m'])
    run(['df', '-h', '/'])
    run(['ss', '-lnt'])
    run(['nginx', '-t'])
    run(['systemctl', 'status', 'postgresql@16-main', '--no-pager'], check=False)
    run(['journalctl', '-u', 'postgresql@16-main', '-n', '15', '--no-pager'], check=False)
    config = run(['nginx', '-T'], raw=True).stdout
    for line in config.splitlines():
        if re.match(r'^# configuration file|^\s*(listen|server_name|root|ssl_certificate|include)\s', line):
            emit(line)
    run(['dpkg-query', '-W', '-f=${Package} ${Version}\n', 'git', 'postgresql', 'python3-venv', 'certbot'], check=False)
    run(['getent', 'ahostsv4', 'rhisseth.ru'], check=False)
    run(['git', 'ls-remote', 'https://github.com/urgat07-star/rhisseth.git', 'refs/heads/main'], env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
    run(['curl', '--max-time', '15', '-sS', '-o', '/dev/null', '-w', 'HTTP %{http_code}\n', '-H', 'Host: rhisseth.ru', 'http://127.0.0.1/'], check=False)
    run(['curl', '--max-time', '15', '-sS', '-o', '/dev/null', '-w', 'HTTPS %{http_code}\n', 'https://rhisseth.ru/'], check=False)

def sql(statement, *, secret=False):
    return run(['runuser', '-u', 'postgres', '--', 'psql', '-X', '-v', 'ON_ERROR_STOP=1', '-At'], input=statement, raw=secret).stdout.strip()

def install():
    emit('Change: package installation, isolated database, systemd API, nginx test virtual host; no reboot')
    if shutil.disk_usage('/').free < 2 * 1024**3:
        raise RuntimeError('Less than 2 GB free disk')
    repo = ROOT / 'repository'
    env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0'}
    if not repo.exists():
        run(['git', 'clone', 'https://github.com/urgat07-star/rhisseth.git', str(repo)], env=env)
    else:
        if run(['git', '-C', str(repo), 'status', '--porcelain'], raw=True).stdout.strip():
            raise RuntimeError('VPS repository has local changes; update refused')
        run(['git', '-C', str(repo), 'fetch', 'origin', 'main'], env=env)
        run(['git', '-C', str(repo), 'merge', '--ff-only', 'origin/main'])
    revision = run(['git', '-C', str(repo), 'rev-parse', 'HEAD']).stdout.strip()
    native = repo / 'deploy/native'
    if not (native / 'rhisseth.service').is_file():
        raise RuntimeError('Native deployment templates missing from Git release')
    backup = ROOT / 'backups' / now.strftime('%Y%m%d-%H%M%S')
    backup.mkdir(parents=True, exist_ok=True)
    backup.chmod(0o700)
    shutil.copytree('/etc/nginx', backup / 'nginx', dirs_exist_ok=True, symlinks=True)
    emit('Backup: original nginx configuration saved inside project')
    apt_env = {**os.environ, 'DEBIAN_FRONTEND': 'noninteractive', 'NEEDRESTART_MODE': 'l'}
    run(['apt-get', 'update'], env=apt_env)
    run(['apt-get', 'install', '-y', '--no-install-recommends', 'postgresql', 'python3-venv', 'apache2-utils', 'openssl', 'ca-certificates'], env=apt_env)
    if not run(['id', 'rhisseth'], check=False, raw=True).returncode == 0:
        run(['useradd', '--system', '--home-dir', str(ROOT), '--shell', '/usr/sbin/nologin', 'rhisseth'])
    secret_dir = ROOT / 'secrets'
    secret_dir.mkdir(exist_ok=True)
    secret_dir.chmod(0o711)
    password_file = secret_dir / 'db-password.txt'
    if not password_file.exists():
        password_file.write_text(secrets.token_urlsafe(36) + '\n')
    password_file.chmod(0o640)
    shutil.chown(password_file, user='root', group='rhisseth')
    password = password_file.read_text().strip()
    pg_config = Path('/etc/postgresql/16/main/conf.d/rhisseth.conf')
    if pg_config.exists():
        pg_config.chmod(0o644)
    run(['systemctl', 'enable', '--now', 'postgresql'])
    run(['systemctl', 'start', 'postgresql@16-main'])
    if sql("SELECT count(*) FROM pg_roles WHERE rolname='rhisseth';") == '0':
        sql('CREATE ROLE rhisseth LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD ' + "'" + password.replace("'", "''") + "';", secret=True)
    if sql("SELECT count(*) FROM pg_database WHERE datname='rhisseth';") == '0':
        sql('CREATE DATABASE rhisseth OWNER rhisseth;')
    version = sql('SHOW server_version;')
    emit('Database role permissions: ' + sql("SELECT rolname,rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname='rhisseth';"))
    if not version.startswith('16.'):
        raise RuntimeError('Expected Ubuntu PostgreSQL 16 for native test deployment')
    shutil.copy2(native / 'postgresql-test.conf', '/etc/postgresql/16/main/conf.d/rhisseth.conf')
    pg_config.chmod(0o644)
    run(['systemctl', 'restart', 'postgresql@16-main'])
    venv = ROOT / 'venv'
    if not (venv / 'bin/python').is_file():
        run(['python3', '-m', 'venv', str(venv)])
    run([str(venv / 'bin/pip'), 'install', '--disable-pip-version-check', '--no-cache-dir', '-r', str(repo / 'app/backend/requirements.lock')])
    # Code/runtime are non-secret and must be readable by the service user.
    # Secret and backup directories retain their separate restrictive modes.
    for tree in (repo, venv):
        for parent, directories, files in os.walk(tree):
            Path(parent).chmod(0o755)
            for name in files:
                file = Path(parent) / name
                if not file.is_symlink():
                    file.chmod(0o755 if file.stat().st_mode & 0o111 else 0o644)
    run(['runuser', '-u', 'rhisseth', '--', str(venv / 'bin/python'), '-c', 'import fastapi, psycopg; print("Service-user runtime access verified")'])
    app_env = {**os.environ, 'DB_HOST': '127.0.0.1', 'DB_PASSWORD_FILE': str(password_file)}
    run([str(venv / 'bin/python'), str(repo / 'app/backend/migrate.py')], env=app_env)
    count = run(['runuser', '-u', 'postgres', '--', 'psql', '-X', '-At', '-d', 'rhisseth', '-c', 'SELECT count(*) FROM hexes']).stdout.strip()
    if count == '0':
        run([str(venv / 'bin/python'), str(repo / 'app/backend/import_csv.py'), str(repo / 'data/import/hex-initial-parameters.csv')], env=app_env)
    else:
        emit('Existing map preserved: initial CSV import skipped')
    env_file = secret_dir / 'app.env'
    env_file.write_text('DB_HOST=127.0.0.1\nDB_PASSWORD_FILE=/opt/rhisseth/secrets/db-password.txt\n')
    env_file.chmod(0o600)
    web_password = secret_dir / 'web-password.txt'
    if not web_password.exists():
        web_password.write_text(secrets.token_urlsafe(24) + '\n')
    web_password.chmod(0o600)
    run(['htpasswd', '-iBc', str(secret_dir / 'web.htpasswd'), 'mapadmin'], input=web_password.read_text(), raw=True)
    (secret_dir / 'web.htpasswd').chmod(0o640)
    shutil.chown(secret_dir / 'web.htpasswd', user='root', group='www-data')
    if not (secret_dir / 'tls.crt').exists():
        run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '30', '-keyout', str(secret_dir / 'tls.key'), '-out', str(secret_dir / 'tls.crt'), '-subj', '/CN=62.113.109.168', '-addext', 'subjectAltName=IP:62.113.109.168,DNS:rhisseth.ru'], raw=True)
    (secret_dir / 'tls.key').chmod(0o600)
    shutil.copy2(native / 'rhisseth.service', '/etc/systemd/system/rhisseth.service')
    Path('/etc/systemd/system/rhisseth.service').chmod(0o644)
    shutil.copy2(native / 'nginx-logrotate.conf', '/etc/logrotate.d/rhisseth')
    run(['systemctl', 'daemon-reload'])
    run(['systemctl', 'enable', '--now', 'rhisseth'])
    run(['systemctl', 'restart', 'rhisseth'])
    for attempt in range(20):
        try:
            if urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3).status == 200:
                break
        except Exception:
            time.sleep(1)
    else:
        raise RuntimeError('API startup health failed')
    site = Path('/etc/nginx/sites-available/rhisseth')
    old_site = site.read_bytes() if site.exists() else None
    enabled = Path('/etc/nginx/sites-enabled/rhisseth')
    site.write_bytes((native / 'nginx.conf').read_bytes())
    if not enabled.exists():
        enabled.symlink_to(site)
    test = run(['nginx', '-t'], check=False)
    if test.returncode:
        if old_site is None:
            enabled.unlink(missing_ok=True)
            site.unlink(missing_ok=True)
        else:
            site.write_bytes(old_site)
        raise RuntimeError('nginx test failed; project vhost restored')
    run(['systemctl', 'reload', 'nginx'])
    (ROOT / 'release.json').write_text(json.dumps({'git_commit': revision, 'postgresql': version, 'deployed_utc': now.isoformat()}, indent=2))
    emit('Web access: HTTPS IP, username mapadmin; password retained in root-only /opt/rhisseth/secrets/web-password.txt (not logged)')
    validate()

def validate():
    if (ROOT/'repository/app/backend/site_auth.py').exists():
        return validate_hosting()
    context = ssl.create_default_context(cafile=str(ROOT / 'secrets/tls.crt'))
    password = (ROOT / 'secrets/web-password.txt').read_text().strip()
    auth = 'Basic ' + base64.b64encode(('mapadmin:' + password).encode()).decode()
    def request(path, payload=None, authorized=True):
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
        headers = {'Content-Type': 'application/json'}
        if authorized:
            headers['Authorization'] = auth
        req = urllib.request.Request('https://62.113.109.168' + path, data=data, headers=headers, method='GET' if data is None else 'PUT')
        try:
            with urllib.request.urlopen(req, context=context, timeout=15) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()
    for unit in ('postgresql@16-main', 'rhisseth', 'nginx'):
        run(['systemctl', 'is-active', unit])
    assert request('/health', authorized=False)[0] == 401
    assert request('/health')[0] == 200
    for path in ('/interactive-map/', '/interactive-map/app.js', '/interactive-map/styles.css', '/interactive-map/terrain-map-final-v2.png'):
        assert request(path)[0] == 200
    assert request('/data/import/hex-initial-parameters.csv')[0] == 404
    status, data = request('/api/hexes')
    assert status == 200
    rows = json.loads(data)
    with (ROOT / 'repository/data/import/hex-initial-parameters.csv').open(encoding='utf-8-sig', newline='') as stream:
        source = list(csv.DictReader(stream, delimiter=';'))
    assert {(r['Q'], r['R']): r for r in source} == {(r['Q'], r['R']): r for r in rows}
    emit(f'Validation: all {len(rows)} imported rows match every original CSV field')
    row = next(row for row in rows if row['Категория'] != 'Вне полотна')
    endpoint = f'/api/hexes/{row["Q"]}/{row["R"]}'
    original = row['Комментарий']
    marker = 'Rhisseth deployment persistence check ' + now.isoformat()
    try:
        assert request(endpoint, {'Защита': '99'})[0] == 400
        assert request('/api/hexes/99999/99999', {'Комментарий': ''})[0] == 404
        assert request(endpoint, {'Комментарий': marker})[0] == 200
        run(['systemctl', 'restart', 'rhisseth'])
        run(['systemctl', 'restart', 'postgresql@16-main'])
        for attempt in range(20):
            try:
                if request('/health')[0] == 200:
                    break
            except Exception:
                pass
            time.sleep(1)
        updated = json.loads(request('/api/hexes')[1])
        assert next(r for r in updated if (r['Q'], r['R']) == (row['Q'], row['R']))['Комментарий'] == marker
        emit('Validation: API edit persists after application and PostgreSQL restart')
    finally:
        assert request(endpoint, {'Комментарий': original})[0] == 200
        emit('Validation: temporary test edit restored')
    backups = ROOT / 'backups'
    backups.mkdir(exist_ok=True)
    backups.chmod(0o700)
    dump = backups / (now.strftime('%Y%m%d-%H%M%S') + '-rhisseth.dump')
    emit('Command: pg_dump rhisseth custom format to project backup (peer authentication)')
    with dump.open('wb') as stream:
        result = subprocess.run(['runuser', '-u', 'postgres', '--', 'pg_dump', '-d', 'rhisseth', '-Fc'], stdout=stream, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError('Backup failed; output suppressed')
    emit('Backup SHA256: ' + hashlib.sha256(dump.read_bytes()).hexdigest())
    restored_db = 'rhisseth_restore_' + secrets.token_hex(4)
    run(['runuser', '-u', 'postgres', '--', 'createdb', restored_db])
    try:
        emit('Command: pg_restore project backup into fresh isolated verification database')
        with dump.open('rb') as stream:
            restored = subprocess.run(['runuser', '-u', 'postgres', '--', 'pg_restore', '-d', restored_db, '--no-owner', '--no-acl', '--exit-on-error', '--single-transaction'], stdin=stream, capture_output=True)
        emit('Restore exit code: ' + str(restored.returncode))
        if restored.returncode:
            raise RuntimeError('Isolated backup restore failed')
        checksum_sql = "SELECT count(*), md5(string_agg(data::text, '' ORDER BY r,q)) FROM hexes"
        checksums = []
        for db in ('rhisseth', restored_db):
            checksums.append(run(['runuser', '-u', 'postgres', '--', 'psql', '-X', '-At', '-d', db, '-c', checksum_sql]).stdout.strip())
        assert checksums[0] == checksums[1]
        emit('Validation: backup restored in isolated database; all hex data checksums match')
    finally:
        run(['runuser', '-u', 'postgres', '--', 'dropdb', restored_db])
    run(['ss', '-lnt'])
    run(['free', '-m'])
    run(['df', '-h', '/'])
    run(['systemctl', 'show', 'rhisseth', 'postgresql@16-main', 'nginx', '--property=MemoryCurrent', '--property=NRestarts', '--property=ActiveState'])
    emit('Validation: nginx TLS, auth, static assets, database API, input validation, persistence and backup passed; no reboot')

def backup_database(label):
    directory = ROOT / 'backups'
    directory.mkdir(exist_ok=True)
    directory.chmod(0o700)
    target = directory / (now.strftime('%Y%m%d-%H%M%S') + '-' + label + '.dump')
    emit('Command: pg_dump project database before/after hosting migration (secret output suppressed)')
    with target.open('wb') as stream:
        result = subprocess.run(['runuser','-u','postgres','--','pg_dump','-d','rhisseth','-Fc'],stdout=stream,stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError('Database backup failed')
    emit(f'Backup: {target}; SHA256={hashlib.sha256(target.read_bytes()).hexdigest()}')
    return target

def hosting():
    emit('Approved change: restore hosting appearance and users/roles in existing PostgreSQL; preserve hex data')
    repo = ROOT / 'repository'
    old_revision = run(['git','-C',str(repo),'rev-parse','HEAD'],raw=True).stdout.strip()
    if run(['git','-C',str(repo),'status','--porcelain'],raw=True).stdout.strip():
        raise RuntimeError('Repository has local changes; update refused')
    backup_database('before-hosting')
    backup = ROOT / 'backups' / (now.strftime('%Y%m%d-%H%M%S') + '-before-hosting')
    backup.mkdir()
    backup.chmod(0o700)
    shutil.copytree('/etc/nginx',backup/'nginx',symlinks=True)
    emit('Backup: nginx configuration saved; previous Git SHA=' + old_revision)
    for name in ('hosting-bkp.zip','sql-bkp.zip'):
        file = ROOT / 'temp' / name
        file.chmod(0o600)
        emit('Source archive: ' + name + '; SHA256=' + hashlib.sha256(file.read_bytes()).hexdigest())
    env = {**os.environ,'GIT_TERMINAL_PROMPT':'0'}
    run(['git','-C',str(repo),'fetch','origin','main'],env=env)
    run(['git','-C',str(repo),'merge','--ff-only','origin/main'])
    revision = run(['git','-C',str(repo),'rev-parse','HEAD']).stdout.strip()
    venv = ROOT / 'venv'
    run([str(venv/'bin/pip'),'install','--no-cache-dir','--disable-pip-version-check','-r',str(repo/'app/backend/requirements.lock')])
    for tree in (repo,venv):
        for parent,directories,files in os.walk(tree):
            Path(parent).chmod(0o755)
            for name in files:
                file = Path(parent)/name
                if not file.is_symlink():
                    file.chmod(0o755 if file.stat().st_mode & 0o111 else 0o644)
    app_env = {**os.environ,'DB_HOST':'127.0.0.1','DB_PASSWORD_FILE':str(ROOT/'secrets/db-password.txt')}
    run([str(venv/'bin/python'),str(repo/'app/backend/migrate.py')],env=app_env)
    count = run(['runuser','-u','postgres','--','psql','-X','-At','-d','rhisseth','-c','SELECT count(*) FROM users']).stdout.strip()
    if count == '0':
        result = run([str(venv/'bin/python'),str(repo/'app/backend/import_users.py'),str(ROOT/'temp/sql-bkp.zip')],env=app_env,raw=True)
        counts = json.loads(result.stdout)
        emit(f'Imported account data: {counts["users"]} users, {counts["roles"]} roles; original hashes preserved')
    else:
        emit('Existing users preserved; account import skipped')
    site = Path('/etc/nginx/sites-available/rhisseth')
    previous = site.read_bytes()
    site.write_bytes((repo/'deploy/native/nginx.conf').read_bytes())
    site.chmod(0o644)
    if run(['nginx','-t'],check=False).returncode:
        site.write_bytes(previous)
        raise RuntimeError('New nginx configuration invalid; restored previous vhost')
    run(['systemctl','restart','rhisseth'])
    for attempt in range(30):
        result = run(['curl','--max-time','2','-sS','-o','/dev/null','-w','%{http_code}','http://127.0.0.1:8080/api/me'],check=False,raw=True)
        if result.stdout == '401':
            break
        time.sleep(1)
    else:
        site.write_bytes(previous)
        raise RuntimeError('New application startup failed; previous nginx config restored on disk')
    run(['systemctl','reload','nginx'])
    release = json.loads((ROOT/'release.json').read_text())
    release.update({'git_commit':revision,'hosting_deployed_utc':now.isoformat(),'account_source':'sql-bkp.zip'})
    (ROOT/'release.json').write_text(json.dumps(release,indent=2))
    validate_hosting()
    backup_database('after-hosting')
    emit('Validation: hosting, PostgreSQL accounts and role-controlled map deployed; no reboot')

def validate_hosting():
    repo = ROOT/'repository'
    sys.path.insert(0,str(repo/'app/backend'))
    from import_users import load_archive
    from db import connect
    import bcrypt
    os.environ['DB_HOST']='127.0.0.1'
    os.environ['DB_PASSWORD_FILE']=str(ROOT/'secrets/db-password.txt')
    imported = load_archive(ROOT/'temp/sql-bkp.zip')
    with connect() as conn:
        for table,rows in imported.items():
            for row in rows:
                key = 'user_id' if table == 'users' else 'role_id'
                columns = list(row)
                restored = conn.execute(f'SELECT {",".join(columns)} FROM {table} WHERE {key}=%s',(row[key],)).fetchone()
                if restored != tuple(row[c] for c in columns):
                    raise RuntimeError('Imported account data mismatch; fields suppressed')
    emit('Validation: all source account IDs, logins, emails, bcrypt hashes and role assignments preserved (values suppressed)')
    context = ssl.create_default_context(cafile=str(ROOT/'secrets/tls.crt'))
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):
            return None
    def client():
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context),urllib.request.HTTPCookieProcessor(jar),NoRedirect())
        def request(path, payload=None, *, method=None, csrf=None):
            headers = {}
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
            req = urllib.request.Request('https://62.113.109.168'+path,data=data,headers=headers,method=method or ('POST' if data else 'GET'))
            try:
                with opener.open(req,timeout=20) as response:
                    return response.status,response.read(),response.headers
            except urllib.error.HTTPError as error:
                return error.code,error.read(),error.headers
        return request,jar
    anonymous,_ = client()
    assert anonymous('/api/hexes')[0]==401
    assert anonymous('/interactive-map/')[0]==303
    status,body,_ = anonymous('/index.php')
    assert status==200 and 'Как вас представить'.encode() in body
    for path in ('/site/css/style.css','/site/img/logo.webp','/register.php'):
        assert anonymous(path)[0]==200
    for path in ('/conn.php','/temp/sql-bkp.zip','/map/.deploy-backups/anything','/data/import/hex-initial-parameters.csv'):
        assert anonymous(path)[0]==404
    assert anonymous('/index.php',{'login':'synthetic','password':'invalid','csrf':'invalid'})[0]==403
    prefix = 'deploycheck_' + secrets.token_hex(5)
    names = []
    password = secrets.token_urlsafe(24)
    stored = bcrypt.hashpw(password.encode(),bcrypt.gensalt(rounds=12)).decode()
    try:
        with connect() as conn:
            for alias in ('admin','moderator','user'):
                name = prefix+'_'+alias
                names.append(name)
                role = conn.execute('SELECT role_id FROM roles WHERE role_alias=%s',(alias,)).fetchone()[0]
                conn.execute('INSERT INTO users(user_login,user_pass,user_email,role_id) VALUES (%s,%s,%s,%s)',(name,stored,name+'@invalid.test',role))
        csrf_pattern = rb'name="csrf" value="([a-f0-9]+)"'
        for alias,name in zip(('admin','moderator','user'),names):
            request,jar = client()
            csrf = re.search(csrf_pattern,request('/index.php')[1])[1].decode()
            status,_,headers = request('/index.php',{'login':name,'password':password,'csrf':csrf})
            assert status==303 and headers['Location']=='/interactive-map/'
            assert all(cookie.secure and cookie.has_nonstandard_attr('HttpOnly') for cookie in jar)
            identity = json.loads(request('/api/me')[1])
            assert identity['role']==alias
            csrf = identity['csrf']
            assert request('/interactive-map/')[0]==200
            for path in ('/interactive-map/app.js','/interactive-map/styles.css','/interactive-map/terrain-map-final-v2.png'):
                assert request(path)[0]==200
            rows = json.loads(request('/api/hexes')[1])
            row = next(row for row in rows if row['Категория']!='Вне полотна')
            endpoint = f'/api/hexes/{row["Q"]}/{row["R"]}'
            original = row['Комментарий']
            assert request(endpoint,{'Комментарий':'blocked'},method='PUT')[0]==403
            if alias=='user':
                assert request(endpoint,{'Комментарий':'blocked'},method='PUT',csrf=csrf)[0]==403
                assert not identity['can_edit']
            else:
                assert request(endpoint,{'Комментарий':prefix},method='PUT',csrf=csrf)[0]==200
                try:
                    if alias=='admin':
                        run(['systemctl','restart','rhisseth'])
                        run(['systemctl','restart','postgresql@16-main'])
                        for attempt in range(30):
                            try:
                                if request('/api/me')[0]==200:
                                    break
                            except Exception:
                                pass
                            time.sleep(1)
                    updated = json.loads(request('/api/hexes')[1])
                    assert next(r for r in updated if (r['Q'],r['R'])==(row['Q'],row['R']))['Комментарий']==prefix
                finally:
                    assert request(endpoint,{'Комментарий':original},method='PUT',csrf=csrf)[0]==200
            assert request('/logout',{'csrf':csrf})[0]==303
            assert request('/api/hexes')[0]==401
            emit('Validation: '+alias+' login, map access, CSRF, permissions and logout passed')
        request,_ = client()
        csrf = re.search(csrf_pattern,request('/register.php')[1])[1].decode()
        name = prefix+'_registered'
        names.append(name)
        form = {'login':name,'email':name+'@invalid.test','password':password,'password_confirm':password,'csrf':csrf,'role_id':'1'}
        assert request('/register.php',form)[0]==200
        assert request('/register.php',form)[0]==409
        assert request('/index.php',{'login':name,'password':password,'csrf':csrf})[0]==303
        assert json.loads(request('/api/me')[1])['role']=='user'
        emit('Validation: registration, duplicate rejection and prevention of role escalation passed')
    finally:
        with connect() as conn:
            conn.execute('DELETE FROM users WHERE user_login=ANY(%s)',(names,))
        emit('Validation: synthetic accounts and their sessions removed; source users unchanged')
    with connect() as conn:
        emit('Final account/hex counts: '+str(conn.execute('SELECT (SELECT count(*) FROM users),(SELECT count(*) FROM roles),(SELECT count(*) FROM hexes)').fetchone()))
    for unit in ('rhisseth','postgresql@16-main','nginx'):
        run(['systemctl','is-active',unit])
    run(['free','-m'])
    run(['systemctl','show','rhisseth','postgresql@16-main','nginx','--property=MemoryCurrent','--property=NRestarts','--property=ActiveState'])

def audit_map():
    import math
    import bcrypt
    sys.path.insert(0,str(ROOT/'repository/app/backend'))
    from db import connect
    os.environ['DB_HOST']='127.0.0.1'
    os.environ['DB_PASSWORD_FILE']=str(ROOT/'secrets/db-password.txt')
    context=ssl.create_default_context(cafile=str(ROOT/'secrets/tls.crt'))
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):
            return None
    jar=http.cookiejar.CookieJar()
    opener=urllib.request.build_opener(urllib.request.HTTPSHandler(context=context),urllib.request.HTTPCookieProcessor(jar),NoRedirect())
    def request(path,payload=None):
        data=urllib.parse.urlencode(payload).encode() if payload else None
        req=urllib.request.Request('https://62.113.109.168'+path,data=data)
        try:
            with opener.open(req,timeout=25) as response:
                return response.status,response.read()
        except urllib.error.HTTPError as error:
            return error.code,error.read()
    name='mapaudit_'+secrets.token_hex(6)
    password=secrets.token_urlsafe(24)
    stored=bcrypt.hashpw(password.encode(),bcrypt.gensalt(rounds=12)).decode()
    try:
        with connect() as conn:
            role=conn.execute("SELECT role_id FROM roles WHERE role_alias='admin'").fetchone()[0]
            conn.execute('INSERT INTO users(user_login,user_pass,user_email,role_id) VALUES (%s,%s,%s,%s)',(name,stored,name+'@invalid.test',role))
        csrf=re.search(rb'name="csrf" value="([a-f0-9]+)"',request('/index.php')[1])[1].decode()
        if request('/index.php',{'login':name,'password':password,'csrf':csrf})[0]!=303:
            raise RuntimeError('Synthetic login validation failed')
        status,page=request('/interactive-map/')
        if status!=200 or b'terrain-map-group3-artistic-v5.png' not in page:
            raise RuntimeError('Authenticated map does not reference V5')
        status,asset=request('/interactive-map/terrain-map-group3-artistic-v5.png')
        expected=(ROOT/'repository/app/frontend/terrain-map-group3-artistic-v5.png').read_bytes()
        if status!=200 or hashlib.sha256(asset).digest()!=hashlib.sha256(expected).digest():
            raise RuntimeError('HTTPS PNG differs from published V5')
        status,body=request('/api/hexes')
        if status!=200:
            raise RuntimeError('Live hex API validation failed')
        rows={(int(row['Q']),int(row['R'])):row for row in json.loads(body)}
        covered=0
        missing=set()
        excluded=set()
        total=0
        for y in range(5,2200,10):
            for x in range(5,3200,10):
                r=y/120
                q=x/(math.sqrt(3)*80)-r/2
                s=-q-r
                rq,rr,rs=round(q),round(r),round(s)
                dq,dr,ds=abs(rq-q),abs(rr-r),abs(rs-s)
                if dq>dr and dq>ds:
                    rq=-rr-rs
                elif dr>ds:
                    rr=-rq-rs
                key=(rq,rr)
                total+=1
                if key not in rows:
                    missing.add(key)
                elif rows[key]['Категория']=='Вне полотна':
                    excluded.add(key)
                else:
                    covered+=1
        emit('Authenticated HTTPS: login, map HTML, V5 PNG SHA256 and live hex API passed; certificate explicitly trusted from pinned SSH')
        emit('Live grid diagnostic: '+json.dumps({'rows':len(rows),'rendered':sum(row['Категория']!='Вне полотна' for row in rows.values()),'coverage_percent':round(100*covered/total,3),'missing_cells':sorted(missing),'excluded_sampled_cells':sorted(excluded)}))
        identity=json.loads(request('/api/me')[1])
        emit('Edit access for synthetic admin: '+str(identity['can_edit'])+'; no hex PUT performed')
    finally:
        with connect() as conn:
            conn.execute('DELETE FROM users WHERE user_login=%s',(name,))
        emit('Temporary validation account/sessions removed; existing accounts and all hex values unchanged; no restart/reboot')

def publish_map():
    repo = ROOT / 'repository'
    old_revision = run(['git','-C',str(repo),'rev-parse','HEAD'],raw=True).stdout.strip()
    if run(['git','-C',str(repo),'status','--porcelain'],raw=True).stdout.strip():
        raise RuntimeError('VPS repository has local changes; publication refused')
    before = run(['runuser','-u','postgres','--','psql','-X','-At','-d','rhisseth','-c',
                  "SELECT count(*),md5(string_agg(data::text,'' ORDER BY r,q)) FROM hexes"],raw=True).stdout.strip()
    backup_database('before-map-v5')
    env = {**os.environ,'GIT_TERMINAL_PROMPT':'0'}
    run(['git','-C',str(repo),'fetch','origin','main'],env=env)
    revision = run(['git','-C',str(repo),'rev-parse','origin/main'],raw=True).stdout.strip()
    changes = run(['git','-C',str(repo),'diff','--name-only',old_revision,revision],raw=True).stdout.splitlines()
    allowed = ('app/frontend/','docs/','scripts/automation/')
    if any(not name.startswith(allowed) for name in changes):
        raise RuntimeError('Release includes unrelated changes; publication refused')
    run(['git','-C',str(repo),'merge','--ff-only','origin/main'])
    frontend = repo / 'app/frontend'
    asset = frontend / 'terrain-map-group3-artistic-v5.png'
    if not asset.is_file() or 'terrain-map-group3-artistic-v5.png' not in (frontend/'index.html').read_text():
        raise RuntimeError('V5 asset/reference missing')
    # New files inherit controller umask; only tracked frontend public assets need read access.
    for path in frontend.rglob('*'):
        path.chmod(0o755 if path.is_dir() else 0o644)
    run(['nginx','-t'])
    for unit in ('rhisseth','postgresql@16-main','nginx'):
        run(['systemctl','is-active',unit])
    after = run(['runuser','-u','postgres','--','psql','-X','-At','-d','rhisseth','-c',
                 "SELECT count(*),md5(string_agg(data::text,'' ORDER BY r,q)) FROM hexes"],raw=True).stdout.strip()
    if before != after:
        raise RuntimeError('Unexpected hex database change during publication')
    emit('Published asset SHA256: '+hashlib.sha256(asset.read_bytes()).hexdigest())
    emit('Previous release: '+old_revision+'; published release: '+revision)
    emit('Hex database count/checksum unchanged: '+after)
    stats = run(['runuser','-u','postgres','--','psql','-X','-At','-d','rhisseth','-c',
                 "SELECT data->>'Категория',count(*) FROM hexes GROUP BY 1 ORDER BY 1"],raw=True).stdout.strip()
    emit('Hex categories: '+stats)
    release_path = ROOT/'release.json'
    release = json.loads(release_path.read_text())
    release.update(git_commit=revision,map_asset=asset.name,map_published_utc=now.isoformat())
    release_path.write_text(json.dumps(release,indent=2))
    emit('Validation: V5 static publication complete; DB unchanged; no service restart; no reboot')

code = 1
try:
    emit('Preflight: project audit log writable; approved VPS identity required')
    if run(['hostname'], raw=True).stdout.strip() != 'rhisseth' or os.geteuid() != 0:
        raise RuntimeError('VPS identity/privilege mismatch')
    if operation == 'inspect':
        inspect()
    elif operation == 'install':
        install()
    elif operation == 'validate':
        validate()
    elif operation == 'hosting':
        hosting()
    elif operation == 'snapshot':
        backup_database('after-hosting')
        run(['git','-C',str(ROOT/'repository'),'rev-parse','HEAD'])
        run(['git','-C',str(ROOT/'repository'),'status','--porcelain'])
        run(['runuser','-u','postgres','--','psql','-X','-At','-d','rhisseth','-c',"SELECT count(*),md5(string_agg(data::text,'' ORDER BY r,q)) FROM hexes"])
        emit('Validation: post-migration database backup saved; existing account data and map retained')
    elif operation == 'publish-map':
        publish_map()
    elif operation == 'audit-map':
        audit_map()
    else:
        raise RuntimeError('Unknown operation')
    code = 0
except Exception as error:
    emit(f'Failure: {type(error).__name__}: {error}')
finally:
    emit(f'Validation: exit_code={code}; operation={operation}; reboot=false')
    emit(f'VPS audit log: {log}')
sys.exit(code)
