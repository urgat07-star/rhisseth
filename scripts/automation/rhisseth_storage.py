#!/usr/bin/python3
"""Forced SSH command for unencrypted archives. No shell or arbitrary paths."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import fcntl
from zoneinfo import ZoneInfo

ROOT = Path('/srv/backups/rhisseth')
NAME = re.compile(r'rhisseth-\d{8}T\d{6}Z-[a-f0-9]{8}\.tar\.gz')
os.umask(0o077)
def main():
    now = dt.datetime.now(dt.timezone.utc)
    logs = ROOT / 'reports/automation-logs' / now.strftime('%Y-%m-%d')
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / (now.strftime('%Y%m%d-%H%M%S-%f') + '-storage.md')
    log.write_text(f'# Archive storage operation\n\nUTC: {now.isoformat()}\n\nMoscow: {now.astimezone(ZoneInfo("Europe/Moscow")).isoformat()}\n\nTask: backup-and-portable-deployment; controller: SSH automation\n\nRunner: STU-AUTOMATION-01 / 10.210.52.128 (current controller)\n\nTarget: 185.216.87.44 /srv/backups/rhisseth\n\nPassbolt: eebbe246-89db-4227-8618-89ff4fefcec5 (bootstrap only)\n', encoding='utf-8')
    def audit(value):
        with log.open('a') as stream:
            stream.write(value + '\n')
            stream.flush()
            os.fsync(stream.fileno())
    parts = os.environ.get('SSH_ORIGINAL_COMMAND', '').split()
    code = 1
    changed = False
    try:
        if not parts or parts[0] not in ('list', 'get', 'put'):
            raise ValueError('Invalid operation')
        operation = parts[0]
        audit(f'Action: {operation}; preflight: audit writable; protocol and paths validated')
        lock = (ROOT / '.lock').open('a')
        fcntl.flock(lock, fcntl.LOCK_EX)
        def entries():
            result = []
            for manifest in sorted(ROOT.glob('rhisseth-*.tar.gz.json')):
                name = manifest.name[:-5]
                if NAME.fullmatch(name) and (ROOT / name).is_file():
                    row = json.loads(manifest.read_text())
                    if row['name'] == name and row['size'] == (ROOT / name).stat().st_size:
                        result.append(row)
            return result
        if operation == 'list' and len(parts) == 1:
            sys.stdout.write(json.dumps(entries()) + '\n')
        elif operation == 'get' and len(parts) == 2 and NAME.fullmatch(parts[1]):
            if not any(row['name'] == parts[1] for row in entries()):
                raise ValueError('Archive not complete')
            with (ROOT / parts[1]).open('rb') as source:
                while chunk := source.read(1024 * 1024):
                    sys.stdout.buffer.write(chunk)
        elif operation == 'put' and len(parts) == 4 and NAME.fullmatch(parts[1]) and re.fullmatch('[a-f0-9]{64}', parts[3]):
            name, size, expected = parts[1], int(parts[2]), parts[3]
            if size <= 0 or size > 8 * 1024**3:
                raise ValueError('Archive size out of range')
            import shutil
            if shutil.disk_usage(ROOT).free < size + 256 * 1024**2:
                raise ValueError('Insufficient storage space')
            target = ROOT / name
            if target.exists() or target.with_suffix(target.suffix + '.json').exists():
                raise ValueError('Archive already exists')
            temporary = ROOT / ('.' + name + '.partial')
            digest, received = hashlib.sha256(), 0
            audit(f'Approved change: receive {name}; expected_size={size}; retention=7 days')
            try:
                with temporary.open('xb') as output:
                    while chunk := sys.stdin.buffer.read(min(1024 * 1024, size - received + 1)):
                        received += len(chunk)
                        if received > size:
                            raise ValueError('Unexpected archive length')
                        digest.update(chunk)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if received != size or digest.hexdigest() != expected:
                    raise ValueError('Archive checksum or length mismatch')
                audit('Validation: incoming SHA256 and length match; publish archive')
                temporary.rename(target)
                changed = True
                row = {'name': name, 'size': size, 'sha256': expected, 'completed_utc': now.isoformat()}
                meta = ROOT / ('.' + name + '.json.partial')
                meta.write_text(json.dumps(row) + '\n')
                meta.rename(ROOT / (name + '.json'))
                cutoff = now - dt.timedelta(days=7)
                for old in entries():
                    if old['name'] != name and dt.datetime.fromisoformat(old['completed_utc']) < cutoff:
                        audit('Approved retention deletion: ' + old['name'])
                        (ROOT / (old['name'] + '.json')).unlink()
                        (ROOT / old['name']).unlink()
                sys.stdout.write(json.dumps(row) + '\n')
            finally:
                temporary.unlink(missing_ok=True)
        else:
            raise ValueError('Invalid protocol arguments')
        code = 0
    except Exception as error:
        # Do not expose environment, input or arbitrary exception text.
        audit('Failure: ' + type(error).__name__)
        sys.stderr.write('Storage operation failed; inspect sanitized storage audit log\n')
    finally:
        audit(f'Validation: exit_code={code}; changed={changed}; reboot=false')
    return code
if __name__ == '__main__':
    raise SystemExit(main())
