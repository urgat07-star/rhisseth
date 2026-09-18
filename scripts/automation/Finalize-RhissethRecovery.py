# Release review 2026-09-18 (0.0.2): Repair traversal permissions for a verified recovered instance only.
# Details: docs/releases/0.0.2-changes-2026-09-18.md.
"""Repair traversal permissions for a verified recovered instance only."""
import datetime as dt
import json
import os
from pathlib import Path
import socket
import subprocess
from zoneinfo import ZoneInfo
os.umask(0o077)
root = Path('/opt/rhisseth')
now = dt.datetime.now(dt.timezone.utc)
logs = Path('/var/log/rhisseth/reports/automation-logs')/now.strftime('%Y-%m-%d')
logs.mkdir(parents=True,exist_ok=True)
log = logs/(now.strftime('%Y%m%d-%H%M%S')+'-finalize.md')
log.write_text(f'# Finalize recovered Rhisseth\n\nUTC: {now.isoformat()}\n\nMoscow: {now.astimezone(ZoneInfo("Europe/Moscow")).isoformat()}\n\nTask: backup-and-portable-deployment; controller: Codex\n\nRunner: STU-AUTOMATION-01 / 10.210.52.128\n\nTarget: {socket.gethostname()} / 10.210.52.56, managed /opt/rhisseth\n\nPassbolt: 34b8e391-f4e8-4dbc-9304-6fcc22e942ab\n\nAction: correct public directory traversal; reboot=false\n')
def audit(message):
    with log.open('a') as stream:
        stream.write(message+'\n')
        stream.flush()
        os.fsync(stream.fileno())
    print(message,flush=True)
code=1
try:
    metadata=json.loads((root/'recovery.json').read_text())
    actual=subprocess.check_output(['git','-C',str(root/'repository'),'rev-parse','HEAD'],text=True).strip()
    if actual!=metadata['release']['sha']:
        raise RuntimeError('Recovered SHA mismatch')
    audit('Preflight: managed recovery metadata and deployed SHA match; audit writable')
    for path,mode in ((root,0o755),(root/'reports',0o755),(root/'secrets',0o711),(root/'scripts',0o755),(Path('/etc/rhisseth'),0o755)):
        audit(f'Approved chmod {path}: {oct(path.stat().st_mode & 0o777)} -> {oct(mode)}')
        path.chmod(mode)
    p=subprocess.run(['systemctl','restart','rhisseth'],capture_output=True)
    audit('Restart application exit_code='+str(p.returncode))
    if p.returncode:
        raise RuntimeError('Restart failed')
    code=0
except Exception as error:
    audit('Failure: '+type(error).__name__+'; sensitive details suppressed')
finally:
    audit(f'Validation: exit_code={code}; permission change/application restart only; reboot=false')
raise SystemExit(code)
