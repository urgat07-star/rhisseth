"""Publish an isolated, authenticated visual comparison; preserve live code/data."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from zoneinfo import ZoneInfo

ROOT = Path('/opt/rhisseth')
SOURCE = ROOT / 'repository/app/frontend'
DEST = SOURCE
URL = '/interactive-map/'
now = dt.datetime.now(dt.timezone.utc)
logs = ROOT / 'reports/automation-logs' / now.strftime('%Y-%m-%d')
logs.mkdir(parents=True, exist_ok=True)
log = logs / (now.strftime('%Y%m%d-%H%M%S') + '-v6-promotion.md')
log.write_text(f'# Island comparison publication\n\n- UTC: {now.isoformat()}\n- Europe/Moscow: {now.astimezone(ZoneInfo("Europe/Moscow")).isoformat()}\n- Task: v6-promotion\n- Controller: Codex via local Docker with pinned SSH\n- Target: Rhisseth 62.113.109.168; isolated preview and nginx routing\n- Credential: owner-provided protected SSH password file\n- Reboot: false\n\n', encoding='utf-8')

def emit(value):
    with log.open('a', encoding='utf-8') as stream:
        stream.write(str(value) + '\n')
    print(value, flush=True)

def run(args):
    emit('Command: ' + ' '.join(args))
    p = subprocess.run(args, capture_output=True, text=True)
    emit(p.stdout.strip())
    emit(p.stderr.strip())
    emit('Exit code: ' + str(p.returncode))
    if p.returncode:
        raise RuntimeError('Validation command failed')
    return p.stdout

def hashes():
    return {str(p.relative_to(SOURCE)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in SOURCE.rglob('*') if p.is_file()}

def database_signature():
    return run(['runuser', '-u', 'postgres', '--', 'psql', '-X', '-At', '-d', 'rhisseth', '-c',
                "SELECT count(*),md5(string_agg(data::text,'' ORDER BY r,q)) FROM hexes"])

code = 1
site = Path('/etc/nginx/sites-available/rhisseth')
previous = None
changed = False
try:
    if not SOURCE.is_dir():
        raise RuntimeError('Primary frontend missing')
    run(['nginx', '-t'])
    config_before = site.read_bytes()
    before = hashes()
    db_before = database_signature()
    incoming = ROOT / 'staging/map-v6'
    manifest = json.loads((incoming/'v6-promotion-manifest.json').read_text())
    for name, expected in manifest['expected_before'].items():
        if hashlib.sha256((SOURCE/name).read_bytes()).hexdigest() != expected:
            raise RuntimeError('Primary frontend changed since preparation: ' + name)
    approved = ROOT / 'previews/map/terrain-map-islands-preview-v2.png'
    if hashlib.sha256(approved.read_bytes()).hexdigest() != manifest['approved_preview_sha256']:
        raise RuntimeError('Approved published preview differs from V6 delivery')
    for name, expected in manifest['files'].items():
        if hashlib.sha256((incoming/name).read_bytes()).hexdigest()!=expected:
            raise RuntimeError('Delivery hash mismatch: '+name)
    new_name = 'terrain-map-group3-artistic-v6-no-grid.png'
    if manifest['files'][new_name] != manifest['approved_preview_sha256']:
        raise RuntimeError('V6 PNG must be identical to the approved grid-free preview')
    new_dest = SOURCE/new_name
    if new_dest.exists():
        raise RuntimeError('V6 filename already exists; refusing replacement')
    html=(incoming/'index.html').read_text()
    if new_name not in html or 'v6-live-grid' not in html or 'id="hex-overlay"' not in html:
        raise RuntimeError('Unexpected V6 frontend HTML')
    if (incoming/'app.js').read_text() != (SOURCE/'app.js').read_text().replace('Artistic V5','Artistic V6'):
        raise RuntimeError('Promotion must preserve all grid and editing behavior')
    previous={name:(SOURCE/name).read_bytes() for name in ('index.html','app.js')}
    snapshot = ROOT/'backups'/(now.strftime('%Y%m%d-%H%M%S')+'-frontend-before-v6')
    snapshot.mkdir(mode=0o700)
    for name,data in previous.items():
        (snapshot/name).write_bytes(data)
    shutil.copyfile(incoming/'v6-promotion-manifest.json',snapshot/'manifest.json')
    emit('Previous main frontend snapshot: '+str(snapshot))
    def atomic(name,data):
        destination=SOURCE/name
        owner=destination.stat() if destination.exists() else (SOURCE/'index.html').stat()
        pending=SOURCE/('.'+name+'.pending')
        pending.write_bytes(data)
        os.chown(pending,owner.st_uid,owner.st_gid)
        pending.chmod(0o644)
        os.replace(pending,destination)
    atomic(new_name,(incoming/new_name).read_bytes())
    changed=True
    atomic('app.js',(incoming/'app.js').read_bytes())
    atomic('index.html',(incoming/'index.html').read_bytes())
    emit('Promoted approved PNG to main V6; interactive grid retained separately')
    sys.path.insert(0, str(ROOT / 'repository/app/backend'))
    os.environ['DB_HOST'] = '127.0.0.1'
    os.environ['DB_PASSWORD_FILE'] = str(ROOT / 'secrets/db-password.txt')
    # Reuse the established authenticated HTTPS audit without sending a hex PUT.
    import ssl, urllib.request, urllib.error, urllib.parse, http.cookiejar, secrets, bcrypt
    from db import connect
    context = ssl.create_default_context()
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), NoRedirect())
    def request(path, payload=None):
        req = urllib.request.Request('https://rhisseth.ru' + path,
            data=urllib.parse.urlencode(payload).encode() if payload else None)
        try:
            with opener.open(req, timeout=25) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()
    status, page = request(URL)
    if status != 303:
        raise RuntimeError('Anonymous preview must show login only')
    for filename in ('index.html', 'app.js', 'styles.css', 'terrain-map-group3-artistic-v6-no-grid.png'):
        status, content = request(URL + filename)
        if status != 303:
            raise RuntimeError('Anonymous asset access must show login only')
    name = 'islandsaudit_' + secrets.token_hex(6)
    password = secrets.token_urlsafe(24)
    stored = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
    try:
        with connect() as conn:
            role = conn.execute("SELECT role_id FROM roles WHERE role_alias='user'").fetchone()[0]
            conn.execute('INSERT INTO users(user_login,user_pass,user_email,role_id) VALUES (%s,%s,%s,%s)',
                         (name, stored, name + '@invalid.test', role))
        csrf = re.search(rb'name="csrf" value="([a-f0-9]+)"', request('/index.php')[1])[1].decode()
        if request('/index.php', {'login': name, 'password': password, 'csrf': csrf})[0] != 303:
            raise RuntimeError('Temporary login failed')
        status, content = request(URL)
        if status != 200 or hashlib.sha256(content).digest() != hashlib.sha256((DEST / 'index.html').read_bytes()).digest():
            raise RuntimeError('Authenticated V6 main index mismatch')
        for filename in ('index.html', 'app.js', 'styles.css', 'terrain-map-group3-artistic-v6-no-grid.png'):
            status, content = request(URL + filename)
            if status != 200 or hashlib.sha256(content).digest() != hashlib.sha256((DEST / filename).read_bytes()).digest():
                raise RuntimeError('Authenticated preview file mismatch: ' + filename)
        status, content = request('/interactive-map/app.js')
        if status != 200 or hashlib.sha256(content).hexdigest() != manifest['files']['app.js']:
            raise RuntimeError('V6 HTTPS JS mismatch')
        status, content = request('/api/hexes')
        if status != 200 or not isinstance(json.loads(content), list):
            raise RuntimeError('Main hex data API unavailable')
        status, content = request('/map/terrain-map-islands-preview-v2.png')
        if status != 200 or hashlib.sha256(content).hexdigest()!=manifest['approved_preview_sha256']:
            raise RuntimeError('Comparison preview unexpectedly changed')
        emit('Validation: anonymous login protection; authenticated main HTML/JS/CSS/PNG exact hashes; V6 HTTPS JS exact hash')
    finally:
        with connect() as conn:
            conn.execute('DELETE FROM users WHERE user_login=%s', (name,))
        emit('Temporary validation account and cascading sessions removed; no hex PUT performed')
    expected_after=dict(before)
    expected_after.update(manifest['files'])
    if hashes()!=expected_after or database_signature()!=db_before or site.read_bytes()!=config_before:
        raise RuntimeError('Unexpected frontend, hex DB or nginx change')
    emit('URL: https://rhisseth.ru' + URL)
    emit('Validation: V6 HTML/JS/PNG hashes verified; other assets and hex DB unchanged; no app restart; no nginx reload; reboot=false')
    code = 0
except Exception as error:
    emit('Failure: ' + type(error).__name__ + ': ' + str(error))
    if changed and previous is not None:
        for name,data in previous.items():
            atomic(name,data)
        emit('Rollback: previous main HTML/JS restored; V6 PNG retained for inspection')
finally:
    emit(f'Exit code: {code}; reboot=false; log={log}')
sys.exit(code)
