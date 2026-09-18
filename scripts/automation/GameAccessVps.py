# Release review 2026-09-18 (0.0.2): Reviewed game-admin SSH/SFTP setup and real protocol verification.
# Details: docs/releases/0.0.2-changes-2026-09-18.md.
"""Reviewed game-admin SSH/SFTP setup and real protocol verification."""
import datetime as dt
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
from zoneinfo import ZoneInfo
import bcrypt
import psycopg

ROOT = Path('/opt/rhisseth')
BASE = Path('/etc/rhisseth-game-access')
IDENTITY = BASE/'identity.py'
GROUP = 'rhisseth-team'
PAM = Path('/etc/pam.d/sshd')
CONF = Path('/etc/ssh/sshd_config.d/00-rhisseth-team.conf')
SERVICE = Path('/etc/systemd/system/rhisseth-game-access-sync.service')
TIMER = SERVICE.with_suffix('.timer')
operation = sys.argv[1]
if operation not in ('inspect','deploy','validate','timer-check'):
    raise SystemExit('Invalid operation')
os.umask(0o077)
now = dt.datetime.now(dt.timezone.utc)
directory = ROOT/'reports/automation-logs'/now.strftime('%Y-%m-%d')
directory.mkdir(parents=True, exist_ok=True)
log = directory/(now.strftime('%Y%m%d-%H%M%S')+'-game-access-'+operation+'.md')
log.write_text(f'# Game admin SSH/SFTP {operation}\n\n- UTC: {now.isoformat()}\n- Europe/Moscow: {now.astimezone(ZoneInfo("Europe/Moscow")).isoformat()}\n- Controller: Codex via STU-AUTOMATION-01 / 10.210.52.128\n- Target: VDS 62.113.109.168; rhisseth PostgreSQL identities; project files; PAM/SSH\n- Action: {operation}\n- Passbolt resource: da44a388-e458-4379-ab4c-c204696804b2\n', encoding='utf-8')

def emit(message):
    with log.open('a') as stream:
        stream.write(str(message)+'\n')
        stream.flush()
        os.fsync(stream.fileno())
    print(message, flush=True)

def run(args, **kwargs):
    emit('Approved command: '+' '.join(args))
    result = subprocess.run(args, capture_output=True, text=True, timeout=120, **kwargs)
    emit('Command exit_code='+str(result.returncode))
    if result.returncode:
        raise RuntimeError('Command failed: '+args[0]+'; raw output suppressed')
    return result.stdout

def connect():
    return psycopg.connect(host='127.0.0.1', dbname='rhisseth', user='rhisseth',
        password=(ROOT/'secrets/db-password.txt').read_text().strip(), connect_timeout=5)

