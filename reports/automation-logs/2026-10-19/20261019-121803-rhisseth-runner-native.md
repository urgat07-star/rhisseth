# Rhisseth runner control operation

- UTC: 2026-10-19T12:18:03.6517005Z
- Europe/Moscow: 2026-10-19T15:18:03.6517005
- Controller: N7198 / Codex
- Runner: STU-AUTOMATION-01 / 10.210.52.128
- Targets: runner project artifacts; selected VPS 62.113.109.168; project GitHub; Passbolt resource only
- Passbolt resource: da44a388-e458-4379-ab4c-c204696804b2
- Script: Publish-RhissethFromRunner.py
- Action: pinned SSH control, reviewed script transfer and execution
- Operation: publish-economy-v045
- Change/reboot: exact VPS changes recorded by remote operation; no reboot requested

Preflight: reviewed script; pinned ED25519 fingerprint confirmed; audit log writable
Archive ref: economy-v0.4.5; commit: a556b072416158adb178721f44b4a2f4587e63e5
Preflight: runner identity, archive and Passbolt endpoint verified; reboot=false
Preflight: archive bytes=23919468; SHA256=f1a8f2ee8b80ef1feca514f0d649096472e78ee4a71b3be08542458e8af3634c; audit writable
pg_dump: exit_code=0; bytes=354514; output suppressed
Command: pg_restore --list /opt/rhisseth/backups/economy-v045-20261019121814/rhisseth.dump; exit_code=0
Command: runuser -u postgres -- createdb -O rhisseth rhisseth_e045_58ea1f2d; exit_code=0
Command: runuser -u postgres -- pg_restore --no-owner --role=rhisseth -d rhisseth_e045_58ea1f2d /tmp/rhisseth-economy-v045-restore-20261019121814.dump; exit_code=0
Command: /opt/rhisseth/venv/bin/python /opt/rhisseth/repository.economy-v045-staging-20261019121814/app/backend/migrate.py; exit_code=0
Crests: {'files': 18, 'added': [], 'changed': [], 'missing': [], 'synchronized': True}
Command: runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -At -d rhisseth_e045_58ea1f2d -c SELECT count(*) FROM schema_migrations WHERE name='046_population_tax_history.sql'; exit_code=0
Command: runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -At -d rhisseth_e045_58ea1f2d -c SELECT count(*) FROM information_schema.tables WHERE table_name IN ('hex_economy_history','hex_population_events','hex_economy_state','game_population_years'); exit_code=0
Restored-copy validation: migration 046 and four tables verified
Command: runuser -u postgres -- dropdb --if-exists rhisseth_e045_58ea1f2d; exit_code=0
Command: systemctl stop rhisseth; exit_code=0
Command: /opt/rhisseth/venv/bin/python /opt/rhisseth/repository.economy-v045-staging-20261019121814/app/backend/migrate.py; exit_code=0
Crests: {'files': 18, 'added': [], 'changed': [], 'missing': [], 'synchronized': True}
Command: runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -At -d rhisseth -c SELECT count(*) FROM schema_migrations WHERE name='046_population_tax_history.sql'; exit_code=0
Command: runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -At -d rhisseth -c SELECT turn_number FROM game_clock WHERE id=true; exit_code=0
Command: runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -At -d rhisseth -c SELECT count(*) FROM game_population_years WHERE year=18; exit_code=0
Command: /opt/rhisseth/venv/bin/python -c import sys;sys.path.insert(0,'/opt/rhisseth/repository.economy-v045-staging-20261019121814/app/backend');from db import connect;from game_clock import _annual_population_and_tax;c=connect();c.execute('INSERT INTO game_population_years(year) VALUES (%s)',(18,));_annual_population_and_tax(c,18);c.commit();c.close();print('backfilled year 18'); exit_code=0
backfilled year 18
Command: runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -At -d rhisseth -c SELECT count(*) FROM hex_economy_history; exit_code=0
Command: systemctl start rhisseth; exit_code=0
Validation: history_rows=723; backfill_year=18; health=200; backup=/opt/rhisseth/backups/economy-v045-20261019121814/rhisseth.dump; reboot=false
Final exit_code=0; host_reboot=false; player_reset=false
Exit code: 0
Validation: exit_code=0; reboot=false; secrets_logged=false
Validation: exit_code=0; operation=publish-economy-v045; change/reboot status in sanitized remote output
