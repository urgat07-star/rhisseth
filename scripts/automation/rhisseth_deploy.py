#!/usr/bin/python3
"""Native recovery on a target VM; root, stdlib Python, no Docker required."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import secrets
import shutil
import socket
import subprocess
import tarfile
import tempfile
import time
import urllib.request
from zoneinfo import ZoneInfo

ROOT = Path('/opt/rhisseth')
PACKAGES = ['git','nginx','postgresql-16','postgresql-client-16','python3-venv','python3-pip','ca-certificates','openssl','openssh-client','tar','gzip','curl','certbot','python3-certbot-nginx']
os.umask(0o077)

def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def validate_schema(repo,manifest):
    migrations = sorted(p.name for p in (Path(repo)/'data/migrations').glob('*.sql'))
    applied = manifest['schema_migrations']
    if applied != migrations[:len(applied)]:
        raise RuntimeError('Archive schema is not a supported release migration prefix')
    for name in applied:
        expected = manifest.get('migrations_sha256',{}).get(name)
        if expected and digest(Path(repo)/'data/migrations'/name) != expected:
            raise RuntimeError('Previously applied migration was modified')
    return migrations[len(applied):]

def inspect_archive(path, expected):
    if digest(path) != expected:
        raise RuntimeError('Archive SHA256 mismatch')
    with tarfile.open(path,'r:gz') as archive:
        members = archive.getmembers()
        names = set()
        total = 0
        for member in members:
            p = PurePosixPath(member.name)
            if p.is_absolute() or '..' in p.parts or not p.parts or p.parts[0] not in ('manifest.json','database.dump','project','configuration'):
                raise RuntimeError('Unsafe archive path')
            if member.name in names:
                raise RuntimeError('Duplicate archive member')
            names.add(member.name)
            if not (member.isfile() or member.isdir() or member.issym()):
                raise RuntimeError('Unsupported archive member')
            # Configuration symlinks are evidence only and are never extracted/applied.
            if member.issym() and p.parts[0] != 'configuration':
                raise RuntimeError('Project symlinks require explicit review')
            total += member.size
            if total > 8 * 1024**3:
                raise RuntimeError('Archive expands beyond supported size')
        manifest_file = archive.extractfile('manifest.json')
        if manifest_file is None:
            raise RuntimeError('Manifest absent')
        manifest = json.loads(manifest_file.read(1024 * 1024))
        if manifest.get('format') != 1 or manifest.get('postgresql_major') != 16:
            raise RuntimeError('Unsupported archive format/database major')
        if not re.fullmatch('[a-f0-9]{40}',manifest.get('git_sha','')):
            raise RuntimeError('Invalid source SHA')
        hashes = manifest.get('files_sha256',{})
        actual_files = {m.name for m in members if m.isfile() and m.name != 'manifest.json'}
        if set(hashes) != actual_files:
            raise RuntimeError('Manifest does not cover every regular file')
        for name, expected_hash in hashes.items():
            with archive.extractfile(name) as stream:
                if hashlib.file_digest(stream,'sha256').hexdigest() != expected_hash:
                    raise RuntimeError('Archive member checksum mismatch')
        return manifest, total

def main():
    import fcntl  # Linux-only locking is needed for deployment, not archive inspection.
    parser = argparse.ArgumentParser()
    parser.add_argument('operation',choices=['preflight','restore','apply-config','validate'])
    parser.add_argument('--archive')
    parser.add_argument('--sha256')
    parser.add_argument('--config',default='/etc/rhisseth/instance.json')
    parser.add_argument('--release-file')
    parser.add_argument('--code-archive')
    args = parser.parse_args()
    now = dt.datetime.now(dt.timezone.utc)
    logs = Path('/var/log/rhisseth/reports/automation-logs') / now.strftime('%Y-%m-%d')
    logs.mkdir(parents=True,exist_ok=True)
    log = logs / (now.strftime('%Y%m%d-%H%M%S-%f')+'-'+args.operation+'.md')
    log.write_text(f'# Rhisseth {args.operation}\n\nUTC: {now.isoformat()}\n\nMoscow: {now.astimezone(ZoneInfo("Europe/Moscow")).isoformat()}\n\nTask: backup-and-portable-deployment; controller: approved SSH controller\n\nRunner: STU-AUTOMATION-01 / 10.210.52.128 (current execution)\n\nTarget: {socket.gethostname()}; local Rhisseth runtime; GitHub urgat07-star/rhisseth\n\nAction: {args.operation}; reboot: false\n')
    def emit(value):
        with log.open('a') as stream:
            stream.write(str(value)+'\n')
            stream.flush()
            os.fsync(stream.fileno())
        print(value,flush=True)
    def run(command, *, input=None, check=True, private=False, env=None):
        result = subprocess.run(command,input=input,capture_output=True,text=True,env=env,timeout=900)
        emit(f'Command: {" ".join(command)}; exit_code={result.returncode}')
        if not private:
            # Commands selected below never dump environment, passwords or user records.
            emit(result.stdout.strip())
        if check and result.returncode:
            raise RuntimeError('Command failed: '+command[0]+'; raw errors suppressed')
        return result
    code, changed = 1, False
    try:
        if os.geteuid() != 0:
            raise RuntimeError('Root required')
        lock = Path('/run/lock/rhisseth-deployment.lock').open('a')
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        config = json.loads(Path(args.config).read_text())
        domain = config['domain']
        if not re.fullmatch(r'(?=.{1,253}$)[a-zA-Z0-9]+(?:[.-][a-zA-Z0-9]+)*',domain) or '.' not in domain:
            raise RuntimeError('Invalid domain')
        if config.get('application_port') != 8080 or config.get('database_port') != 5432:
            raise RuntimeError('This implementation supports ports 8080/5432; conflict cannot be bypassed')
        if config.get('tls_mode') not in ('public','test'):
            raise RuntimeError('Invalid TLS mode')
        test_ip = str(config.get('test_ip',''))
        if config['tls_mode']=='test':
            import ipaddress
            ipaddress.ip_address(test_ip)
        if args.operation=='restore' and (ROOT/'recovery.json').exists():
            existing = json.loads((ROOT/'recovery.json').read_text())
            requested = json.loads(Path(args.release_file).read_text()) if args.release_file else {}
            if existing.get('archive_sha256')==args.sha256 and existing.get('release',{}).get('sha')==requested.get('sha'):
                emit('Idempotent restore: same archive/release already restored; existing data preserved; run validate separately')
                code = 0
                return code
            raise RuntimeError('Existing recovered instance differs; replacement requires separate recovery plan')
        def render_nginx():
            cert = '/etc/letsencrypt/live/'+domain+'/fullchain.pem' if config['tls_mode']=='public' else str(ROOT/'secrets/tls.crt')
            key = '/etc/letsencrypt/live/'+domain+'/privkey.pem' if config['tls_mode']=='public' else str(ROOT/'secrets/tls.key')
            template = (ROOT/'repository/deploy/native/nginx.conf').read_text()
            template = template.replace('62.113.109.168 rhisseth.ru',domain)
            template = template.replace('/opt/rhisseth/secrets/tls.crt',cert).replace('/opt/rhisseth/secrets/tls.key',key)
            template = template.replace('    return 301 https://$host$request_uri;', '    location ^~ /.well-known/acme-challenge/ { root /var/lib/rhisseth-acme; }\n    location / { return 301 https://$host$request_uri; }')
            return template
        def configure_tls():
            if config['tls_mode']=='public':
                email = config.get('acme_email','')
                if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):
                    raise RuntimeError('Public TLS requires ACME email in instance config')
                resolved = {r[4][0] for r in socket.getaddrinfo(domain,443,type=socket.SOCK_STREAM)}
                local = set(run(['hostname','-I'],private=True).stdout.split())
                if config.get('public_ip'):
                    local.add(config['public_ip'])
                if not resolved or not resolved.issubset(local):
                    raise RuntimeError('Domain DNS points elsewhere; public TLS configuration not changed')
                webroot = Path('/var/lib/rhisseth-acme')
                webroot.mkdir(mode=0o755,exist_ok=True)
                webroot.chmod(0o755)
                site = Path('/etc/nginx/sites-available/rhisseth')
                previous = site.read_bytes() if site.exists() else None
                enabled = Path('/etc/nginx/sites-enabled/rhisseth')
                created = not enabled.exists()
                emit('Approved change: enable ACME webroot for configured domain; preserve prior vhost on failure')
                site.write_text('server { listen 80; listen [::]:80; server_name '+domain+'; location ^~ /.well-known/acme-challenge/ { root /var/lib/rhisseth-acme; } location / { return 301 https://$host$request_uri; } }\n')
                site.chmod(0o644)
                if created:
                    enabled.symlink_to(site)
                try:
                    run(['nginx','-t'])
                    run(['systemctl','enable','--now','nginx'])
                    run(['systemctl','reload','nginx'])
                    run(['certbot','certonly','--webroot','-w',str(webroot),'--non-interactive','--agree-tos','--email',email,'-d',domain,'--deploy-hook','systemctl reload nginx'],private=True)
                    run(['systemctl','enable','--now','certbot.timer'])
                except Exception:
                    if previous is None:
                        site.unlink(missing_ok=True)
                    else:
                        site.write_bytes(previous)
                    if created:
                        enabled.unlink(missing_ok=True)
                    run(['systemctl','reload','nginx'],check=False)
                    raise
            else:
                run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','30','-keyout',str(ROOT/'secrets/tls.key'),'-out',str(ROOT/'secrets/tls.crt'),'-subj','/CN='+domain,'-addext','subjectAltName=DNS:'+domain+',IP:'+test_ip],private=True)
                (ROOT/'secrets/tls.key').chmod(0o600)
        def apply_nginx():
            site = Path('/etc/nginx/sites-available/rhisseth')
            previous = site.read_bytes() if site.exists() else None
            emit('Approved change: write project nginx configuration from instance.json')
            site.write_text(render_nginx())
            site.chmod(0o644)
            enabled = Path('/etc/nginx/sites-enabled/rhisseth')
            created = not enabled.exists()
            if created:
                enabled.symlink_to(site)
            if run(['nginx','-t'],check=False).returncode:
                if previous is None:
                    site.unlink(missing_ok=True)
                else:
                    site.write_bytes(previous)
                if created:
                    enabled.unlink(missing_ok=True)
                raise RuntimeError('Nginx validation failed; previous configuration restored')
            run(['systemctl','enable','--now','nginx'])
            run(['systemctl','reload','nginx'])
        if args.operation in ('preflight','restore'):
            conflicts = []
            os_release = Path('/etc/os-release').read_text()
            if 'ID=ubuntu\n' not in os_release or 'VERSION_ID="24.04"' not in os_release:
                conflicts.append('Requires Ubuntu 24.04')
            if platform.machine() != 'x86_64':
                conflicts.append('Supported architecture: x86_64')
            memory = int(re.search(r'MemTotal:\s+(\d+)',Path('/proc/meminfo').read_text())[1])*1024
            if (os.cpu_count() or 0) < 1 or memory < 900*1024**2:
                conflicts.append('Insufficient CPU/RAM (allows OS-visible memory of 1 GB VM)')
            for command in (['free','-m'],['df','-B1','/'],['ss','-lntp']):
                run(command)
            for port in (80,443,5432,8080):
                # Inspect kernel socket table to avoid bind/address family ambiguity.
                for family in ('tcp','tcp6'):
                    for line in Path('/proc/net/'+family).read_text().splitlines()[1:]:
                        columns = line.split()
                        if columns[3]=='0A' and int(columns[1].split(':')[1],16)==port:
                            conflicts.append(f'Required port {port} occupied ({family}); see ss -lntp evidence')
            for unit in ('nginx','apache2','caddy','postgresql','postgresql@16-main','rhisseth'):
                state = run(['systemctl','is-active',unit],check=False,private=True).stdout.strip()
                emit(f'Service {unit}: {state}')
                if state in ('active','activating'):
                    conflicts.append('Existing active service: '+unit)
            if ROOT.exists():
                conflicts.append('Existing /opt/rhisseth; recovery never overwrites an existing instance')
            import pwd
            try:
                pwd.getpwnam('rhisseth')
                conflicts.append('Existing rhisseth OS account requires review')
            except KeyError:
                pass
            if Path('/var/lib/postgresql').exists() and any(Path('/var/lib/postgresql').glob('*/main/PG_VERSION')):
                conflicts.append('Existing PostgreSQL cluster/data; requires review even if stopped')
            if Path('/etc/nginx/sites-enabled').exists():
                for site in Path('/etc/nginx/sites-enabled').iterdir():
                    if site.name != 'default':
                        conflicts.append('Existing enabled nginx site: '+site.name)
            run(['dpkg-query','-W','-f=${Package} ${Version}\n',*PACKAGES],check=False)
            for endpoint in ('https://pypi.org/simple/','https://archive.ubuntu.com/ubuntu/dists/noble/Release','https://api.github.com/repos/urgat07-star/rhisseth'):
                try:
                    request = urllib.request.Request(endpoint,headers={'User-Agent':'rhisseth-recovery-preflight'})
                    with urllib.request.urlopen(request,timeout=15) as response:
                        emit('Network preflight: '+endpoint+'; HTTP='+str(response.status))
                except Exception:
                    conflicts.append('Required package/source endpoint unavailable: '+endpoint)
            archive_size = 0
            manifest = None
            if args.archive:
                if not args.sha256 or not re.fullmatch('[a-f0-9]{64}',args.sha256):
                    raise RuntimeError('Expected archive SHA256 required')
                manifest,archive_size = inspect_archive(args.archive,args.sha256)
                emit('Archive validation: all hashes and safe paths verified')
            if shutil.disk_usage('/').free < 2*archive_size + 2*1024**3:
                conflicts.append('Insufficient free disk for installation/extraction/database workspace')
            if config['tls_mode']=='public':
                if not config.get('acme_email'):
                    conflicts.append('ACME email missing from config')
                try:
                    addresses = sorted({r[4][0] for r in socket.getaddrinfo(domain,443,type=socket.SOCK_STREAM)})
                    emit('Domain DNS addresses: '+json.dumps(addresses))
                    local_addresses = run(['hostname','-I'],private=True).stdout.split()
                    expected_ip = config.get('public_ip')
                    allowed = set(local_addresses + ([expected_ip] if expected_ip else []))
                    if not addresses or not set(addresses).issubset(allowed):
                        conflicts.append('Domain DNS does not exclusively point to this VM/public_ip; configure DNS before public TLS')
                except socket.gaierror:
                    conflicts.append('Domain DNS unavailable')
            release = json.loads(Path(args.release_file).read_text()) if args.release_file else None
            if args.operation=='restore':
                if not manifest or not release:
                    conflicts.append('Archive and approved release metadata required')
                elif not re.fullmatch(r'(?:release/)?v?\d+\.\d+\.\d+',release.get('tag','')) or not re.fullmatch('[a-f0-9]{40}',release.get('sha','')):
                    conflicts.append('Invalid approved release metadata')
            emit('Preflight conflicts: '+json.dumps(conflicts,ensure_ascii=False))
            if conflicts:
                raise RuntimeError('Preflight failed; installation/data changes not started')
            emit('Preflight: passed; no additional confirmation required')
            if args.operation=='preflight':
                code = 0
                return code
            emit('Approved change: create isolated repository workspace for release/schema validation')
            with tempfile.TemporaryDirectory(prefix='rhisseth-release-') as checkout:
                repo = Path(checkout)/'repository'
                git_env = {**os.environ,'GIT_TERMINAL_PROMPT':'0'}
                if args.code_archive:
                    if digest(args.code_archive)!=release.get('code_sha256'):
                        raise RuntimeError('Approved code archive checksum mismatch')
                    with tarfile.open(args.code_archive,'r:gz') as packed:
                        members = packed.getmembers()
                        if sum(m.size for m in members)>512*1024**2:
                            raise RuntimeError('Code archive too large')
                        for member in members:
                            path = PurePosixPath(member.name)
                            if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0]!='repository' or not (member.isfile() or member.isdir()):
                                raise RuntimeError('Unsafe code archive')
                        packed.extractall(checkout,filter='data')
                else:
                    if not shutil.which('git'):
                        raise RuntimeError('Provide controller-validated code archive when Git is unavailable')
                    run(['git','clone','--no-checkout','https://github.com/urgat07-star/rhisseth.git',str(repo)],env=git_env,private=True)
                    run(['git','-C',str(repo),'checkout','--detach',release['sha']],env=git_env,private=True)
                if shutil.which('git'):
                    actual_sha = run(['git','-C',str(repo),'rev-parse','HEAD'],private=True).stdout.strip()
                    reference = release.get('git_ref','refs/tags/'+release['tag'])
                    if reference not in ('refs/tags/'+release['tag'],'refs/remotes/origin/'+release['tag']):
                        raise RuntimeError('Invalid approved Git reference')
                    tag_sha = run(['git','-C',str(repo),'rev-parse',reference+'^{commit}'],private=True).stdout.strip()
                    if actual_sha != release['sha'] or tag_sha != actual_sha:
                        raise RuntimeError('Release tag/SHA changed')
                pending = validate_schema(repo,manifest)
                emit('Schema compatibility: pending migrations='+json.dumps(pending))
                if not (repo/'app/backend/requirements.lock').is_file() or not (repo/'deploy/native/nginx.conf').is_file():
                    raise RuntimeError('Release runtime files missing')
                emit('Release/schema compatibility passed: '+json.dumps(release))
                apt_env = {**os.environ,'DEBIAN_FRONTEND':'noninteractive','NEEDRESTART_MODE':'l'}
                emit('Approved change: install missing runtime packages')
                changed = True
                run(['apt-get','update'],env=apt_env,private=True)
                run(['apt-get','install','-y','--no-install-recommends',*PACKAGES],env=apt_env,private=True)
                if run(['git','-C',str(repo),'rev-parse','HEAD'],private=True).stdout.strip()!=release['sha']:
                    raise RuntimeError('Installed Git validation: code SHA differs')
                ROOT.mkdir(mode=0o755)
                ROOT.chmod(0o755)
                (ROOT/'reports').mkdir(mode=0o755)
                (ROOT/'reports').chmod(0o755)
                shutil.copytree(repo,ROOT/'repository')
                for parent,dirs,files in os.walk(ROOT/'repository'):
                    Path(parent).chmod(0o755)
                    for name in files:
                        path = Path(parent)/name
                        if not path.is_symlink():
                            path.chmod(0o755 if path.stat().st_mode & 0o111 else 0o644)
            with tempfile.TemporaryDirectory(prefix='rhisseth-data-') as temporary:
                work = Path(temporary)
                with tarfile.open(args.archive,'r:gz') as archive:
                    for member in archive.getmembers():
                        if not member.issym():
                            archive.extract(member,work,filter='data')
                for path in (work/'project').iterdir():
                    if path.name == 'secrets':
                        continue
                    if path.is_dir():
                        shutil.copytree(path,ROOT/path.name)
                    else:
                        shutil.copy2(path,ROOT/path.name)
                run(['useradd','--system','--home-dir',str(ROOT),'--shell','/usr/sbin/nologin','rhisseth'])
                private = ROOT/'secrets'
                private.mkdir(mode=0o711)
                private.chmod(0o711)
                # Preserve historical secrets privately; generate target DB connection independently.
                historical = private/'source-secrets'
                if (work/'project/secrets').exists():
                    shutil.copytree(work/'project/secrets',historical)
                    historical.chmod(0o700)
                password = secrets.token_urlsafe(36)
                password_file = private/'db-password.txt'
                password_file.write_text(password+'\n')
                password_file.chmod(0o640)
                shutil.chown(password_file,user='root',group='rhisseth')
                (private/'app.env').write_text('DB_HOST=127.0.0.1\nDB_PASSWORD_FILE=/opt/rhisseth/secrets/db-password.txt\n')
                (private/'app.env').chmod(0o600)
                run(['systemctl','enable','--now','postgresql'])
                run(['systemctl','start','postgresql@16-main'])
                tuning = ROOT/'repository/deploy/native/postgresql-test.conf'
                if tuning.exists():
                    shutil.copy2(tuning,'/etc/postgresql/16/main/conf.d/rhisseth.conf')
                    Path('/etc/postgresql/16/main/conf.d/rhisseth.conf').chmod(0o644)
                    run(['systemctl','restart','postgresql@16-main'])
                # Secret SQL is stdin only and all result output is suppressed.
                sql = "CREATE ROLE rhisseth LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD '"+password+"';\nCREATE DATABASE rhisseth OWNER rhisseth;\n"
                run(['runuser','-u','postgres','--','psql','-X','-v','ON_ERROR_STOP=1'],input=sql,private=True)
                dump = work/'database.dump'
                dump.chmod(0o644)
                work.chmod(0o755)
                run(['runuser','-u','postgres','--','pg_restore','--exit-on-error','--single-transaction','--no-owner','--no-acl','--role=rhisseth','-d','rhisseth',str(dump)],private=True)
                for table,expected in manifest['table_signatures'].items():
                    if not re.fullmatch('[a-zA-Z_][a-zA-Z0-9_]*',table):
                        raise RuntimeError('Invalid signature table')
                    ordering = 'row_value COLLATE "C"' if manifest.get('signature_order')=='C' else 'row_value'
                    timezone = "SET TIME ZONE 'UTC'; " if manifest.get('signature_timezone')=='UTC' else ''
                    sql = f'''{timezone}SELECT count(*), md5(COALESCE(string_agg(row_value, E'\\n' ORDER BY {ordering}),'')) FROM (SELECT row_to_json(t)::text AS row_value FROM "{table}" t) s'''
                    actual = run(['runuser','-u','postgres','--','psql','-X','-At','-d','rhisseth','-c',sql],private=True).stdout.strip().splitlines()[-1]
                    if actual != expected:
                        raise RuntimeError('Restored database signature mismatch: '+table)
                    emit('Restored table signature matches: '+table)
            run(['python3','-m','venv',str(ROOT/'venv')])
            run([str(ROOT/'venv/bin/pip'),'install','--no-cache-dir','--disable-pip-version-check','-r',str(ROOT/'repository/app/backend/requirements.lock')],private=True)
            for parent,dirs,files in os.walk(ROOT/'venv'):
                Path(parent).chmod(0o755)
                for name in files:
                    path = Path(parent)/name
                    if not path.is_symlink():
                        path.chmod(0o755 if path.stat().st_mode & 0o111 else 0o644)
            app_env = {**os.environ,'DB_HOST':'127.0.0.1','DB_PASSWORD_FILE':str(ROOT/'secrets/db-password.txt')}
            run([str(ROOT/'venv/bin/python'),str(ROOT/'repository/app/backend/migrate.py')],env=app_env)
            shutil.copy2(ROOT/'repository/deploy/native/rhisseth.service','/etc/systemd/system/rhisseth.service')
            Path('/etc/systemd/system/rhisseth.service').chmod(0o644)
            logrotate = ROOT/'repository/deploy/native/nginx-logrotate.conf'
            if logrotate.exists():
                shutil.copy2(logrotate,'/etc/logrotate.d/rhisseth')
                Path('/etc/logrotate.d/rhisseth').chmod(0o644)
            config_dir = Path('/etc/rhisseth')
            config_dir.mkdir(mode=0o755,exist_ok=True)
            config_dir.chmod(0o755)
            if Path(args.config).resolve() != (config_dir/'instance.json').resolve():
                shutil.copy2(args.config,config_dir/'instance.json')
            (config_dir/'instance.json').chmod(0o644)
            configure_tls()
            apply_nginx()
            if shutil.which('ufw'):
                firewall = subprocess.run(['ufw','status'],capture_output=True,text=True,env={**os.environ,'LC_ALL':'C'})
                if firewall.returncode:
                    raise RuntimeError('Cannot inspect firewall status')
                if 'Status: active' in firewall.stdout:
                    run(['ufw','allow','80/tcp'])
                    run(['ufw','allow','443/tcp'])
            run(['systemctl','daemon-reload'])
            run(['systemctl','enable','--now','rhisseth'])
            restored = {'release':release,'archive':Path(args.archive).name,'archive_sha256':args.sha256,'restored_utc':now.isoformat(),'source_manifest':manifest}
            scripts = ROOT/'scripts/automation'
            scripts.mkdir(mode=0o755,parents=True,exist_ok=True)
            scripts.parent.chmod(0o755)
            for source in (Path(__file__),Path(__file__).with_name('rhisseth_validate.py')):
                shutil.copy2(source,scripts/source.name)
                (scripts/source.name).chmod(0o755)
            (ROOT/'recovery.json').write_text(json.dumps(restored,indent=2)+'\n')
            (ROOT/'release.json').write_text(json.dumps({'git_commit':release['sha'],'release_tag':release['tag']})+'\n')
            emit('Restore complete; run validate before acceptance')
        elif args.operation=='apply-config':
            if not (ROOT/'recovery.json').exists():
                raise RuntimeError('Managed recovered instance required')
            emit('Preflight: managed instance/config validated; applying project configuration')
            changed = True
            site = Path('/etc/nginx/sites-available/rhisseth')
            previous = site.read_bytes()
            try:
                configure_tls()
                apply_nginx()
            except Exception:
                emit('Rollback: restore complete previous project vhost after configuration failure')
                site.write_bytes(previous)
                run(['nginx','-t'],check=False)
                run(['systemctl','reload','nginx'],check=False)
                raise
        elif args.operation=='validate':
            if not (ROOT/'recovery.json').exists():
                raise RuntimeError('Recovery metadata absent')
            for unit in ('rhisseth','nginx','postgresql@16-main'):
                run(['systemctl','is-active',unit])
            for attempt in range(30):
                try:
                    with urllib.request.urlopen('http://127.0.0.1:8080/index.php',timeout=3) as response:
                        if response.status==200:
                            break
                except Exception:
                    time.sleep(1)
            else:
                raise RuntimeError('Application login page unavailable')
            validator = Path(__file__).with_name('rhisseth_validate.py')
            run([str(ROOT/'venv/bin/python'),str(validator),'--config',args.config],private=False)
            run(['free','-m'])
            run(['df','-h','/'])
            emit('Validation: runtime and application checks passed')
        code = 0
    except Exception as error:
        emit('Failure: '+str(error) if isinstance(error,RuntimeError) else 'Failure: '+type(error).__name__+'; sensitive details suppressed')
    finally:
        emit(f'Validation: exit_code={code}; changed={changed}; reboot=false; elapsed_seconds={(dt.datetime.now(dt.timezone.utc)-now).total_seconds():.1f}')
        emit('Target audit log: '+str(log))
    return code
if __name__=='__main__':
    raise SystemExit(main())
