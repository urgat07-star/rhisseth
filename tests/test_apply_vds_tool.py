import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ApplyVdsToolTests(unittest.TestCase):
    def test_menu_item_seven_runs_backup_migrations_and_validation(self):
        menu = (ROOT / 'tools' / 'rhisseth-sync.ps1').read_text(encoding='utf-8-sig')
        self.assertIn("'7' { 'apply-vds' }", menu)
        self.assertIn('Backup БД, репетиция всех миграций', menu)
        self.assertIn("Invoke-Tool 'Apply-Vds.ps1'", menu)

    def test_controller_transfers_reviewed_script_and_writes_audit_log(self):
        controller = (ROOT / 'tools' / 'Apply-Vds.ps1').read_text(encoding='utf-8-sig')
        self.assertIn("Apply-VdsRemote.sh", controller)
        self.assertIn("reports\\automation-logs", controller)
        self.assertIn('& scp @scp', controller)
        self.assertIn("$safeOutput", controller)
        self.assertLess(controller.index('Set-Content -Encoding UTF8 $logPath'), controller.index('& scp @scp'))

    def test_remote_script_backups_before_migrating_and_restarting(self):
        script = (ROOT / 'tools' / 'Apply-VdsRemote.sh').read_text(encoding='utf-8')
        backup = script.index('pg_dump -Fc')
        migrate = script.index('"$python_bin" "$migration_runner"')
        restart = script.index('systemctl restart rhisseth')
        self.assertLess(backup, migrate)
        self.assertLess(migrate, restart)
        self.assertIn('pg_restore --list', script)
        self.assertIn('install -d -o postgres -g postgres -m 700', script)
        self.assertIn('schema_migrations', script)
        self.assertIn('createdb --owner="$DB_USER"', script)
        self.assertIn('pg_restore --exit-on-error --no-owner --no-privileges --role="$DB_USER"', script)
        self.assertIn('MIGRATION_DRY_RUN=passed', script)
        self.assertIn('verify_all_migrations "$validation_database" "validation"', script)
        self.assertIn('verify_all_migrations "$production_database" "production"', script)
        self.assertIn('APPLY_VDS=passed', script)


if __name__ == '__main__':
    unittest.main()
