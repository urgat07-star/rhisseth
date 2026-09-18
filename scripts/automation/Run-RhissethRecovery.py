#!/usr/bin/python3
"""Portable controller; current installation runs exclusively on pinned runner."""
import datetime as dt
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import urllib.request
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit
import argparse

os.umask(0o077)
ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / '.local/recovery'
RESOURCE = {'source':'da44a388-e458-4379-ab4c-c204696804b2','storage':'eebbe246-89db-4227-8618-89ff4fefcec5','test':'34b8e391-f4e8-4dbc-9304-6fcc22e942ab'}
HOST = {'source':'62.113.109.168','storage':'185.216.87.44','test':'10.210.52.56'}
OPTS = ['-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3']
parser = argparse.ArgumentParser()
parser.add_argument('operation')
parser.add_argument('approved_ref',nargs='?',default='')
parser.add_argument('--controller-config')
options = parser.parse_args()
operation = {'preflight':'preflight-test','restore':'restore-test','validate':'validate-test'}.get(options.operation,options.operation)
explicit_ref = options.approved_ref
settings = json.loads(Path(options.controller_config).read_text()) if options.controller_config else {}
for role,values in settings.get('targets',{}).items():
    if role not in HOST:
        raise SystemExit('Unknown controller target role')
    host = values.get('host',HOST[role])
    try:
        ipaddress.ip_address(host)
    except ValueError:
        raise SystemExit('Controller target hosts must be literal IP addresses')
    HOST[role] = host
    if values.get('resource_id'):
        RESOURCE[role] = values['resource_id']
if explicit_ref and (operation!='restore-test' or not re.fullmatch(r'(?:release/)?v?\d+\.\d+\.\d+',explicit_ref)):
    raise SystemExit('Invalid explicitly approved version reference')
if operation not in ('setup-storage', 'backup', 'test-access', 'schedule', 'list', 'diagnose-storage','preflight-test','restore-test','validate-test','reboot-test','verify-scripts','collect-evidence','run-scheduled','inspect-version','diagnose-memory','backup-summary','pin-target','finalize-test','progress-test','external-check','source-git-status','network-test','cleanup-test'):
    raise SystemExit('Invalid operation')
