#!/usr/bin/env bash
set -euo pipefail
[[ ${EUID:-$(id -u)} -eq 0 ]] || { echo 'Run as root' >&2; exit 1; }
echo '=== configured fail2ban whitelist ==='
grep -E '^ignoreip\s*=' /etc/fail2ban/jail.d/rhisseth.local /etc/fail2ban/jail.d/rhisseth-manual.local 2>/dev/null || echo '(empty)'
echo '=== nginx whitelist ==='
awk '/geo \$rhisseth_whitelisted/,/^}/' /etc/nginx/sites-available/rhisseth 2>/dev/null || echo '(not configured)'
