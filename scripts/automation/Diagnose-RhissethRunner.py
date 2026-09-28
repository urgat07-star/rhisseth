"""Read-only Rhisseth 502 diagnosis through Passbolt and the pinned runner."""
import json, os, subprocess, sys
from pathlib import Path
RID = 'da44a388-e458-4379-ab4c-c204696804b2'
if len(sys.argv) != 3 or sys.argv[1] != RID: raise SystemExit('Invalid operation')
phrase = Path('/etc/avalon-runner/passbolt/passphrase').read_text().rstrip('\r\n')
env = {**os.environ, 'USERPASSWORD': phrase, 'userPassword': phrase}
result = subprocess.run(['passbolt','--config','/etc/avalon-runner/passbolt/passbolt-cli.yaml','get','resource','--id',RID,'--json'], env=env, capture_output=True, text=True, timeout=45)
if result.returncode: raise SystemExit('Passbolt retrieval failed')
resource = json.loads(result.stdout)
if resource.get('username') != 'root' or '62.113.109.168' not in resource.get('uri',''): raise SystemExit('Passbolt endpoint mismatch')
sshenv = {**os.environ, 'SSHPASS': resource['password'].rstrip('\r\n')}
options = ['-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','PreferredAuthentications=password,keyboard-interactive','-o','PubkeyAuthentication=no']
remote = '''set -o pipefail
echo CHECK systemd
systemctl status rhisseth --no-pager || true
echo CHECK journal
journalctl -u rhisseth -n 80 --no-pager || true
echo CHECK sockets
ss -lntp || true
echo CHECK localhost
curl --max-time 10 -sS -i http://127.0.0.1:8080/health || true
echo CHECK external
curl --insecure --max-time 15 -sS -o /dev/null -w 'HTTPS %{http_code}\n' https://62.113.109.168/ || true
echo CHECK permissions
runuser -u rhisseth -- test -r /opt/rhisseth/repository/app/backend/main.py; echo permission_exit=$?
echo CHECK imports
runuser -u rhisseth -- /opt/rhisseth/venv/bin/python -c 'import fastapi,psycopg; print("runtime imports ok")'; echo imports_exit=$?
'''
result = subprocess.run(['sshpass','-e','ssh',*options,'root@62.113.109.168','bash','-s'], env=sshenv, input=remote, capture_output=True, text=True, timeout=180)
print((result.stdout + '\n' + result.stderr).replace(resource['password'],'<redacted>'), flush=True)
sys.exit(result.returncode)
