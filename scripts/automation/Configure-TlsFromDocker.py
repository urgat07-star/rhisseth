"""Local Docker controller for the selected Rhisseth VDS. No secrets in argv."""
import argparse
import datetime as dt
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('operation', choices=['inspect', 'status', 'install'])
parser.add_argument('--known-hosts', required=True)
auth = parser.add_mutually_exclusive_group(required=True)
auth.add_argument('--ssh-key')
auth.add_argument('--password-file')
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
now = dt.datetime.now(dt.timezone.utc)
directory = root / 'reports/automation-logs' / now.strftime('%Y-%m-%d')
directory.mkdir(parents=True, exist_ok=True)
log = directory / (now.strftime('%Y%m%d-%H%M%S') + '-tls-local-docker.md')
log.write_text(f'# Rhisseth TLS through local Docker\n\nUTC: {now.isoformat()}\n'
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
        if args.operation == 'status':
            run([*prefix, 'ssh', *options, target,
                 "ps -eo pid,comm,etimes | grep -E 'apt|dpkg|certbot|install-letsen' || true; "
                 "systemctl list-timers rhisseth-certbot.timer --no-pager; "
                 "grep -iE 'sleep|delay|Simulating|renewal.*failed|renewal.*succeed' /opt/rhisseth/reports/certbot/letsencrypt.log | tail -n 3 || true"], env=env)
        if args.operation == 'install':
            run([*prefix, 'ssh', *options, target,
                 'mkdir -p /opt/rhisseth/repository/deploy/native'], env=env)
            for name in ('install-letsencrypt.sh', 'rhisseth-certbot.service',
                         'rhisseth-certbot.timer'):
                run([*prefix, 'scp', *options, str(root / 'deploy/native' / name),
                     target + ':/opt/rhisseth/repository/deploy/native/' + name], env=env)
            run([*prefix, 'ssh', *options, target,
                 'bash /opt/rhisseth/repository/deploy/native/install-letsencrypt.sh '
                 'urgat07@gmail.com'], env=env, timeout=1800)
            run(['curl', '--fail', '--silent', '--show-error', '--max-time', '20',
                 '--output', '/dev/null', 'https://rhisseth.ru/index.php'])
        code = 0
except Exception as error:
    emit(f'Failure: {type(error).__name__}: {error}')
finally:
    emit(f'Exit code: {code}; operation: {args.operation}; secrets logged: no')
    emit(f'Audit log: {log}')
raise SystemExit(code)
