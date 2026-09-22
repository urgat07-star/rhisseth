import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app/backend'))
from crest_catalog import compare_crests, discover_crests, sync_crests


class CrestCatalogTests(unittest.TestCase):
    def test_discovery_accepts_only_numbered_top_level_webp_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'gerb_10.webp').write_bytes(b'ten')
            (directory / 'gerb_2.webp').write_bytes(b'two')
            (directory / 'other.webp').write_bytes(b'other')
            (directory / 'gerb_3.png').write_bytes(b'png')
            (directory / 'archive').mkdir()
            (directory / 'archive' / 'gerb_1.webp').write_bytes(b'archive')
            self.assertEqual(list(discover_crests(directory)), ['gerb_2.webp', 'gerb_10.webp'])

    def test_comparison_reports_added_changed_and_missing(self):
        files = {
            'gerb_1.webp': {'sha256': 'a' * 64, 'file_size': 1},
            'gerb_2.webp': {'sha256': 'b' * 64, 'file_size': 2},
        }
        records = {
            'gerb_1.webp': {'sha256': 'c' * 64, 'file_size': 1, 'active': True},
            'gerb_3.webp': {'sha256': 'd' * 64, 'file_size': 3, 'active': True},
        }
        self.assertEqual(compare_crests(files, records), {
            'added': ['gerb_2.webp'],
            'changed': ['gerb_1.webp'],
            'missing': ['gerb_3.webp'],
        })

    def test_sync_upserts_files_and_deactivates_missing_records(self):
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [
            ('gerb_3.webp', 'd' * 64, 3, True),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'gerb_1.webp').write_bytes(b'crest')
            report = sync_crests(conn, directory, apply=True)
        self.assertEqual(report['added'], ['gerb_1.webp'])
        self.assertEqual(report['missing'], ['gerb_3.webp'])
        statements = [call.args[0] for call in conn.execute.call_args_list]
        self.assertTrue(any('INSERT INTO crests' in statement for statement in statements))
        self.assertTrue(any('UPDATE crests SET active=false' in statement for statement in statements))


if __name__ == '__main__':
    unittest.main()
