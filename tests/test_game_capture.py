import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app/backend'))
from fastapi.testclient import TestClient
from main import app


class GameCaptureTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.player = {'user_id': 2, 'user_login': 'player', 'role_alias': 'user', 'csrf': 'test'}
        self.headers = {'X-CSRF-Token': 'test'}

    def request_with_results(self, results):
        conn = MagicMock()
        conn.execute.return_value.fetchone.side_effect = results
        connection = patch('main.connect')
        mocked = connection.start()
        self.addCleanup(connection.stop)
        mocked.return_value.__enter__.return_value = conn
        response = self.client.post('/api/game/hexes/0/0/capture', headers=self.headers)
        return response, conn

    def test_player_captures_adjacent_land_hex_in_database(self):
        target = {'Q':'0','R':'0','Категория':'Суша','Тип владельца':'Ничейная территория','Владелец':''}
        source = {'Тип владельца':'Игрок','Владелец':'2','ID территории':'7','Цвет баронии':'#123456'}
        saved = {**target, **source}
        with patch('main.current_user', return_value=self.player):
            response, conn = self.request_with_results([(target,), (source,), (saved,)])
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['captured'])
        update = next(call for call in conn.execute.call_args_list if call.args[0].startswith('UPDATE hexes'))
        self.assertEqual(update.args[1][0].obj['Владелец'], '2')
        self.assertEqual(update.args[1][0].obj['ID территории'], '7')

    def test_sea_capture_is_rejected_without_update(self):
        target = {'Q':'0','R':'0','Категория':'Море','Тип владельца':'Ничейная территория','Владелец':''}
        with patch('main.current_user', return_value=self.player):
            response, conn = self.request_with_results([(target,)])
        self.assertEqual(response.status_code, 400)
        self.assertFalse(any(call.args[0].startswith('UPDATE hexes') for call in conn.execute.call_args_list))

    def test_capture_requires_csrf(self):
        with patch('main.current_user', return_value=self.player), patch('main.connect', side_effect=AssertionError('No DB access')):
            self.assertEqual(self.client.post('/api/game/hexes/0/0/capture').status_code, 403)


if __name__ == '__main__':
    unittest.main()
