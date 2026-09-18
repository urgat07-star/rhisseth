"""Read sanitized deployment logs and process names only."""
import datetime as dt
from pathlib import Path
import subprocess
logs=Path('/var/log/rhisseth/reports/automation-logs')/dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d')
paths=sorted(logs.glob('*restore.md'))
if paths:
    print('Target progress log: '+str(paths[-1]))
    print('\n'.join(paths[-1].read_text().splitlines()[-12:]))
p=subprocess.run(['ps','-eo','comm='],capture_output=True,text=True)
names=p.stdout.splitlines()
print('Relevant process counts: '+str({name:names.count(name) for name in ('apt-get','dpkg','pg_restore','python3','pip','postgres','nginx')}))
