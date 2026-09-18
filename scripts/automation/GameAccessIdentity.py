#!/opt/rhisseth/venv/bin/python
"""Root-owned identity bridge; never import project code writable by the team."""
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import subprocess
import sys
from zoneinfo import ZoneInfo
import bcrypt
import psycopg

BASE = Path('/etc/rhisseth-game-access')
STATE = BASE/'accounts.json'
GROUP = 'rhisseth-team'
MARKER = 'Rhisseth game identity '

def connect():
    return psycopg.connect(host='127.0.0.1', dbname='rhisseth', user='rhisseth',
        password=Path('/opt/rhisseth/secrets/db-password.txt').read_text().strip(), connect_timeout=5)

def accounts():
    return json.loads(STATE.read_text()) if STATE.exists() else {}

def command(args, **kwargs):
    result = subprocess.run(args, capture_output=True, timeout=20, **kwargs)
    if result.returncode:
        raise RuntimeError('Identity command failed: '+args[0])

def pam():
    # PAM passes a NUL-terminated password over stdin; never log it or exceptions.
    name = os.environ.get('PAM_USER', '')
    identity = accounts().get(name)
    if identity is None:
        return 1
    with connect() as conn:
        row = conn.execute('SELECT u.user_login,u.user_pass,r.role_alias FROM users u JOIN roles r USING(role_id) WHERE user_id=%s', (identity['id'],)).fetchone()
    if not row or row[2] != 'admin' or row[0] != identity['login']:
        return 1
    if os.environ.get('PAM_TYPE') == 'account':
        return 0
    if os.environ.get('PAM_TYPE') != 'auth':
        return 1
    supplied = sys.stdin.buffer.read(512).split(b'\0', 1)[0]
    return 0 if bcrypt.checkpw(supplied[:72], row[1].encode('ascii')) else 1

def sync():
    os.umask(0o077)
    BASE.mkdir(mode=0o700, exist_ok=True)
    lock = (BASE/'sync.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX)
    now = dt.datetime.now(dt.timezone.utc)
    directory = Path('/opt/rhisseth/reports/automation-logs')/now.strftime('%Y-%m-%d')
    directory.mkdir(parents=True, exist_ok=True)
    log = directory/'game-access-identity-sync.md'
    def emit(message):
        with log.open('a') as stream:
            stream.write(f'- UTC {dt.datetime.now(dt.timezone.utc).isoformat()}; Europe/Moscow {dt.datetime.now(ZoneInfo("Europe/Moscow")).isoformat()}; {message}\n')
            stream.flush()
            os.fsync(stream.fileno())
    emit('Task rhisseth-game-access-sync; controller systemd via approved runner deployment; runner STU-AUTOMATION-01 / 10.210.52.128; target VDS 62.113.109.168 local identities; action sync; preflight audit writable; Passbolt da44a388-e458-4379-ab4c-c204696804b2')
    current = accounts()
    try:
        with connect() as conn:
            rows = conn.execute("SELECT user_id,user_login FROM users JOIN roles USING(role_id) WHERE role_alias='admin' ORDER BY user_id").fetchall()
        desired = {}
        for uid, login in rows:
            name = login if re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', login) else 'game'+str(uid)
            if name in desired or (name in current and current[name]['id'] != uid):
                raise RuntimeError('Identity name collision')
            try:
                entry = pwd.getpwnam(name)
            except KeyError:
                entry = None
            if entry is not None and (entry.pw_uid < 1000 or entry.pw_gecos != MARKER+str(uid)):
                raise RuntimeError('Existing OS account collision')
            desired[name] = {'id':uid, 'login':login}
        # Persist mappings before creation; partial failures can be recovered safely.
        merged = dict(current)
        merged.update(desired)
        temporary = STATE.with_suffix('.tmp')
        temporary.write_text(json.dumps(merged, ensure_ascii=False))
        temporary.chmod(0o600)
        temporary.replace(STATE)
        for name, identity in desired.items():
            try:
                entry = pwd.getpwnam(name)
            except KeyError:
                emit('Approved change: create game identity '+name)
                command(['useradd','-m','-s','/bin/bash','-g',GROUP,'-c',MARKER+str(identity['id']),name])
                entry = pwd.getpwnam(name)
                Path(entry.pw_dir).chmod(0o700)
                project = Path(entry.pw_dir)/'project'
                project.symlink_to('/opt/rhisseth/repository')
                # Random local hash prevents ordinary UNIX password login; PAM checks game DB.
                import crypt
                hashed = crypt.crypt(secrets.token_urlsafe(48), crypt.mksalt(crypt.METHOD_SHA512))
                command(['chpasswd','-e'], input=(name+':'+hashed+'\n').encode())
                emit('Created '+name+'; exit_code=0; project symlink installed')
            command(['usermod','-U',name])
        for name in set(merged)-set(desired):
            try:
                entry = pwd.getpwnam(name)
            except KeyError:
                continue
            if entry.pw_gecos != MARKER+str(merged[name]['id']):
                raise RuntimeError('Revoked identity ownership mismatch')
            emit('Approved change: revoke '+name)
            command(['usermod','-L',name])
            result = subprocess.run(['pkill','-KILL','-u',str(entry.pw_uid)], capture_output=True)
            if result.returncode not in (0,1):
                raise RuntimeError('Session revocation failed')
            emit('Revoked '+name+'; lock exit_code=0; session termination exit_code='+str(result.returncode))
        emit('Validation exit_code=0; active identities='+','.join(desired)+'; reboot=false')
    except Exception:
        # Live PAM lookup also rejects login on database failure.
        emit('Validation exit_code=1; sync failed; raw diagnostics suppressed; live PAM rejects missing DB/role; reboot=false')
        raise

if __name__ == '__main__':
    if len(sys.argv)>1 and sys.argv[1]=='sync':
        try:
            sync()
        except Exception:
            raise SystemExit('Identity sync failed; sanitized audit contains status')
    else:
        try:
            code = pam()
        except Exception:
            code = 1
        raise SystemExit(code)
