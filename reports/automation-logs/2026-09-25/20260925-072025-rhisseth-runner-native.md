# Rhisseth runner control operation

- UTC: 2026-09-25T07:20:25.2958641Z
- Europe/Moscow: 2026-09-25T10:20:25.2958641
- Controller: N7198 / Codex
- Runner: STU-AUTOMATION-01 / 10.210.52.128
- Targets: runner project artifacts; selected VPS 62.113.109.168; project GitHub; Passbolt resource only
- Passbolt resource: da44a388-e458-4379-ab4c-c204696804b2
- Script: Publish-RhissethFromRunner.py
- Action: pinned SSH control, reviewed script transfer and execution
- Operation: publish-v031
- Change/reboot: exact VPS changes recorded by remote operation; no reboot requested

Preflight: reviewed script; pinned ED25519 fingerprint confirmed; audit log writable
Archive ref: v0.3.1; commit: f2ca399efb8acd135e2f22c2fb0dfd5bd6604d79
Preflight: runner identity, archive and Passbolt endpoint verified; reboot=false
Preflight: reviewed v0.3.1 archive bytes=23431127; SHA256=a0e493f5b53c97c87c59646bb438298a5c718e48f34f6b6fe5675fcdaf93386c
Command: runuser -u postgres -- psql -At -d rhisseth -c SELECT count(*) FROM schema_migrations WHERE name='033_siege_wall.sql'; exit_code=0
Preflight: v0.3.0 database baseline confirmed; v0.3.1 files staged
pg_dump: exit_code=0; output suppressed
Command: pg_restore --list /opt/rhisseth/backups/v031-publish-20260925072034/rhisseth.dump; exit_code=0
Backup verified: /opt/rhisseth/backups/v031-publish-20260925072034/rhisseth.dump; bytes=224367; previous code=/opt/rhisseth/backups/v031-publish-20260925072034/repository-before
Command: systemctl stop rhisseth; exit_code=0
Command: /opt/rhisseth/venv/bin/python /opt/rhisseth/repository.v031-staging-20260925072034/app/backend/migrate.py; exit_code=0
Applied: 034_test_skip.sql
Crests: {'files': 18, 'added': [], 'changed': [], 'missing': [], 'synchronized': True}
Command: runuser -u postgres -- psql -At -d rhisseth -c SELECT count(*) FROM schema_migrations WHERE name='034_test_skip.sql'; exit_code=0
Command: systemctl start rhisseth; exit_code=0
Validation: local /health HTTP 200
Command: nginx -t; exit_code=0
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
Command: systemctl is-active rhisseth; exit_code=0
active
Command: curl --insecure --max-time 15 -sS -o /dev/null -w HTTPS %{http_code} https://62.113.109.168/; exit_code=0
HTTPS 303
Validation: v0.3.1 live; migration 034 applied; backup=/opt/rhisseth/backups/v031-publish-20260925072034/rhisseth.dump; player reset=false; host reboot=false
Final exit_code=0; host_reboot=false; player_reset=false
Exit code: 0
Validation: exit_code=0; reboot=false; secrets_logged=false
Validation: exit_code=0; operation=publish-v031; change/reboot status in sanitized remote output
