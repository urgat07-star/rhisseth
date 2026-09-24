"""Read-only Rhisseth 502 diagnosis executed through the Passbolt runner."""
import datetime as dt
import subprocess
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path('/opt/rhisseth')
now = dt.datetime.now(dt.timezone.utc)
logdir = ROOT / 'reports/automation-logs' / now.strftime('%Y-%m-%d')
logdir.mkdir(parents=True, exist_ok=True)
log = logdir / (now.strftime('%Y%m%d-%H%M%S') + '-diagnose-502.md')
def run(args):
    result = subprocess.run(args, capture_output=True, text=True)
    output = 'COMMAND ' + ' '.join(args) + '\n' + result.stdout + result.stderr + '\nEXIT ' + str(result.returncode) + '\n'
    print(output, flush=True)
    with log.open('a', encoding='utf-8') as stream: stream.write(output)
def main():
    log.write_text(f'# Rhisseth 502 diagnosis\n\n- UTC: {now.isoformat()}\n- Europe/Moscow: {now.astimezone(ZoneInfo("Europe/Moscow")).isoformat()}\n- Target: 62.113.109.168\n- Action: read-only diagnosis\n\n', encoding='utf-8')
    checks = [
        ['systemctl', 'status', 'rhisseth', '--no-pager'],
        ['journalctl', '-u', 'rhisseth', '-n', '80', '--no-pager'],
        ['ss', '-lntp'],
        ['curl', '--max-time', '10', '-sS', '-i', 'http://127.0.0.1:8080/health'],
        ['runuser', '-u', 'rhisseth', '--', 'test', '-r', '/opt/rhisseth/repository/app/backend/main.py'],
        ['runuser', '-u', 'rhisseth', '--', '/opt/rhisseth/venv/bin/python', '-c', 'import fastapi,psycopg; print("runtime imports ok")'],
    ]
    for check in checks: run(check)
main()