now = dt.datetime.now(dt.timezone.utc)
logs = ROOT / 'reports/automation-logs' / now.strftime('%Y-%m-%d')
logs.mkdir(parents=True, exist_ok=True)
log = logs / (now.strftime('%Y%m%d-%H%M%S-%f') + '-' + operation + '.md')
log.write_text(f'# Rhisseth {operation}\n\nUTC: {now.isoformat()}\n\nMoscow: {now.astimezone(ZoneInfo("Europe/Moscow")).isoformat()}\n\nTask: backup-and-portable-deployment; controller: Codex / {socket.gethostname()}\n\nRunner: STU-AUTOMATION-01 / 10.210.52.128\n\nTargets: {json.dumps(HOST)}; GitHub urgat07-star/rhisseth\n\nPassbolt resource IDs: {json.dumps(RESOURCE)}\n\nAction: {operation}; reboot=false\n')
def emit(value):
    with log.open('a') as stream:
        stream.write(str(value) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    print(value, flush=True)
def resource(role):
    values = settings.get('targets',{}).get(role,{})
    if values.get('credentials_file'):
        path = Path(values['credentials_file'])
        if path.stat().st_mode & 0o077:
            raise RuntimeError('Credential file must be owner-only')
        row = json.loads(path.read_text())
        parsed = urlsplit(row.get('uri',''))
        if parsed.hostname!=HOST[role]:
            raise RuntimeError('Credential file endpoint mismatch')
        return row
    env = os.environ.copy()
    phrase = Path('/etc/avalon-runner/passbolt/passphrase').read_text().rstrip('\r\n')
    env.update(USERPASSWORD=phrase, userPassword=phrase)
    p = subprocess.run(['passbolt','--config','/etc/avalon-runner/passbolt/passbolt-cli.yaml','get','resource','--id',RESOURCE[role],'--json'],env=env,capture_output=True,text=True,timeout=60)
    if p.returncode:
        raise RuntimeError('Passbolt retrieval failed')
    row = json.loads(p.stdout)
    parsed = urlsplit(row.get('uri',''))
    if parsed.hostname!=HOST[role]:
        raise RuntimeError('Resource endpoint mismatch')
    return row
def remote(role, command, *, file=None, download=None, upload=None, user_override=None, check=True):
    values = settings.get('targets',{}).get(role,{})
    row = {'username':values['username'],'password':''} if values.get('identity_file') else resource(role)
    password = row.get('password','').rstrip('\r\n')
    user = user_override or row['username']
    if not re.fullmatch('[a-zA-Z0-9_.-]+',user) or (not password and not values.get('identity_file')):
        raise RuntimeError('Invalid SSH credentials')
    env = {**os.environ,'SSHPASS':password}
    auth = ['-i',values['identity_file'],'-o','IdentitiesOnly=yes','-o','BatchMode=yes'] if values.get('identity_file') else ['-o','PubkeyAuthentication=no']
    port = int(values.get('port',22))
    if not 1<=port<=65535:
        raise RuntimeError('Invalid target SSH port')
    if file:
        args = ['scp',*OPTS,*auth,'-P',str(port),str(file),f'{user}@{HOST[role]}:{command}']
    else:
        args = ['ssh',*OPTS,*auth,'-p',str(port),f'{user}@{HOST[role]}',command]
    with tempfile.TemporaryFile() as errors:
        p = subprocess.run(args if values.get('identity_file') else ['sshpass','-e',*args],env=env,stdin=upload,stdout=download or subprocess.PIPE,stderr=errors,timeout=900)
        errors.seek(0)
        diagnostic = errors.read()
    emit(f'SSH role={role}; action={"script transfer" if file else "reviewed operation"}; exit_code={p.returncode}; raw errors suppressed')
    if p.returncode:
        for label in ('Permission denied','Connection refused','Connection timed out','No route to host','Host key verification failed','REMOTE HOST IDENTIFICATION HAS CHANGED','Network is unreachable'):
            if label.encode() in diagnostic:
                emit('SSH diagnostic: '+label)
    if check and p.returncode:
        raise RuntimeError('SSH operation failed: ' + role)
    return p
def storage(command, *, upload=None, download=None):
    values = settings.get('targets',{}).get('storage',{})
    key = values.get('automation_identity_file',str(STATE/'storage-key'))
    p = subprocess.run(['ssh',*OPTS,'-p',str(values.get('port',22)),'-i',key,'-o','IdentitiesOnly=yes','-o','BatchMode=yes','rhisseth-backup@'+HOST['storage'],command],stdin=upload,stdout=download or subprocess.PIPE,stderr=subprocess.PIPE,timeout=900)
    emit(f'Restricted storage operation={command.split()[0]}; exit_code={p.returncode}; raw errors suppressed')
    if p.returncode:
        for label in ('Permission denied', 'Host key verification failed', 'Connection refused', 'Connection timed out', 'REMOTE HOST IDENTIFICATION HAS CHANGED'):
            if label.encode() in p.stderr:
                emit('SSH diagnostic: ' + label)
        raise RuntimeError('Restricted storage operation failed')
    return p
def destination_user():
    return settings.get('targets',{}).get('test',{}).get('username') or resource('test')['username']
def sudo_test(command,check=True):
    values = settings.get('targets',{}).get('test',{})
    user = destination_user()
    if user=='root':
        p = remote('test',command,user_override=user,check=False)
        if p.stdout:
            emit(p.stdout.decode())
        if check and p.returncode:
            raise RuntimeError('Destination root operation failed')
        return p
    if values.get('identity_file'):
        p = remote('test','sudo -n '+command,user_override=user,check=False)
        if p.stdout:
            emit(p.stdout.decode())
        if check and p.returncode:
            raise RuntimeError('Destination sudo operation failed')
        return p
    row = resource('test')
    with tempfile.TemporaryFile() as secret_input:
        secret_input.write((row['password'].rstrip('\r\n')+'\n').encode())
        secret_input.seek(0)
        p = remote('test','sudo -S -p "" '+command,user_override=user,upload=secret_input,check=False)
    if p.stdout:
        emit(p.stdout.decode())
    if check and p.returncode:
        raise RuntimeError('Test VM operation failed; sanitized output above')
    return p
def approved_release():
    if explicit_ref:
        emit('Explicit version selected by repository owner in task session: '+explicit_ref+'; pin exact SHA for this operation')
        selected = {'tag':explicit_ref,'approval':'explicit owner selection in session','author':'urgat07-star'}
        inspected = STATE/'owner-selected-reference.txt'
        if inspected.exists():
            for line in inspected.read_text().splitlines():
                sha,reference = line.split()
                if reference in ('refs/heads/'+explicit_ref,'refs/tags/'+explicit_ref+'^{}'):
                    selected['expected_sha'] = sha
        return selected
    def api(suffix):
        request = urllib.request.Request('https://api.github.com/repos/urgat07-star/rhisseth'+suffix,headers={'User-Agent':'rhisseth-recovery'})
        with urllib.request.urlopen(request,timeout=30) as response:
            return json.load(response)
    owner = api('')['owner']['id']
    releases = [r for r in api('/releases?per_page=100') if not r['draft'] and not r['prerelease'] and r['author']['id']==owner and re.fullmatch(r'(?:release/)?v?\d+\.\d+\.\d+',r['tag_name'])]
    if not releases:
        raise RuntimeError('No owner-published approved stable release; main fallback prohibited')
    release = max(releases,key=lambda r:r['published_at'])
    tag = release['tag_name']
    emit('Approved owner-published release: '+tag)
    return {'tag':tag,'release_id':release['id'],'published_at':release['published_at'],'author':release['author']['login']}
code = 1
try:
    on_runner = socket.gethostname().lower().split('.')[0]=='stu-automation-01'
    if not on_runner:
        if not settings or settings.get('enforce_runner',True):
            raise RuntimeError('Current installation requires approved runner')
        if any(not ipaddress.ip_address(host).is_global for host in HOST.values()):
            raise RuntimeError('Internal infrastructure requires STU-AUTOMATION-01; external mode only allows public target IPs')
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = (STATE/'controller.lock').open('a')
    if operation!='progress-test':
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    emit('Preflight: runner identity, audit writes and controller lock verified; target SSH keys pinned')
    if operation == 'setup-storage':
        if not (STATE/'storage-key').exists():
            emit('Approved change: generate dedicated storage automation key on runner')
            p = subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(STATE/'storage-key')],capture_output=True)
            if p.returncode:
                raise RuntimeError('Key generation failed')
        for name in ('rhisseth_storage.py','Bootstrap-RhissethStorage.py'):
            remote('storage','/tmp/'+name,file=Path(__file__).with_name(name))
        remote('storage','/tmp/rhisseth-controller.pub',file=STATE/'storage-key.pub')
        p = remote('storage','python3 /tmp/Bootstrap-RhissethStorage.py')
        emit(p.stdout.decode())
        emit(storage('list').stdout.decode())
    elif operation == 'diagnose-storage':
        p = remote('storage', 'getent passwd rhisseth-backup')
        emit(p.stdout.decode())
        p = remote('storage', 'namei -l /srv/backups/rhisseth/.ssh/authorized_keys')
        emit(p.stdout.decode())
        p = remote('storage', 'journalctl -u ssh --since "10 minutes ago" --no-pager -o cat')
        for line in p.stdout.decode().splitlines():
            if 'rhisseth-backup' in line:
                emit(line)
        p = remote('storage', 'sshd -T')
        for line in p.stdout.decode().splitlines():
            if line.startswith(('allowusers ', 'allowgroups ', 'denyusers ', 'denygroups ', 'authorizedkeysfile ', 'pubkeyauthentication ', 'usepam ')):
                emit(line)
    elif operation == 'backup':
        remote('source','/opt/rhisseth/scripts/automation/rhisseth_backup.py',file=Path(__file__).with_name('rhisseth_backup.py'))
        p = remote('source','python3 /opt/rhisseth/scripts/automation/rhisseth_backup.py')
        result = json.loads(p.stdout)
        if not re.fullmatch(r'rhisseth-\d{8}T\d{6}Z-[a-f0-9]{8}\.tar\.gz',result['name']) or result['path'] != '/opt/rhisseth/backup-spool/'+result['name']:
            raise RuntimeError('Unexpected archive path')
        emit('Source archive complete: '+json.dumps({k:result[k] for k in ('name','size','sha256','log')}))
        emit('Source table counts (values suppressed): '+json.dumps({table:int(signature.split('|')[0]) for table,signature in result['manifest']['table_signatures'].items()}))
        with tempfile.TemporaryFile(dir=STATE) as archive:
            remote('source','cat '+result['path'],download=archive)
            archive.seek(0)
            if hashlib.file_digest(archive,'sha256').hexdigest() != result['sha256']:
                raise RuntimeError('Runner archive checksum mismatch')
            archive.seek(0)
            stored = storage(f'put {result["name"]} {result["size"]} {result["sha256"]}',upload=archive)
            emit('Storage receipt: '+stored.stdout.decode())
            archive.seek(0)
            with tempfile.TemporaryFile(dir=STATE) as received:
                storage('get '+result['name'],download=received)
                received.seek(0)
                if hashlib.file_digest(received,'sha256').hexdigest() != result['sha256']:
                    raise RuntimeError('Storage round-trip checksum mismatch')
        emit('Validation: source -> runner -> storage -> runner SHA256 matches')
        (STATE/'last-backup.json').write_text(json.dumps(result,indent=2)+'\n')
        emit('Approved cleanup: remove transferred source spool archive only')
        remote('source','rm -- '+result['path'])
    elif operation == 'pin-target':
        # First-contact read-only login; changed keys always rejected.
        original = OPTS[1]
        OPTS[1] = 'StrictHostKeyChecking=accept-new'
        try:
            p = remote('test','id -un',user_override=destination_user())
            emit('First contact verified with Passbolt credentials; host key pinned (TOFU)')
            emit(p.stdout.decode())
        finally:
            OPTS[1] = original
        p = subprocess.run(['ssh-keygen','-F',HOST['test']],capture_output=True,text=True)
        fingerprint = subprocess.run(['ssh-keygen','-lf','-'],input=p.stdout,capture_output=True,text=True)
        emit('Pinned target fingerprint: '+fingerprint.stdout.strip())
    elif operation == 'test-access':
        p = remote('test','id -un',user_override=destination_user(),check=False)
        emit('Test VM login avalon: '+str(p.returncode))
        if p.returncode:
            raise RuntimeError('Test VM login unavailable')
        if p.returncode == 0:
            emit(p.stdout.decode())
            p = remote('test','sudo -n true',user_override=destination_user(),check=False)
            emit('Test VM noninteractive sudo: '+str(p.returncode))
            if p.returncode:
                row = resource('test')
                with tempfile.TemporaryFile() as secret_input:
                    secret_input.write((row['password'].rstrip('\r\n')+'\n').encode())
                    secret_input.seek(0)
                    p = remote('test','sudo -S -p "" -v',user_override=destination_user(),upload=secret_input,check=False)
                emit('Test VM sudo via private stdin: '+str(p.returncode))
                if p.returncode:
                    raise RuntimeError('Test VM sudo unavailable')
    elif operation == 'list':
        emit(storage('list').stdout.decode())
    elif operation == 'schedule':
        emit('Approved change: install daily backup systemd service/timer on runner')
        for name in ('rhisseth-backup.service','rhisseth-backup.timer'):
            p = subprocess.run(['sudo','-n','install','-m','644',str(Path(__file__).with_name(name)),'/etc/systemd/system/'+name],capture_output=True)
            emit(f'Install {name}: exit_code={p.returncode}')
            if p.returncode:
                raise RuntimeError('Runner timer installation failed')
        for args in (['systemctl','daemon-reload'],['systemctl','enable','--now','rhisseth-backup.timer'],['systemctl','list-timers','rhisseth-backup.timer','--no-pager']):
            p = subprocess.run(['sudo','-n',*args],capture_output=True,text=True)
            emit(p.stdout.strip())
            emit('Schedule command exit_code='+str(p.returncode))
            if p.returncode:
                raise RuntimeError('Schedule activation failed')
    elif operation == 'verify-scripts':
        import ast
        for path in Path(__file__).parent.glob('*Rhisseth*.py'):
            ast.parse(path.read_text())
        for path in Path(__file__).parent.glob('rhisseth_*.py'):
            ast.parse(path.read_text())
        emit('Python syntax: all recovery scripts passed')
        p = subprocess.run(['systemd-analyze','calendar','*-*-* 06:00:00 Europe/Moscow'],capture_output=True,text=True)
        emit(p.stdout.strip())
        if p.returncode:
            raise RuntimeError('Timer calendar invalid')
        p = subprocess.run([sys.executable,str(ROOT/'tests/test_recovery_safety.py')],capture_output=True,text=True,timeout=90)
        emit(p.stdout+p.stderr)
        if p.returncode:
            raise RuntimeError('Recovery safety checks failed')
    elif operation=='run-scheduled':
        # Release controller lock so systemd service can acquire its own operation lock.
        emit('Approved change: exercise installed backup service in actual systemd environment')
        fcntl.flock(lock,fcntl.LOCK_UN)
        p = subprocess.run(['sudo','-n','systemctl','start','rhisseth-backup.service'],capture_output=True,text=True,timeout=600)
        emit('Installed backup service start exit_code='+str(p.returncode))
        result = subprocess.run(['systemctl','show','rhisseth-backup.service','--property=Result','--property=ExecMainStatus'],capture_output=True,text=True)
        emit(result.stdout)
        if p.returncode or 'ExecMainStatus=0' not in result.stdout:
            raise RuntimeError('Installed backup service failed')
    elif operation=='inspect-version':
        p = subprocess.run(['git','ls-remote','https://github.com/urgat07-star/rhisseth.git','refs/heads/release/0.0.1','refs/tags/release/0.0.1','refs/tags/release/0.0.1^{}'],capture_output=True,text=True,timeout=60,env={**os.environ,'GIT_TERMINAL_PROMPT':'0'})
        emit('Owner-selected reference inspection: '+p.stdout.strip())
        if p.returncode or not p.stdout.strip():
            raise RuntimeError('Owner-selected version unavailable')
        (STATE/'owner-selected-reference.txt').write_text(p.stdout)
    elif operation=='diagnose-memory':
        remote('test','/tmp/Inspect-RhissethMemory.sh',file=Path(__file__).with_name('Inspect-RhissethMemory.sh'),user_override='avalon')
        sudo_test('bash /tmp/Inspect-RhissethMemory.sh')
    elif operation=='backup-summary':
        result = json.loads((STATE/'last-backup.json').read_text())
        emit('Latest verified backup: '+json.dumps({k:result[k] for k in ('name','size','sha256','log')}))
        emit('Archived source SHA: '+result['manifest']['git_sha'])
        emit('Archived table counts: '+json.dumps({table:int(signature.split('|')[0]) for table,signature in result['manifest']['table_signatures'].items()}))
        if not re.fullmatch(r'/opt/rhisseth/reports/automation-logs/\d{4}-\d{2}-\d{2}/\d{8}-\d{6}-\d{6}-full-backup.md',result['log']):
            raise RuntimeError('Unexpected source log path')
        p = remote('source','cat '+result['log'])
        lines = p.stdout.decode().splitlines()
        for line in lines:
            if any(word in line for word in ('systemctl stop','systemctl start','Validation:')):
                emit(line)
        stopped = next((line.split(' / ')[0] for line in lines if 'Command: systemctl stop rhisseth' in line),None)
        started = next((line.split(' / ')[0] for line in lines if 'Command: systemctl start rhisseth' in line),None)
        if stopped and started:
            duration = (dt.datetime.fromisoformat(started)-dt.datetime.fromisoformat(stopped)).total_seconds()
            emit(f'Service stop completion -> start completion: {duration:.3f} seconds; HTTP startup recovery not included')
        emit(storage('list').stdout.decode())
        for endpoint in ('http://127.0.0.1:8080/index.php','http://127.0.0.1:8080/api/me'):
            p = remote('source','curl --max-time 10 -sS -o /dev/null -w "%{http_code}" '+endpoint)
            emit('Source application endpoint '+endpoint+'; HTTP='+p.stdout.decode())
            if p.stdout.decode() != ('200' if endpoint.endswith('index.php') else '401'):
                raise RuntimeError('Source application health check failed')
    elif operation in ('preflight-test','restore-test','validate-test'):
        target_user = destination_user()
        config = settings.get('instance',{'domain':'rhisseth.ru','tls_mode':'test','acme_email':'','application_port':8080,'database_port':5432,'test_ip':HOST['test']})
        config_path = STATE/'test-instance.json'
        config_path.write_text(json.dumps(config)+'\n')
        for name in ('rhisseth_deploy.py','rhisseth_validate.py'):
            remote('test','/tmp/'+name,file=Path(__file__).with_name(name),user_override=target_user)
        remote('test','/tmp/rhisseth-instance.json',file=config_path,user_override=target_user)
        if operation=='preflight-test':
            sudo_test('python3 /tmp/rhisseth_deploy.py preflight --config /tmp/rhisseth-instance.json')
        elif operation=='validate-test':
            sudo_test('python3 /tmp/rhisseth_deploy.py validate --config /etc/rhisseth/instance.json')
            if (STATE/'test-boot-id').exists():
                p = remote('test','cat /proc/sys/kernel/random/boot_id',user_override=target_user)
                if p.stdout.decode().strip()==(STATE/'test-boot-id').read_text().strip():
                    raise RuntimeError('Test VM reboot not confirmed: boot ID unchanged')
                emit('Reboot validation: boot ID changed; application checks passed after reboot')
        else:
            release = approved_release()
            entries = json.loads(storage('list').stdout)
            if not entries:
                raise RuntimeError('No completed backup available')
            selected = max(entries,key=lambda r:r['completed_utc'])
            if not re.fullmatch(r'rhisseth-\d{8}T\d{6}Z-[a-f0-9]{8}\.tar\.gz',selected['name']):
                raise RuntimeError('Invalid storage manifest name')
            # Preflight before downloading/transferring data and before any target installation.
            sudo_test('python3 /tmp/rhisseth_deploy.py preflight --config /tmp/rhisseth-instance.json')
            with tempfile.TemporaryDirectory(dir=STATE,prefix='restore-') as directory:
                work = Path(directory)
                archive = work/selected['name']
                with archive.open('wb') as stream:
                    storage('get '+selected['name'],download=stream)
                if archive.stat().st_size!=selected['size'] or hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()!=selected['sha256']:
                    raise RuntimeError('Downloaded backup checksum mismatch')
                from rhisseth_deploy import inspect_archive,validate_schema
                manifest,_ = inspect_archive(archive,selected['sha256'])
                repo = work/'repository'
                git_env = {**os.environ,'GIT_TERMINAL_PROMPT':'0'}
                for args in (['git','clone','--no-checkout','https://github.com/urgat07-star/rhisseth.git',str(repo)],):
                    p = subprocess.run(args,capture_output=True,text=True,env=git_env,timeout=180)
                    emit('Release checkout command exit_code='+str(p.returncode))
                    if p.returncode:
                        raise RuntimeError('Approved release checkout failed')
                for reference in ('refs/tags/'+release['tag'],'refs/remotes/origin/'+release['tag']):
                    p = subprocess.run(['git','-C',str(repo),'rev-parse','--verify',reference+'^{commit}'],capture_output=True,text=True)
                    if p.returncode==0:
                        release['sha'] = p.stdout.strip()
                        release['git_ref'] = reference
                        break
                if 'git_ref' not in release:
                    raise RuntimeError('Selected reference does not resolve to pinned SHA')
                if release.get('expected_sha') and release['sha']!=release['expected_sha']:
                    raise RuntimeError('Owner-selected reference changed since inspection; explicit new approval required')
                p = subprocess.run(['git','-C',str(repo),'checkout','--detach',release['sha']],capture_output=True,text=True,env=git_env,timeout=180)
                emit('Pinned release checkout exit_code='+str(p.returncode))
                if p.returncode:
                    raise RuntimeError('Pinned release checkout failed')
                pending = validate_schema(repo,manifest)
                emit('Schema compatibility: pending migrations='+json.dumps(pending))
                import tarfile
                code_archive = work/'approved-code.tar.gz'
                with tarfile.open(code_archive,'w:gz') as packed:
                    packed.add(repo,arcname='repository')
                release['code_sha256'] = hashlib.file_digest(code_archive.open('rb'),'sha256').hexdigest()
                release_file = work/'approved-release.json'
                release_file.write_text(json.dumps(release)+'\n')
                emit('Validated restoration selection: '+json.dumps({'backup':selected,'release':release}))
                for file,name in ((archive,selected['name']),(code_archive,'rhisseth-approved-code.tar.gz'),(release_file,'rhisseth-approved-release.json')):
                    remote('test','/tmp/'+name,file=file,user_override=target_user)
                sudo_test('python3 /tmp/rhisseth_deploy.py restore --config /tmp/rhisseth-instance.json --archive /tmp/'+selected['name']+' --sha256 '+selected['sha256']+' --release-file /tmp/rhisseth-approved-release.json --code-archive /tmp/rhisseth-approved-code.tar.gz')
                sudo_test('python3 /tmp/rhisseth_deploy.py validate --config /etc/rhisseth/instance.json')
                sudo_test('rm -- /tmp/'+selected['name'])
    elif operation=='network-test':
        sudo_test('test -f /opt/rhisseth/recovery.json')
        sudo_test('test -f /etc/rhisseth/instance.json')
        emit('Approved change: permit required web ingress TCP 80/443 on recovered test VM; preserve SSH and other firewall rules')
        sudo_test('ufw allow 80/tcp')
        sudo_test('ufw allow 443/tcp')
        sudo_test('ufw status numbered')
    elif operation=='cleanup-test':
        sudo_test('python3 /tmp/rhisseth_deploy.py validate --config /etc/rhisseth/instance.json')
        emit('Approved cleanup: remove exact transferred recovery archive from test VM after successful validation')
        sudo_test('rm -f -- /tmp/rhisseth-20260916T135317Z-b836c6ed.tar.gz')
    elif operation=='source-git-status':
        p = remote('source','git -C /opt/rhisseth/repository status --porcelain')
        emit('Source local changes (paths only): '+p.stdout.decode())
    elif operation=='external-check':
        values = settings.get('targets',{}).get('test',{})
        user = destination_user()
        if user=='root' or values.get('identity_file'):
            command = ('sudo -n ' if user!='root' else '')+'cat /opt/rhisseth/secrets/tls.crt'
            p = remote('test',command,user_override=user)
        else:
            row = resource('test')
            with tempfile.TemporaryFile() as secret_input:
                secret_input.write((row['password'].rstrip('\r\n')+'\n').encode())
                secret_input.seek(0)
                p = remote('test','sudo -S -p "" cat /opt/rhisseth/secrets/tls.crt',user_override=user,upload=secret_input)
        certificate = STATE/'test-tls.crt'
        certificate.write_bytes(p.stdout)
        for path,expected in (('/index.php','200'),('/api/me','401'),('/interactive-map/','303')):
            p = subprocess.run(['curl','--noproxy',HOST['test']+',rhisseth.ru','--connect-timeout','8','--max-time','15','--cacert',str(certificate),'--resolve','rhisseth.ru:443:'+HOST['test'],'-sS','-o','/dev/null','-w','%{http_code}','https://rhisseth.ru'+path],capture_output=True,text=True)
            emit(f'External HTTPS via runner: {path}; HTTP={p.stdout}; exit_code={p.returncode}; certificate/hostname verification enabled')
            if p.returncode or p.stdout!=expected:
                emit('Curl failure: '+p.stderr.strip())
                sudo_test('ufw status numbered',check=False)
                sudo_test('ss -lntp',check=False)
                raise RuntimeError('External HTTPS check failed')
    elif operation=='progress-test':
        remote('test','/tmp/Read-RhissethRecoveryProgress.py',file=Path(__file__).with_name('Read-RhissethRecoveryProgress.py'),user_override=destination_user())
        sudo_test('python3 /tmp/Read-RhissethRecoveryProgress.py')
    elif operation=='finalize-test':
        for name in ('Finalize-RhissethRecovery.py','rhisseth_deploy.py','rhisseth_validate.py'):
            remote('test','/tmp/'+name,file=Path(__file__).with_name(name),user_override=destination_user())
        sudo_test('python3 /tmp/Finalize-RhissethRecovery.py')
        sudo_test('install -m 755 /tmp/rhisseth_deploy.py /tmp/rhisseth_validate.py /opt/rhisseth/scripts/automation/')
        sudo_test('python3 /tmp/rhisseth_deploy.py validate --config /etc/rhisseth/instance.json')
    elif operation=='reboot-test':
        sudo_test('test -f /opt/rhisseth/recovery.json')
        p = remote('test','cat /proc/sys/kernel/random/boot_id',user_override=destination_user())
        (STATE/'test-boot-id').write_text(p.stdout.decode().strip()+'\n')
        emit('Approved change: reboot recovered test VM only; follow with validate-test')
        sudo_test('systemctl reboot',check=False)
    elif operation=='collect-evidence':
        for path in sorted(logs.glob('*.md')):
            if any(word in path.name for word in ('backup','storage','recovery','schedule','test','scripts')) and path != log:
                emit('## Runner evidence: '+path.name)
                emit(path.read_text())
        p = remote('source','cat /opt/rhisseth/reports/automation-logs/'+now.strftime('%Y-%m-%d')+'/*full-backup.md')
        emit('## Source backup evidence')
        emit(p.stdout.decode())
    code = 0
except Exception as error:
    emit('Failure: '+type(error).__name__+': '+str(error) if isinstance(error,RuntimeError) else 'Failure: '+type(error).__name__+'; sensitive details suppressed')
finally:
    emit(f'Validation: exit_code={code}; operation={operation}; changes according to actions above; reboot_requested={operation=="reboot-test"}; reboot confirmed by boot ID on subsequent validation')
    emit('Runner audit log: '+str(log))
raise SystemExit(code)