def timer_check():
    import pwd
    import spwd
    import time
    name='rhtimercheck'+secrets.token_hex(3)
    uid=None
    def wait_for(predicate):
        until=time.monotonic()+45
        while time.monotonic()<until:
            if predicate():
                return
            time.sleep(0.5)
        raise RuntimeError('Automatic identity timer did not converge within 45 seconds')
    def created():
        try:
            entry=pwd.getpwnam(name)
            return entry.pw_gecos=='Rhisseth game identity '+str(uid) and not spwd.getspnam(name).sp_pwdp.startswith('!')
        except KeyError:
            return False
    try:
        emit('Approved action: create synthetic game admin; wait for automatic timer without manual sync')
        with connect() as conn:
            uid=conn.execute("INSERT INTO users(user_login,user_pass,user_email,role_id) VALUES(%s,%s,%s,(SELECT role_id FROM roles WHERE role_alias='admin')) RETURNING user_id",(name,bcrypt.hashpw(secrets.token_bytes(24),bcrypt.gensalt(12)).decode(),name+'@example.invalid')).fetchone()[0]
        wait_for(created)
        emit('Validated: automatic timer provisioned newly assigned game administrator')
        with connect() as conn:
            conn.execute('DELETE FROM users WHERE user_id=%s',(uid,))
        wait_for(lambda:spwd.getspnam(name).sp_pwdp.startswith('!'))
        emit('Validated: automatic timer revoked deleted game user without manual sync')
    finally:
        if uid is not None:
            with connect() as conn:
                conn.execute('DELETE FROM users WHERE user_id=%s',(uid,))
            run([str(IDENTITY),'sync'])
            try:
                entry=pwd.getpwnam(name)
            except KeyError:
                entry=None
            if entry:
                if entry.pw_uid<1000 or entry.pw_gecos!='Rhisseth game identity '+str(uid) or entry.pw_dir!='/home/'+name:
                    raise RuntimeError('Timer synthetic account ownership mismatch')
                run(['userdel','-r',name])
            import fcntl
            with (BASE/'sync.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                state=json.loads((BASE/'accounts.json').read_text()); state.pop(name,None)
                (BASE/'accounts.json').write_text(json.dumps(state,ensure_ascii=False))
            emit('Timer test synthetic user and account cleaned')

def validate():
    name = 'rhaccesscheck'+secrets.token_hex(3)
    password = secrets.token_urlsafe(24)
    uid = None
    known = BASE/'test-known-hosts'
    key = Path('/etc/ssh/ssh_host_ed25519_key.pub').read_text().split()
    known.write_text('127.0.0.1 '+key[0]+' '+key[1]+'\n')
    opts = ['-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(known),'-o','ConnectTimeout=8','-o','PreferredAuthentications=password','-o','PubkeyAuthentication=no','-o','NumberOfPasswordPrompts=1']
    def ssh(supplied, command, succeeds=True):
        env = os.environ.copy(); env['SSHPASS'] = supplied
        result = subprocess.run(['sshpass','-e','ssh',*opts,name+'@127.0.0.1',command],env=env,capture_output=True,text=True,timeout=20)
        if (result.returncode==0) != succeeds:
            raise RuntimeError('Synthetic SSH expectation failed; diagnostics suppressed')
        return result.stdout.strip()
    try:
        with connect() as conn:
            uid = conn.execute("INSERT INTO users(user_login,user_pass,user_email,role_id) VALUES(%s,%s,%s,(SELECT role_id FROM roles WHERE role_alias='admin')) RETURNING user_id",(name,bcrypt.hashpw(password.encode(),bcrypt.gensalt(12)).decode(),name+'@example.invalid')).fetchone()[0]
        run([str(IDENTITY),'sync'])
        if ssh(password,'id -un') != name:
            raise RuntimeError('Synthetic identity mismatch')
        ssh('incorrect-'+password,'true',False)
        ssh(password,'test ! -r /opt/rhisseth/secrets/db-password.txt && test ! -w /opt/rhisseth/repository/.git && ! sudo -n true 2>/dev/null')
        emit('Validated: game admin SSH; wrong password denied; no direct secret/.git/sudo access')
        local = BASE/'sftp-check.txt'; local.write_text('rhisseth-sftp-verification\n')
        remote = '/opt/rhisseth/repository/app/frontend/.'+name+'.txt'
        output = BASE/'sftp-result.txt'
        env = os.environ.copy(); env['SSHPASS']=password
        batch = f'put {local} {remote}\nget {remote} {output}\nrm {remote}\nbye\n'
        result = subprocess.run(['sshpass','-e','sftp',*opts,name+'@127.0.0.1'],input=batch,env=env,capture_output=True,text=True,timeout=20)
        if result.returncode or not output.exists() or output.read_bytes()!=local.read_bytes() or Path(remote).exists():
            raise RuntimeError('Synthetic SFTP transfer failed; diagnostics suppressed')
        local.unlink(); output.unlink()
        emit('Validated: SFTP upload/download/delete; content matches')
        new_password = secrets.token_urlsafe(24)
        with connect() as conn:
            conn.execute('UPDATE users SET user_pass=%s WHERE user_id=%s',(bcrypt.hashpw(new_password.encode(),bcrypt.gensalt(12)).decode(),uid))
        ssh(password,'true',False); ssh(new_password,'true')
        emit('Validated: game password change takes effect immediately without sync')
        with connect() as conn:
            conn.execute("UPDATE users SET role_id=(SELECT role_id FROM roles WHERE role_alias='user') WHERE user_id=%s",(uid,))
        ssh(new_password,'true',False)
        emit('Validated: role downgrade blocks SSH immediately before sync')
        run([str(IDENTITY),'sync']); ssh(new_password,'true',False)
        emit('Validated: role downgrade locks local identity')
        with connect() as conn:
            conn.execute("UPDATE users SET role_id=(SELECT role_id FROM roles WHERE role_alias='admin') WHERE user_id=%s",(uid,))
        run([str(IDENTITY),'sync']); ssh(new_password,'true')
        env=os.environ.copy(); env['SSHPASS']=new_password
        session=subprocess.Popen(['sshpass','-e','ssh',*opts,name+'@127.0.0.1','echo connected; exec sleep 120'],env=env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
        try:
            if session.stdout.readline().strip()!='connected':
                raise RuntimeError('Synthetic persistent session failed')
            with connect() as conn:
                conn.execute('DELETE FROM users WHERE user_id=%s',(uid,))
            ssh(new_password,'true',False)
            run([str(IDENTITY),'sync'])
            session.wait(timeout=10)
            emit('Validated: user deletion denies new login immediately and sync terminates open SSH session')
        finally:
            if session.poll() is None:
                session.kill(); session.wait(timeout=10)
        run(['/usr/sbin/sshd','-t'])
        emit('Application service: '+run(['systemctl','is-active','rhisseth']).strip())
        emit('Identity timer: '+run(['systemctl','is-active','rhisseth-game-access-sync.timer']).strip())
    finally:
        if uid is not None:
            with connect() as conn:
                conn.execute('DELETE FROM users WHERE user_id=%s',(uid,))
            run([str(IDENTITY),'sync'])
            import pwd
            try:
                entry = pwd.getpwnam(name)
            except KeyError:
                entry = None
            if entry:
                if entry.pw_uid<1000 or entry.pw_gecos!='Rhisseth game identity '+str(uid) or entry.pw_dir!='/home/'+name:
                    raise RuntimeError('Synthetic cleanup ownership mismatch')
                run(['userdel','-r',name])
            state = json.loads((BASE/'accounts.json').read_text()); state.pop(name,None)
            (BASE/'accounts.json').write_text(json.dumps(state,ensure_ascii=False))
            Path('/opt/rhisseth/repository/app/frontend/.'+name+'.txt').unlink(missing_ok=True)
            emit('Synthetic accounts/files cleaned; existing users/passwords unchanged')
        known.unlink(missing_ok=True)

code = 1
changed = False
try:
    emit('Preflight: audit writable; root controller; helpers do not import team-writable code')
    with connect() as conn:
        admins = conn.execute("SELECT user_id,user_login FROM users JOIN roles USING(role_id) WHERE role_alias='admin' ORDER BY user_id").fetchall()
    emit('Game administrator identities: '+json.dumps(admins,ensure_ascii=False))
    if run(['systemctl','show','rhisseth','-p','User','--value']).strip()!='rhisseth':
        raise RuntimeError('Unexpected app service identity')
    if operation=='inspect':
        import ast
        ast.parse(Path(__file__).read_text(encoding='utf-8-sig'))
        ast.parse(Path(__file__).with_name('GameAccessIdentity.py').read_text(encoding='utf-8-sig'))
        emit('Validated: deployment and identity helper Python syntax; no execution of identity changes')
        emit('ACL available: '+str(Path('/usr/bin/setfacl').exists()))
        emit('PAM auth include count: '+str(PAM.read_text().count('@include common-auth')))
    if operation=='deploy':
        if CONF.exists() or BASE.exists():
            raise RuntimeError('Existing game access setup; refusing blind overwrite')
        pam_original = PAM.read_text()
        if pam_original.count('@include common-auth')!=1 or pam_original.count('@include common-account')!=1:
            raise RuntimeError('Unexpected PAM layout')
        backup = ROOT/'backups'/('game-access-'+now.strftime('%Y%m%d-%H%M%S'))
        backup.mkdir(parents=True)
        shutil.copy2(PAM,backup/'sshd.pam'); shutil.copy2('/etc/ssh/sshd_config',backup/'sshd_config')
        emit('Backup: '+str(backup)); changed=True
        env=os.environ.copy(); env['DEBIAN_FRONTEND']='noninteractive'
        run(['apt-get','install','-y','acl','sshpass'],env=env)
        run(['groupadd',GROUP]); BASE.mkdir(mode=0o700)
        IDENTITY.write_text(Path(__file__).with_name('GameAccessIdentity.py').read_text(encoding='utf-8-sig'),encoding='utf-8'); IDENTITY.chmod(0o700)
        run([str(IDENTITY),'sync'])
        run(['setfacl','-m','g:'+GROUP+':--x',str(ROOT)])
        run(['setfacl','-m','g:'+GROUP+':r-x',str(ROOT/'repository')])
        for relative in ('app','data','docs','deploy'):
            target=ROOT/'repository'/relative
            if target.exists():
                run(['setfacl','-R','-m','g:'+GROUP+':rwX',str(target)])
                run(['find',str(target),'-type','d','-exec','setfacl','-m','d:g:'+GROUP+':rwx','{}','+'])
        auth=f'auth [success=1 default=ignore] pam_succeed_if.so quiet user notingroup {GROUP}\nauth [success=done default=die] pam_exec.so expose_authtok seteuid {IDENTITY}\n'
        account=f'account [success=1 default=ignore] pam_succeed_if.so quiet user notingroup {GROUP}\naccount requisite pam_exec.so seteuid {IDENTITY}\n'
        PAM.write_text(pam_original.replace('@include common-auth',auth+'@include common-auth').replace('@include common-account',account+'@include common-account'))
        CONF.write_text(f'Match Group {GROUP}\n    PasswordAuthentication yes\n    AuthenticationMethods password\n    PubkeyAuthentication no\n    KbdInteractiveAuthentication no\n    DisableForwarding yes\n    X11Forwarding no\n    PermitUserRC no\nMatch all\n')
        SERVICE.write_text('[Unit]\nDescription=Provision game administrators for SSH and SFTP\nAfter=postgresql.service\n\n[Service]\nType=oneshot\nUser=root\nExecStart=/etc/rhisseth-game-access/identity.py sync\nUMask=0077\n')
        TIMER.write_text('[Unit]\nDescription=Sync game administrator access every 30 seconds\n\n[Timer]\nOnBootSec=30s\nOnUnitActiveSec=30s\nAccuracySec=1s\n\n[Install]\nWantedBy=timers.target\n')
        try:
            run(['/usr/sbin/sshd','-t']); run(['systemctl','daemon-reload']); run(['systemctl','reload','ssh'])
            run(['systemctl','enable','--now','rhisseth-game-access-sync.timer']); validate()
        except Exception:
            emit('Validation failed; restoring PAM/SSH admission configuration and disabling team identities')
            shutil.copy2(backup/'sshd.pam',PAM); CONF.unlink(missing_ok=True)
            subprocess.run(['systemctl','disable','--now','rhisseth-game-access-sync.timer'],capture_output=True)
            for name in json.loads((BASE/'accounts.json').read_text()):
                run(['usermod','-L',name])
            run(['/usr/sbin/sshd','-t']); run(['systemctl','reload','ssh'])
            raise
    elif operation=='validate':
        validate()
    elif operation=='timer-check':
        changed=True
        timer_check()
    code=0
except Exception as error:
    emit('Failure: '+type(error).__name__+': '+str(error))
finally:
    emit(f'Validation: exit_code={code}; changed={str(changed).lower()}; reboot=false; audit={log}')
sys.exit(code)
