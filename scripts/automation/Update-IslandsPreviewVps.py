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
DEST = ROOT / 'previews/map'
URL = '/map/'
now = dt.datetime.now(dt.timezone.utc)
logs = ROOT / 'reports/automation-logs' / now.strftime('%Y-%m-%d')
logs.mkdir(parents=True, exist_ok=True)
log = logs / (now.strftime('%Y%m%d-%H%M%S') + '-islands-map-v2-update.md')
log.write_text(f'# Island comparison publication\n\n- UTC: {now.isoformat()}\n- Europe/Moscow: {now.astimezone(ZoneInfo("Europe/Moscow")).isoformat()}\n- Task: islands-map-preview\n- Controller: Codex via local Docker with pinned SSH\n- Target: Rhisseth 62.113.109.168; isolated preview and nginx routing\n- Credential: owner-provided protected SSH password file\n- Reboot: false\n\n', encoding='utf-8')

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
    if not SOURCE.is_dir() or not DEST.is_dir():
        raise RuntimeError('Original frontend or existing /map/ preview missing')
    original_js = (SOURCE / 'app.js').read_text()
    if 'const RADIUS = 80;' not in original_js:
        raise RuntimeError('Unexpected live radius')
    run(['nginx', '-t'])
    config_before = site.read_bytes()
    if 'alias /opt/rhisseth/previews/map/;' not in site.read_text():
        raise RuntimeError('Unexpected /map/ route; refusing update')
    before = hashes()
    db_before = database_signature()
    before_original = hashlib.sha256((SOURCE / 'terrain-map-group3-artistic-v5-no-grid.png').read_bytes()).digest()
    if hashlib.sha256((DEST / 'terrain-map-group3-artistic-v5-no-grid.png').read_bytes()).digest() != before_original:
        raise RuntimeError('Comparison original differs from current primary map')
    incoming = ROOT / 'staging/islands-map-v2'
    new_name = 'terrain-map-islands-preview-v2.png'
    new_png = incoming / new_name
    analysis = json.loads((incoming / 'placement-analysis.json').read_text(encoding='utf-8'))
    if analysis['source_sha256'] != before_original.hex():
        raise RuntimeError('Local editing source differs from the live original')
    if analysis['output_sha256'] != hashlib.sha256(new_png.read_bytes()).hexdigest():
        raise RuntimeError('Delivered image differs from verified image')
    if not all(analysis['validation'].values()):
        raise RuntimeError('Placement validation was not successful')
    emit('Verified small-island moves: ' + str(analysis['moved_count']))
    emit('Verified source artwork and final shoreline containment')
    import struct
    dimensions = struct.unpack('>II', new_png.read_bytes()[16:24])
    original_dimensions = struct.unpack('>II', (SOURCE / 'terrain-map-group3-artistic-v5-no-grid.png').read_bytes()[16:24])
    if dimensions != original_dimensions:
        raise RuntimeError('Preview canvas dimensions differ from original')
    html = (incoming / 'index.html').read_text(encoding='utf-8-sig')
    html = html.replace('../../../app/frontend/terrain-map-group3-artistic-v5-no-grid.png', 'terrain-map-group3-artistic-v5-no-grid.png')
    if new_name not in html or 'fetch(' in html or 'PUT' in html:
        raise RuntimeError('Unexpected comparison viewer')
    previous = (DEST / 'index.html').read_bytes()
    snapshot = ROOT / 'backups' / (now.strftime('%Y%m%d-%H%M%S') + '-map-before-v2')
    shutil.copytree(DEST, snapshot)
    snapshot.chmod(0o700)
    emit('Previous preview snapshot: ' + str(snapshot))
    new_dest = DEST / new_name
    if new_dest.exists() and hashlib.sha256(new_dest.read_bytes()).digest() != hashlib.sha256(new_png.read_bytes()).digest():
        raise RuntimeError('Versioned preview filename already contains another image')
    shutil.copyfile(new_png, new_dest)
    new_dest.chmod(0o644)
    pending = DEST / '.index-v2.pending'
    pending.write_text(html, encoding='utf-8')
    pending.chmod(0o644)
    os.replace(pending, DEST / 'index.html')
    changed = True
    emit('Updated comparison index atomically; nginx configuration preserved')
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
    for filename in ('index.html', 'terrain-map-islands-preview-v2.png', 'terrain-map-group3-artistic-v5-no-grid.png'):
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
        for filename in ('index.html', 'terrain-map-islands-preview-v2.png', 'terrain-map-group3-artistic-v5-no-grid.png'):
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
    if hashes() != before or database_signature() != db_before or site.read_bytes() != config_before:
        raise RuntimeError('Original frontend or hex database changed')
    emit('URL: https://rhisseth.ru' + URL)
    emit('Validation: original frontend SHA256 and hex DB checksum unchanged; preview read-only; no app restart; no nginx reload; reboot=false')
    code = 0
except Exception as error:
    emit('Failure: ' + type(error).__name__ + ': ' + str(error))
    if changed and previous is not None:
        rollback = DEST / '.index-rollback.pending'
        rollback.write_bytes(previous)
        rollback.chmod(0o644)
        os.replace(rollback, DEST / 'index.html')
        emit('Rollback: previous comparison index restored; immutable PNGs retained')
finally:
    emit(f'Exit code: {code}; reboot=false; log={log}')
sys.exit(code)
