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

    def test_unit_price_with_predecessor_upgrades_existing_assignment(self):
        class Result:
            def __init__(self, one=None, many=None): self.one,self.many=one,many or []
            def fetchone(self): return self.one
            def fetchall(self): return self.many
        conn=MagicMock()
        def execute(sql,args=()):
            if 'FROM player_generals WHERE id=' in sql:return Result((7,))
            if 'FROM unit_catalog WHERE id=' in sql and 'purchasable' in sql:return Result((1,))
            if 'FROM unit_upgrade_requirements' in sql:return Result((2,))
            if 'FROM player_general_units' in sql and 'unit_id=' in sql:return Result((55,3))
            if 'FROM unit_resource_costs' in sql:return Result(many=[('wood',1),('cloth',1)])
            if 'SELECT gold FROM game_wallets' in sql:return Result((10,))
            if 'SELECT resource_code,quantity FROM game_inventory' in sql:return Result(many=[('wood',5),('cloth',5)])
            return Result()
        conn.execute.side_effect=execute; self.connection(conn)
        with patch('main.current_user',return_value=self.player):
            response=self.client.post('/api/cabinet/army/generals/7/units',json={'unit_id':3},headers=self.headers)
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.json()['upgraded'])
        self.assertEqual(response.json()['slot'],3)
        self.assertTrue(any('UPDATE player_general_units SET unit_id=' in call.args[0] for call in conn.execute.call_args_list))
        upgrade_sql=next(call.args[0] for call in conn.execute.call_args_list if 'UPDATE player_general_units SET unit_id=' in call.args[0])
        self.assertIn("status='ready'",upgrade_sql)
        self.assertNotIn("status='active'",upgrade_sql)
        self.assertFalse(any('INSERT INTO player_general_units' in call.args[0] for call in conn.execute.call_args_list))
        self.assertFalse(any('SELECT slot FROM player_general_units' in call.args[0] for call in conn.execute.call_args_list), 'upgrade must not look for a free slot')
        self.assertTrue(any('UPDATE game_inventory SET quantity=quantity-' in call.args[0] and call.args[1][:3] == (1,2,'wood') for call in conn.execute.call_args_list))
        self.assertTrue(any('UPDATE game_inventory SET quantity=quantity-' in call.args[0] and call.args[1][:3] == (1,2,'cloth') for call in conn.execute.call_args_list))

    def test_every_catalogued_upgrade_uses_its_configured_predecessor(self):
        """The endpoint must not hard-code the militia/hunter chain."""
        class Result:
            def __init__(self, one=None, many=None): self.one,self.many=one,many or []
            def fetchone(self): return self.one
            def fetchall(self): return self.many
        for target_id,predecessor_id in ((3,2),(8,7),(13,12)):
            with self.subTest(target_id=target_id,predecessor_id=predecessor_id):
                conn=MagicMock()
                def execute(sql,args=()):
                    if 'FROM player_generals WHERE id=' in sql:return Result((7,))
                    if 'FROM unit_catalog WHERE id=' in sql and 'purchasable' in sql:return Result((1,))
                    if 'FROM unit_upgrade_requirements' in sql:return Result((predecessor_id,))
                    if 'FROM player_general_units' in sql and 'unit_id=' in sql:
                        self.assertEqual(args,(7,predecessor_id));return Result((50+predecessor_id,4))
                    if 'FROM unit_resource_costs' in sql:return Result(many=[('gold',2)])
                    if 'SELECT gold FROM game_wallets' in sql:return Result((20,))
                    if 'SELECT resource_code,quantity FROM game_inventory' in sql:return Result(many=[])
                    return Result()
                conn.execute.side_effect=execute; self.connection(conn)
                with patch('main.current_user',return_value=self.player):
                    response=self.client.post('/api/cabinet/army/generals/7/units',json={'unit_id':target_id},headers=self.headers)
                self.assertEqual(response.status_code,200)
                self.assertTrue(response.json()['upgraded'])
                self.assertTrue(any('UPDATE game_wallets SET gold=gold-' in call.args[0] and call.args[1][:2] == (2,2) for call in conn.execute.call_args_list))


if __name__ == '__main__':
    unittest.main()
