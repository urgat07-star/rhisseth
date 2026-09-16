"""Publish an isolated, authenticated visual comparison; preserve live code/data."""
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from zoneinfo import ZoneInfo

ROOT = Path('/opt/rhisseth')
SOURCE = ROOT / 'repository/app/frontend'
DEST = ROOT / 'previews/interactive-map-hex70'
URL = '/interactive-map-hex70/'
now = dt.datetime.now(dt.timezone.utc)
logs = ROOT / 'reports/automation-logs' / now.strftime('%Y-%m-%d')
logs.mkdir(parents=True, exist_ok=True)
log = logs / (now.strftime('%Y%m%d-%H%M%S') + '-hex70-preview.md')
log.write_text(f'# Hex70 comparison publication\n\n- UTC: {now.isoformat()}\n- Europe/Moscow: {now.astimezone(ZoneInfo("Europe/Moscow")).isoformat()}\n- Task: hex70-preview\n- Controller: Codex via STU-AUTOMATION-01 / 10.210.52.128\n- Target: Rhisseth 62.113.109.168; isolated preview and nginx routing\n- Passbolt resource: da44a388-e458-4379-ab4c-c204696804b2\n- Reboot: false\n\n', encoding='utf-8')

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
    if not SOURCE.is_dir() or DEST.exists():
        raise RuntimeError('Source missing or comparison directory already exists')
    original_js = (SOURCE / 'app.js').read_text()
    if 'const RADIUS = 80;' not in original_js:
        raise RuntimeError('Unexpected live radius; review required')
    run(['nginx', '-t'])
    before = hashes()
    db_before = database_signature()
    previous = site.read_text()
    if 'location / {' not in previous or URL in previous:
        raise RuntimeError('Unexpected nginx configuration')
    emit('Preflight: writable audit log; live radius 80; isolated destination absent; nginx valid')
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.parent.chmod(0o755)
    shutil.copytree(SOURCE, DEST)
    # No terrain data mapping is implied by the new coordinate system.
    start = original_js.index('form.addEventListener("submit",')
    end = original_js.index('\nfunction render(rows)', start)
    js = original_js[:start] + 'form.addEventListener("submit", (event) => event.preventDefault());\n' + original_js[end:]
    js = js.replace('const RADIUS = 80;', 'const RADIUS = 56;')
    js = re.sub(r'const VERSION = .*?;', 'const VERSION = "Rhisseth · сравнение · гексы −30%";', js, count=1)
    start = js.index('  if (!identity.can_edit) {')
    end = js.index('\n}\n', start)
    js = js[:start] + '''  for (const element of form.elements) element.disabled = true;
  document.querySelector('#editor-hint').textContent = 'Сравнение · гексы −30% · только просмотр';
  return { rows: [], source: "тестовая сетка без изменения данных" };''' + js[end:]
    (DEST / 'app.js').write_text(js, encoding='utf-8')
    html = (DEST / 'index.html').read_text()
    html = html.replace('<title>Rhisseth — интерактивная карта</title>', '<title>Rhisseth — сравнение гексов −30%</title>\n  <meta name="robots" content="noindex, nofollow">')
    html = html.replace('v5-live-grid', 'hex70-preview-v1').replace('<h1>Оперативная карта</h1>', '<h1>Сравнение: гексы −30%</h1>')
    html = html.replace('<button class="save" type="submit">Сохранить</button>', '')
    html = html.replace('Перерисовка изображения будет подключена отдельным этапом.', 'Тестовая сетка. Данные гексов исходной карты не изменяются.')
    (DEST / 'index.html').write_text(html, encoding='utf-8')
    for p in DEST.rglob('*'):
        p.chmod(0o755 if p.is_dir() else 0o644)
    DEST.chmod(0o755)
    assert 'method: "PUT"' not in js and 'fetch(`${API_BASE}/hexes`' not in js
    block = '''    # Isolated visual comparison, discoverable only through its direct URL.
    location = /interactive-map-hex70 { return 302 /interactive-map-hex70/; }
    location = /_hex70_identity {
        internal;
        proxy_pass http://127.0.0.1:8080/api/me;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
        proxy_set_header Host $host;
    }
    location ^~ /interactive-map-hex70/ {
        auth_request /_hex70_identity;
        error_page 401 = /index.php;
        alias /opt/rhisseth/previews/interactive-map-hex70/;
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
    backup = ROOT / 'backups' / (now.strftime('%Y%m%d-%H%M%S') + '-nginx-before-hex70.conf')
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
    context = ssl.create_default_context(cafile=str(ROOT / 'secrets/tls.crt'))
    context.check_hostname = False
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
    if status != 200 or b'id="hex-overlay"' in page:
        raise RuntimeError('Anonymous preview must show login only')
    name = 'hex70audit_' + secrets.token_hex(6)
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
        for filename in ('index.html', 'app.js', 'styles.css', 'terrain-map-group3-artistic-v5-no-grid.png'):
            status, content = request(URL + filename)
            if status != 200 or hashlib.sha256(content).digest() != hashlib.sha256((DEST / filename).read_bytes()).digest():
                raise RuntimeError('Authenticated preview file mismatch: ' + filename)
        status, content = request('/interactive-map/app.js')
        if status != 200 or hashlib.sha256(content).hexdigest() != before['app.js']:
            raise RuntimeError('Original HTTPS version changed')
        emit('Validation: anonymous login protection; authenticated preview HTML/JS/CSS/PNG exact hashes; original HTTPS JS unchanged')
    finally:
        with connect() as conn:
            conn.execute('DELETE FROM users WHERE user_login=%s', (name,))
        emit('Temporary validation account and cascading sessions removed; no hex PUT performed')
    if hashes() != before or database_signature() != db_before:
        raise RuntimeError('Original frontend or hex database changed')
    counts = []
    for radius in (80, 56):
        count = sum(math.floor(3200 / (math.sqrt(3) * radius) + .5 - r / 2) - math.ceil(-.5 - r / 2) + 1
                    for r in range(math.ceil((2200 + radius) / (radius * 1.5))))
        counts.append(count)
    emit('Grid cells original/preview: ' + json.dumps(counts))
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
