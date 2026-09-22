"""Local Docker controller for the selected Rhisseth VDS. No secrets in argv."""
import argparse
import datetime as dt
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('operation', choices=['inspect', 'update'])
parser.add_argument('--known-hosts', required=True)
auth = parser.add_mutually_exclusive_group(required=True)
auth.add_argument('--ssh-key')
auth.add_argument('--password-file')
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
now = dt.datetime.now(dt.timezone.utc)
directory = root / 'reports/automation-logs' / now.strftime('%Y-%m-%d')
directory.mkdir(parents=True, exist_ok=True)
log = directory / (now.strftime('%Y%m%d-%H%M%S') + '-islands-v2-local-docker.md')
log.write_text(f'# Rhisseth island comparison through local Docker\n\nUTC: {now.isoformat()}\n'
               f'Target: root@62.113.109.168:22\nOperation: {args.operation}\n'
               'Contact: urgat07@gmail.com\nReboot: no\n', encoding='utf-8')
secret = ''

def emit(value):
    text = str(value)
    if secret:
        text = text.replace(secret, '<redacted>')
    with log.open('a', encoding='utf-8') as stream:
        stream.write(text + '\n')
    print(text, flush=True)

def run(command, *, env=None, timeout=60):
    result = subprocess.run(command, capture_output=True, text=True,
                            env=env, timeout=timeout)
    emit(result.stdout)
    emit(result.stderr)
    if result.returncode:
        raise RuntimeError(f'Command failed: exit {result.returncode}')
    return result.stdout

code = 1
try:
    if not Path(args.known_hosts).is_file():
        raise RuntimeError('Verified known_hosts file required')
    run(['ssh-keygen', '-F', '62.113.109.168', '-f', args.known_hosts])
    options = ['-o', 'StrictHostKeyChecking=yes', '-o',
               f'UserKnownHostsFile={args.known_hosts}', '-o', 'ConnectTimeout=12']
    env = os.environ.copy()
    prefix = []
    with tempfile.TemporaryDirectory(prefix='rhisseth-ssh-', dir='/run') as scratch:
        if args.ssh_key:
            key = Path(scratch) / 'key'
            shutil.copyfile(args.ssh_key, key)
            key.chmod(0o600)
            options += ['-i', str(key), '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes']
        else:
            credential = Path(args.password_file).read_text(encoding='utf-8-sig').rstrip('\r\n')
            # Existing local store format: login on line 1, password on line 2.
            lines = credential.splitlines()
            if len(lines) == 2 and lines[0].strip() == 'root':
                secret = lines[1]
            elif len(lines) == 1:
                secret = lines[0]
            else:
                raise RuntimeError('Expected password or root/password on two lines')
            if not secret:
                raise RuntimeError('Empty password file')
            env['SSHPASS'] = secret
            prefix = ['sshpass', '-e']
            options += ['-o', 'PubkeyAuthentication=no', '-o',
                        'PreferredAuthentications=password,keyboard-interactive']
        target = 'root@62.113.109.168'
        identity = run([*prefix, 'ssh', *options, target, 'id -u'], env=env)
        if identity.strip() != '0':
            raise RuntimeError('Root access required for this controller')
        run([*prefix, 'ssh', *options, target,
             'nginx -t && systemctl is-active nginx && date -u && '
             'getent ahostsv4 rhisseth.ru && df -h / && '
             'test -f /etc/nginx/sites-available/rhisseth'], env=env)
        if args.operation == 'update':
            run([*prefix, 'ssh', *options, target,
                 'mkdir -p /opt/rhisseth/staging/islands-map-v2 /opt/rhisseth/repository/scripts/automation'], env=env)
            for name in ('index.html', 'terrain-map-islands-preview-v2.png', 'placement-analysis.json'):
                run([*prefix, 'scp', *options, str(root / 'reports/previews/islands-v2' / name),
                     target + ':/opt/rhisseth/staging/islands-map-v2/' + name], env=env)
            run([*prefix, 'scp', *options, str(root / 'scripts/automation/Update-IslandsPreviewVps.py'),
                 target + ':/opt/rhisseth/repository/scripts/automation/Update-IslandsPreviewVps.py'], env=env)
            run([*prefix, 'ssh', *options, target,
                 'flock -n /opt/rhisseth/.local/islands-publication.lock /opt/rhisseth/venv/bin/python /opt/rhisseth/repository/scripts/automation/Update-IslandsPreviewVps.py'], env=env, timeout=300)
            run(['curl', '--fail', '--silent', '--show-error', '--max-time', '20',
                 '--output', '/dev/null', 'https://rhisseth.ru/map/'])
        code = 0
except Exception as error:
    emit(f'Failure: {type(error).__name__}: {error}')
finally:
    emit(f'Exit code: {code}; operation: {args.operation}; secrets logged: no')
    emit(f'Audit log: {log}')
raise SystemExit(code)
