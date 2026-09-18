# Release review 2026-09-18 (0.0.2): Reviewed root bootstrap; preserve root access and existing services.
# Details: docs/releases/0.0.2-changes-2026-09-18.md.
"""Reviewed root bootstrap; preserve root access and existing services."""
import datetime as dt
import os
from pathlib import Path
import pwd
import shutil
import subprocess
from zoneinfo import ZoneInfo

os.umask(0o077)
now = dt.datetime.now(dt.timezone.utc)
logs = Path('/var/log/rhisseth/reports/automation-logs') / now.strftime('%Y-%m-%d')
logs.mkdir(parents=True, exist_ok=True)
log = logs / (now.strftime('%Y%m%d-%H%M%S') + '-storage-bootstrap.md')
log.write_text(f'# Storage bootstrap\n\nUTC: {now.isoformat()}\n\nMoscow: {now.astimezone(ZoneInfo("Europe/Moscow")).isoformat()}\n\nTask: backup-and-portable-deployment; controller: Codex\n\nRunner: STU-AUTOMATION-01 / 10.210.52.128\n\nTarget: 185.216.87.44 /srv/backups/rhisseth; account rhisseth-backup\n\nPassbolt: eebbe246-89db-4227-8618-89ff4fefcec5\n\nAction: setup archive directory and restricted SSH key; no reboot\n')
def audit(value):
    with log.open('a') as stream:
        stream.write(value + '\n')
        stream.flush()
        os.fsync(stream.fileno())
def run(args):
    p = subprocess.run(args, capture_output=True)
    audit(f'Command: {" ".join(args)}; exit_code={p.returncode}; output suppressed')
    if p.returncode:
        raise RuntimeError('Bootstrap command failed')
key = Path('/tmp/rhisseth-controller.pub').read_text().strip()
if not key.startswith('ssh-ed25519 ') or '\n' in key or '"' in key:
    raise SystemExit('Invalid public key')
if os.geteuid() != 0 or shutil.disk_usage('/srv').free < 512 * 1024**2:
    raise SystemExit('Storage preflight failed')
root = Path('/srv/backups/rhisseth')
user = 'rhisseth-backup'
try:
    account = pwd.getpwnam(user)
    if account.pw_dir != str(root):
        raise SystemExit('Existing account conflict')
except KeyError:
    account = None
if root.exists() and account is None:
    raise SystemExit('Existing backup directory requires review')
audit('Preflight: root, public key, disk and account/directory compatibility verified; root access preserved')
if account is None:
    run(['useradd', '--system', '--home-dir', str(root), '--shell', '/bin/sh', user])
    account = pwd.getpwnam(user)
root.mkdir(mode=0o700, parents=True, exist_ok=True)
# Parent created under restrictive umask must allow account traversal, not listing.
audit('Approved change: allow traversal of /srv/backups; archive directory remains owner-only')
root.parent.chmod(0o711)
root.chmod(0o700)
os.chown(root, account.pw_uid, account.pw_gid)
ssh = root / '.ssh'
ssh.mkdir(mode=0o700, exist_ok=True)
os.chown(ssh, account.pw_uid, account.pw_gid)
authorized = ssh / 'authorized_keys'
line = 'restrict,command="/usr/bin/python3 /usr/local/lib/rhisseth/rhisseth_storage.py" ' + key
existing = authorized.read_text().splitlines() if authorized.exists() else []
if line not in existing:
    audit('Approved change: add forced-command automation key; no root SSH changes')
    authorized.write_text('\n'.join(existing + [line]) + '\n')
authorized.chmod(0o600)
os.chown(authorized, account.pw_uid, account.pw_gid)
destination = Path('/usr/local/lib/rhisseth')
destination.mkdir(mode=0o755, parents=True, exist_ok=True)
destination.chmod(0o755)
shutil.copy2('/tmp/rhisseth_storage.py', destination / 'rhisseth_storage.py')
(destination / 'rhisseth_storage.py').chmod(0o644)
audit('Validation: exit_code=0; directory/account/key configured; existing services unchanged; reboot=false')
print('Storage configured: /srv/backups/rhisseth; restricted account rhisseth-backup; root access preserved')
