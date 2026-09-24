#!/usr/bin/env bash
set -euo pipefail
[[ ${EUID:-$(id -u)} -eq 0 ]] || { echo 'Run as root' >&2; exit 1; }
ip=${1:-}
python3 - "$ip" <<'PY'
import ipaddress, pathlib, sys
value=sys.argv[1]
try: ip=str(ipaddress.ip_address(value))
except ValueError: raise SystemExit('Invalid IP address')
path=pathlib.Path('/etc/rhisseth-blacklist')
items=set(path.read_text().split()) if path.exists() else set()
items.add(ip); path.write_text('\n'.join(sorted(items))+'\n'); path.chmod(0o600)
print(f'blacklist_saved={ip}')
PY
install -d -m 755 /etc/nginx/conf.d
python3 - <<'PY'
import ipaddress, pathlib
source=pathlib.Path('/etc/rhisseth-blacklist')
items=[]
for value in source.read_text().split() if source.exists() else []:
    try: items.append(str(ipaddress.ip_address(value)))
    except ValueError: pass
path=pathlib.Path('/etc/nginx/conf.d/rhisseth-blacklist.conf')
path.write_text(''.join(f'    deny {value};\n' for value in sorted(set(items))) or '    # empty\n')
path.chmod(0o644)
PY
nginx -t && systemctl reload nginx
fail2ban-client set rhisseth-auth banip "$ip"
echo "blacklist_applied=$ip"
