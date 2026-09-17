"""Publish an isolated, authenticated visual comparison; preserve live code/data."""
import datetime as dt
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from zoneinfo import ZoneInfo

ROOT = Path('/opt/rhisseth')
SOURCE = ROOT / 'repository/app/frontend'
DEST = ROOT / 'previews/map'
URL = '/map/'
now = dt.datetime.now(dt.timezone.utc)
logs = ROOT / 'reports/automation-logs' / now.strftime('%Y-%m-%d')
logs.mkdir(parents=True, exist_ok=True)
log = logs / (now.strftime('%Y%m%d-%H%M%S') + '-islands-map-preview.md')
log.write_text(f'# Island comparison publication\n\n- UTC: {now.isoformat()}\n- Europe/Moscow: {now.astimezone(ZoneInfo("Europe/Moscow")).isoformat()}\n- Task: islands-map-preview\n- Controller: Codex via local Docker with pinned SSH\n- Target: Rhisseth 62.113.109.168; isolated preview and nginx routing\n- Passbolt resource: da44a388-e458-4379-ab4c-c204696804b2\n- Reboot: false\n\n', encoding='utf-8')

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
        raise RuntimeError('Source missing')
    original_js = (SOURCE / 'app.js').read_text()
    if 'const RADIUS = 80;' not in original_js:
        raise RuntimeError('Unexpected live radius; review required')
    run(['nginx', '-t'])
    before = hashes()
    db_before = database_signature()
    previous = site.read_text()
    if 'location / {' not in previous or URL in previous:
        raise RuntimeError('Unexpected nginx configuration')
    emit('Preflight: writable audit log; live radius 80; isolated destination validated; nginx valid')
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.parent.chmod(0o755)
    if DEST.exists():
        expected = {
            'index.html': None,
            'terrain-map-islands-preview-v1.png': ROOT / 'staging/islands-map-v1/terrain-map-islands-preview-v1.png',
            'terrain-map-group3-artistic-v5-no-grid.png': SOURCE / 'terrain-map-group3-artistic-v5-no-grid.png',
        }
        if {p.name for p in DEST.iterdir()} != set(expected):
            raise RuntimeError('Existing preview contains unexpected files; refusing overwrite')
        for name, reference in expected.items():
            if reference is not None and hashlib.sha256((DEST/name).read_bytes()).digest() != hashlib.sha256(reference.read_bytes()).digest():
                raise RuntimeError('Existing preview differs from this delivery; refusing overwrite')
        emit('Retry: existing isolated preview matches delivered PNG and live original')
    else:
        shutil.copytree(SOURCE, DEST)
    incoming = ROOT / 'staging/islands-map-v1'
    shutil.copyfile(incoming / 'terrain-map-islands-preview-v1.png', DEST / 'terrain-map-islands-preview-v1.png')
    html = (incoming / 'index.html').read_text(encoding='utf-8-sig')
    html = html.replace('../../../app/frontend/terrain-map-group3-artistic-v5-no-grid.png', 'terrain-map-group3-artistic-v5-no-grid.png')
    html = html.replace('\u0427\u0435\u0440\u043d\u043e\u0432\u0438\u043a imagegen; \u043d\u0430 VDS \u043d\u0435 \u043e\u043f\u0443\u0431\u043b\u0438\u043a\u043e\u0432\u0430\u043d.', '\u041f\u0440\u0435\u0434\u0432\u0430\u0440\u0438\u0442\u0435\u043b\u044c\u043d\u044b\u0439 \u0432\u0430\u0440\u0438\u0430\u043d\u0442 \u0434\u043b\u044f \u0441\u0440\u0430\u0432\u043d\u0435\u043d\u0438\u044f.')
    html = html.replace('<meta charset="utf-8">', '<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex, nofollow">')
    html = html.replace('<button id="before">', '<p><a style="color:#b9dcff" href="/interactive-map/" target="_blank" rel="noopener">\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043e\u0441\u043d\u043e\u0432\u043d\u0443\u044e \u043a\u0430\u0440\u0442\u0443</a></p><button id="before">')
    html = html.replace('<img id="map"', '<img alt="\u041f\u0440\u0435\u0434\u0432\u0430\u0440\u0438\u0442\u0435\u043b\u044c\u043d\u0430\u044f \u043a\u0430\u0440\u0442\u0430 \u043e\u0441\u0442\u0440\u043e\u0432\u043e\u0432" id="map"')
    # Publish only the comparison viewer and its two PNGs.
    for p in list(DEST.iterdir()):
        if p.name not in ('index.html', 'terrain-map-group3-artistic-v5-no-grid.png', 'terrain-map-islands-preview-v1.png'):
            if p.is_file():
                p.unlink()
    (DEST / 'index.html').write_text(html, encoding='utf-8')
    for p in DEST.rglob('*'):
        p.chmod(0o755 if p.is_dir() else 0o644)
    DEST.chmod(0o755)
    assert 'fetch(' not in html and 'PUT' not in html
    block = '''    # Isolated visual comparison, discoverable only through its direct URL.
    location = /map { return 302 /map/; }
    location = /_islands_map_identity {
        internal;
        proxy_pass http://127.0.0.1:8080/api/me;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
        proxy_set_header Host $host;
    }
    location ^~ /map/ {
        auth_request /_islands_map_identity;
        error_page 401 = /index.php;
        alias /opt/rhisseth/previews/map/;
        index index.html;
        autoindex off;
        add_header X-Robots-Tag "noindex, nofollow" always;
        add_header X-Content-Type-Options nosniff always;
        add_header X-Frame-Options DENY always;
        add_header Referrer-Policy same-origin always;
        add_header Cache-Control "no-store" always;
        limit_except GET { deny all; }
    }
'''
    backup = ROOT / 'backups' / (now.strftime('%Y%m%d-%H%M%S') + '-nginx-before-islands-map.conf')
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_text(previous)
    backup.chmod(0o600)
    site.write_text(previous.replace('    location / {', block + '    location / {', 1))
    changed = True
    run(['nginx', '-t'])
    run(['systemctl', 'reload', 'nginx'])
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
    if status != 200 or b'id="overlay"' in page:
        raise RuntimeError('Anonymous preview must show login only')
    for filename in ('index.html', 'terrain-map-islands-preview-v1.png', 'terrain-map-group3-artistic-v5-no-grid.png'):
        status, content = request(URL + filename)
        if status != 200 or b'name="csrf"' not in content:
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
            raise RuntimeError('Authenticated /map/ index mismatch')
        for filename in ('index.html', 'terrain-map-islands-preview-v1.png', 'terrain-map-group3-artistic-v5-no-grid.png'):
            status, content = request(URL + filename)
            if status != 200 or hashlib.sha256(content).digest() != hashlib.sha256((DEST / filename).read_bytes()).digest():
                raise RuntimeError('Authenticated preview file mismatch: ' + filename)
        status, content = request('/interactive-map/app.js')
        if status != 200 or hashlib.sha256(content).hexdigest() != before['app.js']:
            raise RuntimeError('Original HTTPS version changed')
        emit('Validation: anonymous login protection; authenticated comparison HTML and both PNG exact hashes; original HTTPS JS unchanged')
    finally:
        with connect() as conn:
            conn.execute('DELETE FROM users WHERE user_login=%s', (name,))
        emit('Temporary validation account and cascading sessions removed; no hex PUT performed')
    if hashes() != before or database_signature() != db_before:
        raise RuntimeError('Original frontend or hex database changed')
    emit('URL: https://rhisseth.ru' + URL)
    emit('Validation: original frontend SHA256 and hex DB checksum unchanged; preview read-only; no app restart; nginx reload only; reboot=false')
    code = 0
except Exception as error:
    emit('Failure: ' + type(error).__name__ + ': ' + str(error))
    if changed and previous is not None:
        site.write_text(previous)
        run(['nginx', '-t'])
        run(['systemctl', 'reload', 'nginx'])
        emit('Rollback: original nginx routing restored; unpublished preview retained for review')
finally:
    emit(f'Exit code: {code}; reboot=false; log={log}')
sys.exit(code)
