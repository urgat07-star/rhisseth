"""Build a confidential handoff archive on the mandatory runner; no secret output."""
import datetime as dt
import hashlib
import os
from pathlib import Path
import socket
import subprocess
from zipfile import ZipFile, ZIP_DEFLATED
from zoneinfo import ZoneInfo

os.umask(0o077)
root=Path('/home/avalon/rhisseth.ru')
now=dt.datetime.now(dt.timezone.utc)
logs=root/'reports/automation-logs'/now.strftime('%Y-%m-%d')
logs.mkdir(parents=True,exist_ok=True)
log=logs/(now.strftime('%Y%m%d-%H%M%S')+'-handoff-package.md')
log.write_text(f'# Confidential recovery handoff\n\nUTC: {now.isoformat()}\nMoscow: {now.astimezone(ZoneInfo("Europe/Moscow")).isoformat()}\nTask: backup-and-portable-deployment; controller: Codex\nRunner: STU-AUTOMATION-01 / 10.210.52.128\nTarget: runner-local files only; no target connections\nAction: package scripts and existing automation key; reboot=false\nPassbolt: no resource retrieval\n')

def audit(message):
    with log.open('a') as stream:
        stream.write(message+'\n')
        stream.flush()
        os.fsync(stream.fileno())
    print(message,flush=True)

code=1
output=root/'.local/handoff/rhisseth-recovery-handoff-2026-09-17.zip'
try:
    if socket.gethostname().lower().split('.')[0]!='stu-automation-01':
        raise RuntimeError('Runner required')
    kit=root/'.local/handoff/recovery-kit-input.zip'
    key=root/'.local/recovery/storage-key'
    if not kit.is_file() or not key.is_file():
        raise RuntimeError('Required input missing')
    if key.stat().st_mode & 0o077:
        raise RuntimeError('Automation key permissions too broad')
    hosts=[]
    for host in ('185.216.87.44','10.210.52.56'):
        result=subprocess.run(['ssh-keygen','-F',host],capture_output=True,text=True)
        if result.returncode:
            raise RuntimeError('Pinned host key missing')
        hosts.extend(row for row in result.stdout.splitlines() if row and not row.startswith('#'))
    audit('Preflight: runner identity, writable audit, input ZIP, owner-only existing key and pinned host entries verified')
    with ZipFile(kit) as source:
        if source.testzip() is not None:
            raise RuntimeError('Input ZIP corrupted')
        with ZipFile(output,'w',ZIP_DEFLATED) as destination:
            for entry in source.infolist():
                if entry.filename in ('deploy/recovery/storage-key.local','deploy/recovery/known_hosts.local','deploy/recovery/recovery.local.json','START-WINDOWS.md'):
                    continue
                destination.writestr(entry.filename,source.read(entry))
            destination.write(key,'deploy/recovery/storage-key.local')
            destination.writestr('deploy/recovery/known_hosts.local','\n'.join(hosts)+'\n')
            destination.writestr('deploy/recovery/recovery.local.json',source.read('deploy/recovery/recovery.example.json'))
            start=source.read('START-WINDOWS.md').decode('utf-8-sig')
            start=start.replace('rhisseth-docker-recovery-kit-2026-09-17.zip',output.name)
            note='''# Один архив: начните здесь

В комплект уже включены storage-key.local, known_hosts.local и recovery.local.json.
Отдельно искать и копировать эти файлы не нужно. После распаковки выполните
шаги установки Docker, заполните IP/логин/пароль в готовом recovery.local.json
и запустите проверки и восстановление. Команду Copy-Item для создания конфига
пропустите: конфиг уже создан.

SSH ключи известны для хранилища 185.216.87.44 и прежней цели 10.210.52.56.
Для другой ВМ администратор перед передачей комплекта должен добавить ее
проверенный host key в known_hosts.local. Docker режим по действующей политике
работает только с публичными IP.

АРХИВ СОДЕРЖИТ СЕКРЕТНЫЙ КЛЮЧ. Передавать только по защищенному каналу,
не публиковать в GitHub. Ключ существующей автоматизации разрешает не только
чтение, но и запись бэкапов; выдавайте комплект только доверенному оператору.

'''
            destination.writestr('НАЧНИТЕ-ЗДЕСЬ.md',note)
            destination.writestr('START-WINDOWS.md',note+'\n'+start)
    output.chmod(0o600)
    with ZipFile(output) as packed:
        if packed.testzip() is not None:
            raise RuntimeError('Handoff ZIP corrupted')
        if packed.read('deploy/recovery/storage-key.local')!=key.read_bytes():
            raise RuntimeError('Packaged key mismatch')
    digest=hashlib.file_digest(output.open('rb'),'sha256').hexdigest()
    audit('Validation: ZIP integrity and packaged files verified; exit_code=0; no infrastructure changes or reboot')
    audit('Confidential archive ready on runner: '+str(output))
    audit('SHA256: '+digest)
    code=0
except Exception as error:
    output.unlink(missing_ok=True)
    import traceback
    location=traceback.extract_tb(error.__traceback__)[-1]
    audit('Failure: '+type(error).__name__+'; line='+str(location.lineno)+'; details suppressed; packaging stopped; exit_code=1; no infrastructure changes/reboot')
finally:
    audit('Audit log: '+str(log))
raise SystemExit(code)
