#!/usr/bin/python3
"""Read only the sanitized barony count from archived Rhisseth backup manifests."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tarfile
import tempfile
from zoneinfo import ZoneInfo

os.umask(0o077)
root=Path('/home/avalon/rhisseth.ru')
now=dt.datetime.now(dt.timezone.utc)
directory=root/'reports/automation-logs'/now.strftime('%Y-%m-%d')
directory.mkdir(parents=True,exist_ok=True)
log=directory/(now.strftime('%Y%m%d-%H%M%S')+'-start-zone-backup-review.md')
log.write_text(f'''# Rhisseth start-zone backup review

UTC: {now.isoformat()}
Moscow: {now.astimezone(ZoneInfo('Europe/Moscow')).isoformat()}
Task: batell-v0.3-start-zones; operator/controller: Codex
Runner: STU-AUTOMATION-01 / 10.210.52.128
Approved target: restricted Rhisseth backup storage 185.216.87.44; read-only list/get
Related Passbolt resource ID: eebbe246-89db-4227-8618-89ff4fefcec5
Preflight: log writable; runner host and pinned storage key checked below
Change/reboot: none / none
''',encoding='utf-8')


def audit(message):
    with log.open('a',encoding='utf-8') as stream:
        stream.write(message+'\n')
        stream.flush()
        os.fsync(stream.fileno())


def storage(operation, output=None):
    key=root/'.local/recovery/storage-key'
    if not key.is_file() or key.stat().st_mode & 0o077:
        raise RuntimeError('Pinned storage identity missing or has unsafe permissions')
    command=['ssh','-o','StrictHostKeyChecking=yes','-o','BatchMode=yes','-o','IdentitiesOnly=yes',
             '-i',str(key),'rhisseth-backup@185.216.87.44',operation]
    result=subprocess.run(command,stdout=output or subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
    audit(f'Storage action={operation.split()[0]}; exit_code={result.returncode}; raw errors suppressed')
    if result.returncode:
        raise RuntimeError('Restricted storage action failed')
    return result.stdout


try:
    if socket.gethostname().lower().split('.')[0]!='stu-automation-01':
        raise RuntimeError('Must execute on STU-AUTOMATION-01')
    audit('Preflight passed: runner host, restricted key and audit file')
    entries=json.loads(storage('list'))
    results=[]
    with tempfile.TemporaryDirectory(prefix='start-zone-',dir=root/'.local') as temporary:
        for entry in entries:
            name=entry['name']
            if not re.fullmatch(r'rhisseth-\d{8}T\d{6}Z-[a-f0-9]{8}\.tar\.gz',name):
                raise RuntimeError('Invalid backup name')
            archive=Path(temporary)/name
            with archive.open('wb') as stream:
                storage('get '+name,stream)
            if archive.stat().st_size!=entry['size'] or hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()!=entry['sha256']:
                raise RuntimeError('Backup size or digest mismatch')
            with tarfile.open(archive,'r:gz') as source:
                manifest=json.load(source.extractfile('manifest.json'))
            signature=manifest.get('table_signatures',{}).get('player_baronies','0|')
            count=int(signature.split('|',1)[0])
            result={'name':name,'completed_utc':entry['completed_utc'],'player_baronies':count}
            results.append(result)
            audit(f'Validated {name}: player_baronies={count}; archive removed after inspection')
            archive.unlink()
    print(json.dumps(results,ensure_ascii=False))
    audit('Validation: all available manifests inspected; exit_code=0; no change or reboot')
except Exception as error:
    audit(f'Failure: {type(error).__name__}; exit_code=1; no change or reboot')
    raise SystemExit('Start-zone backup review failed; see sanitized runner log')
