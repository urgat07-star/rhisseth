"""Move only the reviewed Rhisseth artifacts into the runner project folder."""
import datetime as dt
from pathlib import Path
import socket
from zoneinfo import ZoneInfo

now = dt.datetime.now(dt.timezone.utc)
root = Path('/home/avalon/rhisseth.ru')
directory = root / 'reports/automation-logs/2026-09-16'
directory.mkdir(parents=True, exist_ok=True)
log = directory / (now.strftime('%Y%m%d-%H%M%S') + '-consolidate-rhisseth-files.md')
log.write_text(f'# Consolidate Rhisseth artifacts\n\n- UTC: {now.isoformat()}\n- Europe/Moscow: {now.astimezone(ZoneInfo("Europe/Moscow")).isoformat()}\n- Controller: N7198 / Codex\n- Runner: STU-AUTOMATION-01 / 10.210.52.128\n- Target: runner Rhisseth files only\n- Action: move reports and reviewed scripts into project\n- VPS change/reboot: none\n\n', encoding='utf-8')

def emit(text):
    with log.open('a', encoding='utf-8') as stream:
        stream.write(text + '\n')
    print(text, flush=True)

if socket.gethostname().lower().split('.')[0] != 'stu-automation-01':
    emit('Preflight failed: hostname mismatch; exit_code=1')
    raise SystemExit(1)
emit('Preflight: runner identity verified; project audit log writable')
sources = list(Path('/home/avalon/reports/automation-logs/2026-09-16').glob('*rhisseth*'))
sources += list(Path('/tmp').glob('*Inspect-RhissethVpsFromRunner.py'))
for source in sources:
    if not source.is_file() or source.is_symlink():
        raise RuntimeError('Unexpected source type')
    target = (directory if source.parent != Path('/tmp') else root / 'scripts/automation/archive') / source.name
    if not target.resolve().is_relative_to(root.resolve()) or target.exists():
        raise RuntimeError('Invalid or existing destination')
    target.parent.mkdir(parents=True, exist_ok=True)
    emit(f'Approved move: {source} -> {target}')
    source.rename(target)
    emit('Validation: moved file present=' + str(target.is_file()))
emit('Validation: exit_code=0; runner files moved; VPS change=false; reboot=false')
