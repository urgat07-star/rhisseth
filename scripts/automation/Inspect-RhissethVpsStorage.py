#!/usr/bin/python3
"""Read-only storage audit for Rhisseth VDS; emits sizes, never mutates."""
import datetime as dt, json, os, re, socket, subprocess
from pathlib import Path
from zoneinfo import ZoneInfo

now = dt.datetime.now(dt.timezone.utc)
logdir = Path.home() / 'rhisseth.ru/reports/automation-logs' / now.strftime('%Y-%m-%d')
logdir.mkdir(parents=True, exist_ok=True)
log = logdir / (now.strftime('%Y%m%d-%H%M%S') + '-rhisseth-storage-audit.md')
log.write_text(f'# Rhisseth VDS storage audit\n\nUTC: {now.isoformat()}\nMoscow: {now.astimezone(ZoneInfo("Europe/Moscow")).isoformat()}\nController: Codex\nRunner: STU-AUTOMATION-01 / 10.210.52.128\nTarget: 62.113.109.168; read-only storage inventory\nChange/reboot: none / none\n\n', encoding='utf-8')

def audit(value):
    with log.open('a', encoding='utf-8') as f:
        f.write(value + '\n'); f.flush(); os.fsync(f.fileno())

def main():
    if socket.gethostname().lower().split('.')[0] != 'stu-automation-01':
        raise SystemExit('Must execute on runner')
    # The controller supplies the credential and target command exactly as in the existing inspector.
    phrase = Path('/etc/avalon-runner/passbolt/passphrase').read_text().rstrip('\r\n')
    env = {**os.environ, 'USERPASSWORD': phrase, 'userPassword': phrase}
    c = subprocess.run(['passbolt','--config','/etc/avalon-runner/passbolt/passbolt-cli.yaml','get','resource','--id','da44a388-e458-4379-ab4c-c204696804b2','--json'], env=env, capture_output=True, text=True, timeout=60)
    if c.returncode: raise SystemExit('Source credential unavailable')
    row = json.loads(c.stdout); password = row.get('password','').rstrip('\r\n')
    env = {**os.environ, 'SSHPASS': password}
    base = ['sshpass','-e','ssh','-o','StrictHostKeyChecking=yes','-o','PubkeyAuthentication=no','-o','ConnectTimeout=12',f"{row['username']}@62.113.109.168"]
    remote = r'''set -eu
printf '{"df":'; df -B1 / | tail -1 | awk '{printf "{\"size\":%s,\"used\":%s,\"avail\":%s,\"pct\":\"%s\"}", $2,$3,$4,$5}'; printf ',"du":['
first=1
for p in /opt/rhisseth /var /var/log /var/lib/postgresql /var/cache/apt /tmp /root; do
  [ -e "$p" ] || continue
  n=$(du -x -s -B1 "$p" 2>/dev/null | awk '{print $1}')
  [ "$first" -eq 1 ] || printf ','; first=0
  printf '{"path":"%s","bytes":%s}' "$p" "${n:-0}"
done
printf '],"children":['
du -x -B1 -d 2 /opt/rhisseth /var 2>/dev/null | sort -nr | head -40 | awk 'BEGIN{first=1}{gsub(/"/,"",$2); if(first==0)printf ",";first=0; printf "{\"bytes\":%s,\"path\":\"%s\"}",$1,$2}'
printf '],"journal":'; journalctl --disk-usage 2>/dev/null | sed 's/\\/\\\\/g;s/"/\\"/g' | awk '{printf "\"%s\"",$0}'
printf ',"backups":['
find /opt/rhisseth/backups -maxdepth 1 -type f -printf '{"name":"%f","bytes":%s,"mtime":"%TY-%Tm-%TdT%TH:%TM:%TSZ"},' 2>/dev/null | sed 's/,$//'
printf '],"vds_archives":['
find /var/backups/rhisseth -maxdepth 2 -type f -printf '{"name":"%f","relative":"%P","bytes":%s,"mtime":"%TY-%Tm-%TdT%TH:%TM:%TSZ"},' 2>/dev/null | sed 's/,$//'
printf '],"rollback_repositories":['
find /opt/rhisseth -maxdepth 1 -type d -name 'repository.before-deploy-*' -printf '{"name":"%f","bytes":"'"'"'$(du -s -B1 {} 2>/dev/null | awk '"'"'{print $1}'"'"')'"'"'"},' 2>/dev/null | sed 's/,$//'
printf ']}\n'
'''
    r = subprocess.run([*base, remote], env=env, capture_output=True, text=True, timeout=120)
    audit(f'VDS storage audit: exit_code={r.returncode}; output sanitized; no change or reboot')
    if r.returncode: raise SystemExit('VDS storage audit failed')
    print(r.stdout)
    print(f'Audit log: {log}')

if __name__ == '__main__': main()
