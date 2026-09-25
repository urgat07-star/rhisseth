#!/usr/bin/env bash
set -euo pipefail

[[ ${EUID:-$(id -u)} -eq 0 ]] || { echo 'Run as root' >&2; exit 1; }

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
WHITELIST_CONF=/etc/nginx/conf.d/rhisseth-whitelist.conf
BLACKLIST_FILE=/etc/rhisseth-blacklist
BLACKLIST_CONF=/etc/nginx/conf.d/rhisseth-blacklist.conf
MANUAL_JAIL=/etc/fail2ban/jail.d/rhisseth-manual.local

validate_ip() {
    python3 - "$1" <<'PY'
import ipaddress, sys
try:
    print(ipaddress.ip_address(sys.argv[1]))
except ValueError:
    raise SystemExit('Invalid IP address')
PY
}

remove_whitelist() {
    local ip=$1
    validate_ip "$ip" >/dev/null
    python3 - "$ip" "$MANUAL_JAIL" "$WHITELIST_CONF" <<'PY'
import ipaddress, pathlib, sys
ip = str(ipaddress.ip_address(sys.argv[1]))
jail, nginx = (pathlib.Path(item) for item in sys.argv[2:])
if jail.exists():
    lines = []
    for line in jail.read_text().splitlines():
        if line.lower().startswith('ignoreip') and '=' in line:
            values = [value for value in line.split('=', 1)[1].split() if value != ip]
            line = 'ignoreip = ' + ' '.join(values)
        lines.append(line)
    jail.write_text('\n'.join(lines) + '\n')
if nginx.exists():
    lines = []
    for line in nginx.read_text().splitlines():
        fields = line.strip().split()
        try:
            if fields and str(ipaddress.ip_address(fields[0])) == ip:
                continue
        except ValueError:
            pass
        lines.append(line)
    nginx.write_text('\n'.join(lines) + '\n')
print(f'whitelist_removed={ip}')
PY
    systemctl reload fail2ban 2>/dev/null || systemctl restart fail2ban
    nginx -t && systemctl reload nginx
}

remove_blacklist() {
    local ip=$1
    validate_ip "$ip" >/dev/null
    python3 - "$ip" "$BLACKLIST_FILE" "$BLACKLIST_CONF" <<'PY'
import ipaddress, pathlib, sys
ip = str(ipaddress.ip_address(sys.argv[1]))
source, nginx = (pathlib.Path(item) for item in sys.argv[2:])
items = []
if source.exists():
    for value in source.read_text().split():
        try:
            normalized = str(ipaddress.ip_address(value))
            if normalized != ip:
                items.append(normalized)
        except ValueError:
            pass
source.write_text(('\n'.join(sorted(set(items))) + '\n') if items else '')
source.chmod(0o600)
nginx.write_text(''.join(f'    deny {value};\n' for value in sorted(set(items))) or '    # empty\n')
nginx.chmod(0o644)
print(f'blacklist_removed={ip}')
PY
    fail2ban-client set rhisseth-auth unbanip "$ip" >/dev/null 2>&1 || true
    nginx -t && systemctl reload nginx
}

pause() { read -r -p 'Нажмите Enter для продолжения...' _; }

while true; do
    printf '\n=== Rhisseth: управление IP-списками ===\n'
    printf '1. Показать whitelist\n2. Добавить IP в whitelist\n3. Удалить IP из whitelist\n'
    printf '4. Показать blacklist и активные баны\n5. Добавить IP в blacklist\n6. Удалить IP из blacklist\n0. Выход\n\n'
    read -r -p 'Выберите действие: ' choice
    case "$choice" in
        1) "$SCRIPT_DIR/rhisseth-ip-whitelist-list.sh"; pause ;;
        2) read -r -p 'IP для whitelist: ' ip; validate_ip "$ip" >/dev/null; "$SCRIPT_DIR/rhisseth-ip-whitelist-add.sh" "$ip"; pause ;;
        3) read -r -p 'IP для удаления из whitelist: ' ip; remove_whitelist "$ip"; pause ;;
        4) "$SCRIPT_DIR/rhisseth-ip-bans-list.sh"; pause ;;
        5) read -r -p 'IP для blacklist: ' ip; validate_ip "$ip" >/dev/null; "$SCRIPT_DIR/rhisseth-ip-blacklist-add.sh" "$ip"; pause ;;
        6) read -r -p 'IP для удаления из blacklist: ' ip; remove_blacklist "$ip"; pause ;;
        0) exit 0 ;;
        *) echo 'Неизвестный пункт меню.'; pause ;;
    esac
done
