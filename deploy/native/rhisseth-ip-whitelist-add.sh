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
blacklist=pathlib.Path('/etc/rhisseth-blacklist')
if blacklist.exists():
    remaining=[item for item in blacklist.read_text().split() if item != ip]
    blacklist.write_text(('\n'.join(sorted(set(remaining)))+'\n') if remaining else '')
    blacklist.chmod(0o600)
print(f'whitelist_saved={ip}')
PY
install -d -m 755 /etc/nginx/conf.d
python3 - "$ip" <<'PY'
import ipaddress, pathlib, sys
ip=str(ipaddress.ip_address(sys.argv[1]))
path=pathlib.Path('/etc/nginx/conf.d/rhisseth-whitelist.conf')
items=[]
if path.exists():
    for line in path.read_text().splitlines():
        value=line.strip().split()[0] if line.strip() and not line.strip().startswith(('geo','default','}')) else ''
        try: ipaddress.ip_address(value); items.append(value)
        except ValueError: pass
if ip not in items: items.append(ip)
path.write_text('geo $rhisseth_whitelisted {\n    default 0;\n' + ''.join(f'    {value} 1;\n' for value in sorted(set(items), key=lambda x: (ipaddress.ip_address(x).version, int(ipaddress.ip_address(x)))) ) + '}\n')
path.chmod(0o644)
PY
fail2ban-client set rhisseth-auth unbanip "$ip" >/dev/null 2>&1 || true
systemctl reload fail2ban 2>/dev/null || systemctl restart fail2ban
nginx -t && systemctl reload nginx
fail2ban-client status rhisseth-auth
