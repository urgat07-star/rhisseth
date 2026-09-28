import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app/backend'))
from fastapi.testclient import TestClient
from main import app


class ArmyTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.player = {'user_id':2,'user_login':'player','role_alias':'user','csrf':'test'}
        self.admin = {'user_id':1,'user_login':'admin','role_alias':'admin','csrf':'test'}
        self.headers = {'X-CSRF-Token':'test'}

    def connection(self, conn):
        context=patch('army.connect')
        mocked=context.start(); self.addCleanup(context.stop)
        mocked.return_value.__enter__.return_value=conn

    def test_player_can_hire_generated_general(self):
        conn=MagicMock(); conn.execute.return_value.fetchone.side_effect=[(300,),(0,),(1,'Генерал 1','general/gen-01.webp'),(0,0),(7,'Альрик Храбрый','general/gen-01.webp')]
        self.connection(conn)
        with patch('main.current_user',return_value=self.player):
            response=self.client.post('/api/cabinet/army/generals',json={},headers=self.headers)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['general']['id'],7)
        self.assertTrue(response.json()['general']['name'])
        self.assertTrue(any('SET gold=gold-100' in call.args[0] for call in conn.execute.call_args_list))

    def test_general_hire_rejects_insufficient_gold(self):
        conn=MagicMock(); conn.execute.return_value.fetchone.return_value=(99,)
        self.connection(conn)
        with patch('main.current_user',return_value=self.player):
            response=self.client.post('/api/cabinet/army/generals',json={},headers=self.headers)
        self.assertEqual(response.status_code,409)
        self.assertFalse(any('INSERT INTO player_generals' in call.args[0] for call in conn.execute.call_args_list))

    def test_player_cannot_change_foreign_general(self):
        conn=MagicMock(); conn.execute.return_value.fetchone.return_value=None
        self.connection(conn)
        with patch('main.current_user',return_value=self.player):
            response=self.client.post('/api/cabinet/army/generals/99/units',json={'unit_id':1},headers=self.headers)
        self.assertEqual(response.status_code,404)

    def test_army_mutations_require_csrf(self):
        with patch('main.current_user',return_value=self.player),patch('army.connect',side_effect=AssertionError('No DB')):
            self.assertEqual(self.client.post('/api/cabinet/army/generals',json={}).status_code,403)

    def test_unit_administration_is_not_available_to_player(self):
        with patch('main.current_user',return_value=self.player),patch('army.connect',side_effect=AssertionError('No DB')):
            self.assertEqual(self.client.get('/admin/units').status_code,403)
            self.assertEqual(self.client.get('/api/admin/units').status_code,403)


if __name__ == '__main__':
    unittest.main()
