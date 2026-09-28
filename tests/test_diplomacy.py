import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app/backend'))
from fastapi.testclient import TestClient
from main import app


class RansomTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.player = {'user_id': 2, 'user_login': 'player', 'role_alias': 'user', 'csrf': 'test'}

    def connection(self, captive):
        conn = MagicMock()

        def execute(query, params=None):
            result = MagicMock()
            if 'FROM player_generals' in query and 'FOR UPDATE' in query:
                result.fetchone.return_value = captive
            elif 'FROM game_wallets' in query and 'FOR UPDATE' in query:
                result.fetchall.return_value = [(2, 300), (3, 200)]
            elif 'SELECT q,r FROM hexes' in query:
                result.fetchone.return_value = (0, 0)
            return result

        conn.execute.side_effect = execute
        patcher = patch('diplomacy.connect')
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        mocked.return_value.__enter__.return_value = conn
        return conn

    def test_ransom_transfers_gold_and_releases_general_once(self):
        conn = self.connection((2, 3, 'captive'))
        with patch('main.current_user', return_value=self.player):
            response = self.client.post('/api/cabinet/diplomacy/generals/7/ransom',
                                        json={}, headers={'X-CSRF-Token': 'test'})
        self.assertEqual(response.status_code, 200)
        sql = [call.args[0] for call in conn.execute.call_args_list]
        self.assertEqual(sum('UPDATE game_wallets' in query for query in sql), 2)
        self.assertEqual(sum('INSERT INTO game_gold_ledger' in query for query in sql), 2)

    def test_general_no_longer_captive_cannot_be_paid_again(self):
        conn = self.connection((2, None, 'active'))
        with patch('main.current_user', return_value=self.player):
            response = self.client.post('/api/cabinet/diplomacy/generals/7/ransom',
                                        json={}, headers={'X-CSRF-Token': 'test'})
        self.assertEqual(response.status_code, 409)
        self.assertFalse(any('UPDATE game_wallets' in call.args[0] for call in conn.execute.call_args_list))


if __name__ == '__main__':
    unittest.main()
