#!/usr/bin/python3
"""Transfer reviewed v0.3 validation payload and execute it on the Rhisseth VDS."""
import datetime as dt
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from zoneinfo import ZoneInfo

RID='da44a388-e458-4379-ab4c-c204696804b2'
ROOT=Path.home()/'rhisseth.ru'
ARCHIVE=ROOT/'temp/batell-v03-migrations.tar.gz'
PAYLOAD=ROOT/'scripts/automation/Validate-RhissethV03Vps.py'
now=dt.datetime.now(dt.timezone.utc)
log_dir=ROOT/'reports/automation-logs'/now.strftime('%Y-%m-%d')
log_dir.mkdir(parents=True,exist_ok=True)
log=log_dir/(now.strftime('%Y%m%d-%H%M%S')+'-v03-sql-validation.md')
log.write_text(f'''# v0.3 SQL validation

- UTC: {now.isoformat()}
- Europe/Moscow: {now.astimezone(ZoneInfo('Europe/Moscow')).isoformat()}
- Task: batell-v0.3; operator/controller: Codex
- Runner: STU-AUTOMATION-01 / 10.210.52.128
- Target: Rhisseth VDS 62.113.109.168; read-only production backup and temporary test database
- Action: transfer reviewed SQL and validation script, then validate on a restored copy
- Passbolt resource: {RID}
- Reboot: none

''',encoding='utf-8')


def emit(value):
    with log.open('a',encoding='utf-8') as stream:
        stream.write(str(value)+'\n');stream.flush();os.fsync(stream.fileno())
    print(value,flush=True)


def main():
    if socket.gethostname().lower().split('.')[0]!='stu-automation-01':
        raise RuntimeError('Runner identity mismatch')
    if not ARCHIVE.is_file() or ARCHIVE.stat().st_size<1024 or not PAYLOAD.is_file():
        raise RuntimeError('Reviewed archive or validation script missing')
    phrase=Path('/etc/avalon-runner/passbolt/passphrase').read_text().rstrip('\r\n')
    env={**os.environ,'USERPASSWORD':phrase,'userPassword':phrase}
    result=subprocess.run(['passbolt','--config','/etc/avalon-runner/passbolt/passbolt-cli.yaml',
                           'get','resource','--id',RID,'--json'],env=env,
                          capture_output=True,text=True,timeout=45)
    if result.returncode:raise RuntimeError('Passbolt retrieval failed')
    resource=json.loads(result.stdout)
    if resource.get('username')!='root' or '62.113.109.168' not in resource.get('uri',''):
        raise RuntimeError('Passbolt endpoint mismatch')
    secret=resource['password'].rstrip('\r\n')
    sshenv={**os.environ,'SSHPASS':secret}
    opts=['-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12',
          '-o','PreferredAuthentications=password,keyboard-interactive',
          '-o','PubkeyAuthentication=no']
    def remote(args,timeout=300):
        outcome=subprocess.run(['sshpass','-e',*args],env=sshenv,
                               capture_output=True,text=True,timeout=timeout)
        for line in (outcome.stdout+outcome.stderr).replace(secret,'<redacted>').splitlines():
            emit(line)
        emit(f'Command exit_code={outcome.returncode}')
        if outcome.returncode:raise RuntimeError('Reviewed VDS validation step failed')
    emit(f'Preflight: runner verified; archive bytes={ARCHIVE.stat().st_size}; Passbolt endpoint verified')
    remote(['scp',*opts,str(ARCHIVE),'root@62.113.109.168:/opt/rhisseth/temp/batell-v03-migrations.tar.gz'])
    remote(['scp',*opts,str(PAYLOAD),'root@62.113.109.168:/opt/rhisseth/scripts/automation/Validate-RhissethV03Vps.py'])
    remote(['ssh',*opts,'root@62.113.109.168',
            '/opt/rhisseth/venv/bin/python /opt/rhisseth/scripts/automation/Validate-RhissethV03Vps.py'],timeout=600)
    emit('Validation: restored-copy migration succeeded; production database unchanged; reboot=false')


try:
    main();code=0
except Exception as error:
    emit(f'Failure: {type(error).__name__}: {error}');code=1
finally:
    emit(f'Final exit_code={code}; reboot=false; secrets_logged=false')
sys.exit(code)
