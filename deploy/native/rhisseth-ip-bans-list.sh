#!/usr/bin/env bash
set -euo pipefail
[[ ${EUID:-$(id -u)} -eq 0 ]] || { echo 'Run as root' >&2; exit 1; }
echo '=== fail2ban jails ==='
fail2ban-client status || true
for jail in $(fail2ban-client status 2>/dev/null | sed -n 's/.*Jail list:\s*//p' | tr ',' ' '); do
  jail=$(echo "$jail" | xargs)
  [[ -n "$jail" ]] || continue
  echo "=== $jail ==="
  fail2ban-client status "$jail" || true
done
echo '=== persistent blacklist ==='
if [[ -f /etc/rhisseth-blacklist ]]; then sort -u /etc/rhisseth-blacklist; else echo '(empty)'; fi
echo '=== manual whitelist ==='
grep -E '^ignoreip\s*=' /etc/fail2ban/jail.d/rhisseth-manual.local 2>/dev/null || echo '(empty)'
