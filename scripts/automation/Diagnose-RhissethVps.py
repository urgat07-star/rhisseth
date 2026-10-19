"""Read-only Rhisseth service and annual-economy diagnosis through the runner."""
import datetime as dt
import subprocess
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path('/opt/rhisseth')
now = dt.datetime.now(dt.timezone.utc)
logdir = ROOT / 'reports/automation-logs' / now.strftime('%Y-%m-%d')
logdir.mkdir(parents=True, exist_ok=True)
log = logdir / (now.strftime('%Y%m%d-%H%M%S') + '-diagnose-service.md')
def run(args):
    result = subprocess.run(args, capture_output=True, text=True)
    output = 'COMMAND ' + ' '.join(args) + '\n' + result.stdout + result.stderr + '\nEXIT ' + str(result.returncode) + '\n'
    print(output, flush=True)
    with log.open('a', encoding='utf-8') as stream: stream.write(output)
def main():
    log.write_text(f'# Rhisseth service diagnosis\n\n- UTC: {now.isoformat()}\n- Europe/Moscow: {now.astimezone(ZoneInfo("Europe/Moscow")).isoformat()}\n- Controller: Codex through STU-AUTOMATION-01 / 10.210.52.128\n- Target: Rhisseth VDS 62.113.109.168\n- Action: read-only service, schema and annual-economy diagnosis\n- Change/reboot: none\n\n', encoding='utf-8')
    checks = [
        ['systemctl', 'status', 'rhisseth', '--no-pager'],
        ['journalctl', '-u', 'rhisseth', '-n', '80', '--no-pager'],
        ['ss', '-lntp'],
        ['curl', '--max-time', '10', '-sS', '-i', 'http://127.0.0.1:8080/health'],
        ['runuser', '-u', 'rhisseth', '--', 'test', '-r', '/opt/rhisseth/repository/app/backend/main.py'],
        ['runuser', '-u', 'rhisseth', '--', '/opt/rhisseth/venv/bin/python', '-c', 'import fastapi,psycopg; print("runtime imports ok")'],
        ['runuser', '-u', 'postgres', '--', 'psql', '-X', '-At', '-d', 'rhisseth', '-c', "SELECT 'clock|'||turn_number||'|'||(turn_number/4)||'|'||(turn_number%4) FROM game_clock WHERE id=true;"],
        ['runuser', '-u', 'postgres', '--', 'psql', '-X', '-At', '-d', 'rhisseth', '-c', "SELECT 'tables|'||coalesce(to_regclass('hex_economy_history')::text,'missing')||'|'||coalesce(to_regclass('hex_population_events')::text,'missing')||'|'||coalesce(to_regclass('hex_economy_state')::text,'missing');"],
        ['runuser', '-u', 'postgres', '--', 'psql', '-X', '-At', '-d', 'rhisseth', '-c', "SELECT 'processed|'||coalesce(string_agg(year::text,',' ORDER BY year),'none') FROM game_economy_years;"],
        ['runuser', '-u', 'postgres', '--', 'psql', '-X', '-At', '-d', 'rhisseth', '-c', "SELECT 'history|'||count(*)||'|'||coalesce(max(year)::text,'none') FROM hex_economy_history;"],
        ['sha256sum', '/opt/rhisseth/repository/app/backend/game_clock.py', '/opt/rhisseth/repository/app/frontend/cabinet.js'],
        ['test', '-f', '/opt/rhisseth/repository/data/migrations/046_population_tax_history.sql'],
    ]
    for check in checks: run(check)
main()
