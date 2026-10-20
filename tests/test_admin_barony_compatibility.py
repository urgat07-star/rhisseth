import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AdminBaronyCompatibilityTests(unittest.TestCase):
    def test_backend_has_read_only_fallback_for_admin_owned_hexes(self):
        source=(ROOT/'app/backend/player_cabinet.py').read_text(encoding='utf-8')
        self.assertIn("request.state.user['role_alias'] in ('admin','moderator')",source)
        self.assertIn("'statistics':statistics(owned),'editable':False",source)

    def test_optional_economy_tables_are_checked_before_queries(self):
        source=(ROOT/'app/backend/player_cabinet.py').read_text(encoding='utf-8')
        self.assertIn("to_regclass('game_wallets')",source)
        self.assertIn('if inventory_table and resources_table else []',source)
        self.assertIn("'available':not missing_tables",source)

    def test_read_only_fallback_hides_mutating_barony_settings(self):
        source=(ROOT/'app/frontend/cabinet.js').read_text(encoding='utf-8')
        self.assertIn("barony.editable===false",source)


if __name__ == '__main__':
    unittest.main()
