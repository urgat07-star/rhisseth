#!/usr/bin/env bash
# Reviewed server-side part of menu item 7. Never print secret environment values.
set -euo pipefail

repository="${1:-/opt/rhisseth/repository}"
python_bin="/opt/rhisseth/venv/bin/python"
environment_file="/opt/rhisseth/secrets/app.env"
migration_runner="$repository/app/backend/migrate.py"
migrations_dir="$repository/data/migrations"
backup_dir="/var/backups/rhisseth"
stamp="$(date -u +%Y%m%d-%H%M%S)"
database_backup="$backup_dir/rhisseth-db-$stamp.dump"

echo "PREFLIGHT=started"
test -d "$repository"
test -x "$python_bin"
test -r "$environment_file"
test -f "$migration_runner"
test -d "$migrations_dir"
command -v pg_dump >/dev/null
command -v pg_restore >/dev/null
command -v psql >/dev/null
command -v createdb >/dev/null
command -v dropdb >/dev/null
echo "PREFLIGHT=passed"

set -a
# shellcheck disable=SC1090
source "$environment_file"
set +a
export DB_HOST="${DB_HOST:-127.0.0.1}"
export DB_NAME="${DB_NAME:-rhisseth}"
export DB_USER="${DB_USER:-rhisseth}"
export DB_PORT="${DB_PORT:-5432}"
export DB_PASSWORD_FILE="${DB_PASSWORD_FILE:-/opt/rhisseth/secrets/db-password.txt}"
test -r "$DB_PASSWORD_FILE"
production_database="$DB_NAME"
validation_database="rhisseth_migration_check_${stamp//-/}"

cleanup_validation_database() {
    if [[ -n "${validation_database:-}" ]]; then
        runuser -u postgres -- dropdb --if-exists --force "$validation_database" >/dev/null 2>&1 || true
    fi
}
trap cleanup_validation_database EXIT

verify_all_migrations() {
    local database="$1"
    local label="$2"
    local missing=0
    while IFS= read -r migration; do
        local name
        local applied
        name="$(basename "$migration")"
        if [[ ! "$name" =~ ^[A-Za-z0-9_.-]+$ ]]; then
            echo "INVALID_MIGRATION_NAME=$name"
            return 31
        fi
        applied="$(runuser -u postgres -- psql -X -At -d "$database" -c "SELECT count(*) FROM schema_migrations WHERE name='$name'")"
        if [[ "$applied" != "1" ]]; then
            echo "MISSING_MIGRATION=$name DATABASE=$label"
            missing=1
        fi
    done < <(find "$migrations_dir" -maxdepth 1 -type f -name '*.sql' -print | sort)
    if [[ "$missing" != "0" ]]; then return 32; fi
    echo "MIGRATIONS_CURRENT=$label"
}

install -d -o postgres -g postgres -m 700 "$backup_dir"
runuser -u postgres -- pg_dump -Fc -d "$production_database" -f "$database_backup"
test -s "$database_backup"
runuser -u postgres -- pg_restore --list "$database_backup" >/dev/null
chmod 600 "$database_backup"
echo "DATABASE_BACKUP=$database_backup"
echo "DATABASE_BACKUP_VALID=1"

# Универсальная репетиция: восстанавливаем текущие реальные данные во временную
# БД и применяем к ним весь каталог миграций до изменения production.
cleanup_validation_database
runuser -u postgres -- createdb --owner="$DB_USER" "$validation_database"
runuser -u postgres -- pg_restore --exit-on-error --no-owner --no-privileges --role="$DB_USER" \
    -d "$validation_database" "$database_backup"
export DB_NAME="$validation_database"
runuser -u rhisseth --preserve-environment -- "$python_bin" "$migration_runner"
verify_all_migrations "$validation_database" "validation"
echo "MIGRATION_DRY_RUN=passed"
cleanup_validation_database
validation_database=""

export DB_NAME="$production_database"
runuser -u rhisseth --preserve-environment -- "$python_bin" "$migration_runner"
verify_all_migrations "$production_database" "production"
echo "MIGRATIONS_EXECUTED=production"

systemctl restart rhisseth
active=0
for _ in $(seq 1 12); do
    if systemctl is-active --quiet rhisseth; then active=1; break; fi
    sleep 2
done
if [[ "$active" != "1" ]]; then
    echo "SERVICE_RHISSETH=failed"
    systemctl status rhisseth --no-pager || true
    exit 34
fi

nginx -t
systemctl reload nginx
systemctl is-active --quiet nginx
health_code="000"
for attempt in $(seq 1 10); do
    health_code="$(curl -ksS -o /dev/null -w '%{http_code}' --max-time 15 https://rhisseth.ru/health || true)"
    echo "HEALTH_ATTEMPT=$attempt HTTP=$health_code"
    case "$health_code" in 200|401) break ;; esac
    sleep 3
done
case "$health_code" in
    200|401) ;;
    *) echo "HEALTH_HTTP=$health_code"; exit 35 ;;
esac

echo "HEALTH_HTTP=$health_code"
echo "SERVICE_RHISSETH=active"
echo "SERVICE_NGINX=active"
echo "APPLY_VDS=passed"
