#!/usr/bin/env bash
set -euo pipefail
[[ ${EUID:-$(id -u)} -eq 0 ]] || { echo 'Run as root' >&2; exit 1; }
ip=${1:-}
python3 - "$ip" <<'PY'
import ipaddress, pathlib, sys
value=sys.argv[1]
try: ip=str(ipaddress.ip_address(value))
except ValueError: raise SystemExit('Invalid IP address')
path=pathlib.Path('/etc/fail2ban/jail.d/rhisseth-manual.local')
path.parent.mkdir(parents=True,exist_ok=True)
existing=path.read_text() if path.exists() else '[DEFAULT]\nignoreip = 127.0.0.1/8 ::1\n'
lines=existing.splitlines()
for i,line in enumerate(lines):
    if line.lower().startswith('ignoreip'):
        values=line.split('=',1)[1].split() if '=' in line else []
        if ip not in values: values.append(ip)
        lines[i]='ignoreip = '+' '.join(values); break
else: lines.append('ignoreip = '+ip)
path.write_text('\n'.join(lines)+'\n'); path.chmod(0o640)
print(f'whitelist_saved={ip}')
PY
systemctl reload fail2ban 2>/dev/null || systemctl restart fail2ban
fail2ban-client status rhisseth-auth
