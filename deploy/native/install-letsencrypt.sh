#!/usr/bin/env bash
# Run as root on the approved Rhisseth VDS, through a runner or local Docker.
set -Eeuo pipefail
umask 077
[[ $(id -u) == 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
email=${1:?Usage: sudo bash install-letsencrypt.sh ACME_CONTACT_EMAIL}
[[ "$email" == *@* && "$email" != -* ]] || { echo 'Invalid email.' >&2; exit 1; }
base=/opt/rhisseth
site=/etc/nginx/sites-available/rhisseth
config=$base/secrets/letsencrypt
work=$base/.local/certbot
logs=$base/reports/certbot
stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup=$base/backups/nginx-before-letsencrypt-$stamp.conf
[[ -f "$site" ]] || { echo 'Rhisseth nginx site missing.' >&2; exit 1; }
for unit in rhisseth-certbot.service rhisseth-certbot.timer; do
    [[ -f "$base/repository/deploy/native/$unit" ]] || { echo "Missing unit: $unit" >&2; exit 1; }
done
grep -Eq 'server_name[^;]*\brhisseth\.ru\b' "$site" || { echo 'Domain missing in Rhisseth site.' >&2; exit 1; }
systemctl is-active --quiet nginx
addresses=$(getent ahostsv4 rhisseth.ru | awk '{print $1}' | sort -u)
[[ "$addresses" == '62.113.109.168' ]] || {
    echo 'Domain does not resolve to the approved VDS.' >&2; exit 1;
}
nginx -t
install -d -m 700 "$config" "$work" "$logs" "$base/backups"
cp -p "$site" "$backup"
echo "Nginx backup: $backup"
apt-get update
apt-get install -y certbot python3-certbot-nginx
args=(--config-dir "$config" --work-dir "$work" --logs-dir "$logs")
# Nginx plugin retains application locations and installs the full chain.
if ! certbot --nginx "${args[@]}" --non-interactive --agree-tos \
    --email "$email" --cert-name rhisseth.ru -d rhisseth.ru --redirect; then
    cp -p "$backup" "$site"
    nginx -t && systemctl reload nginx
    echo 'Issuance failed; original Rhisseth nginx site restored.' >&2
    exit 1
fi
nginx -t
systemctl reload nginx
install -d -m 700 "$config/renewal-hooks/deploy"
cat > "$config/renewal-hooks/deploy/reload-nginx" <<'HOOK'
#!/bin/sh
set -eu
/usr/sbin/nginx -t
/usr/bin/systemctl reload nginx
HOOK
chmod 700 "$config/renewal-hooks/deploy/reload-nginx"
# Dedicated timer: the distro timer uses /etc/letsencrypt, not our project dirs.
install -m 644 /opt/rhisseth/repository/deploy/native/rhisseth-certbot.service /etc/systemd/system/rhisseth-certbot.service
install -m 644 /opt/rhisseth/repository/deploy/native/rhisseth-certbot.timer /etc/systemd/system/rhisseth-certbot.timer
systemctl daemon-reload
systemctl enable --now rhisseth-certbot.timer
certbot renew "${args[@]}" --cert-name rhisseth.ru --dry-run --run-deploy-hooks
curl --fail --silent --show-error --max-time 20 https://rhisseth.ru/index.php -o /dev/null
systemctl list-timers rhisseth-certbot.timer --no-pager
openssl x509 -in "$config/live/rhisseth.ru/fullchain.pem" -noout -issuer -dates -ext subjectAltName
echo 'Certificate, HTTPS and renewal verified.'
