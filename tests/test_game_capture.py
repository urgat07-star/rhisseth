import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app/backend'))
from fastapi.testclient import TestClient
from main import app


class GameCaptureTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.player = {'user_id': 2, 'user_login': 'player', 'role_alias': 'user', 'csrf': 'test'}
        self.headers = {'X-CSRF-Token': 'test'}

    def test_capture_delegates_to_server_battle(self):
        async def started(q, r, request):
            self.assertEqual((q, r), (0, 0))
            self.assertEqual(await request.json(), {'general_id': 7})
            return {'battle': {'id': 19, 'status': 'active'}}

        with patch('main.current_user', return_value=self.player), patch('main.start_capture_battle', side_effect=started):
            response = self.client.post('/api/game/hexes/0/0/capture', headers=self.headers, json={'general_id': 7})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['battle']['status'], 'active')

    def test_capture_requires_csrf(self):
        with patch('main.current_user', return_value=self.player), patch('main.start_capture_battle', side_effect=AssertionError('No battle')):
            self.assertEqual(self.client.post('/api/game/hexes/0/0/capture', json={'general_id': 7}).status_code, 403)

    def test_capture_requires_general_before_database_access(self):
        with patch('main.current_user', return_value=self.player), patch('battle.connect', side_effect=AssertionError('No DB access')):
            response=self.client.post('/api/game/hexes/0/0/capture',headers=self.headers)
        self.assertEqual(response.status_code,400)

    def test_starting_battle_does_not_transfer_hex(self):
        class Result:
            def __init__(self,one=None,many=None):self.one=one;self.many=many or []
            def fetchone(self):return self.one
            def fetchall(self):return self.many
        class Connection:
            def __init__(self):self.calls=[]
            def execute(self,sql,args=None):
                self.calls.append((sql,args))
                if 'FROM player_generals pg JOIN general_catalog' in sql:
                    return Result((7,1,0,'active',10,2,2,1,1,'Генерал','general.webp',5))
                if 'SELECT turn_number FROM game_clock' in sql:return Result((0,))
                if 'FROM game_turn_votes' in sql or 'FROM game_battles WHERE status' in sql:return Result()
                if 'SELECT data FROM hexes' in sql and 'FOR UPDATE' not in sql:
                    return Result(({'Тип владельца':'Игрок','Владелец':'2'},))
                if 'SELECT data FROM hexes' in sql:
                    return Result(({'Тип владельца':'Ничейная территория','Владелец':'',
                                    'Категория':'Суша','Проходимость':'1','Защита':'0','Уровень гекса':'0'},))
                if 'FROM player_general_units pgu JOIN unit_catalog' in sql:return Result(many=[])
                if 'FROM unit_catalog WHERE active' in sql:
                    return Result(many=[(1,'Варвар','units/barbarians-001.webp',5,1,1,0,1,1,1,1)])
                if 'INSERT INTO game_battles' in sql:return Result((22,))
                return Result()
        conn=Connection()
        with patch('main.current_user',return_value=self.player),patch('battle.connect') as connect,\
             patch('battle._clock',return_value=(0,None,None)),\
             patch('battle._battle',return_value={'id':22,'round_number':1}),\
             patch('battle._state',return_value={'battle':{'id':22,'status':'active'}}),\
             patch('battle._drive_ai'):
            connect.return_value.__enter__.return_value=conn
            response=self.client.post('/api/game/hexes/0/0/capture',headers=self.headers,json={'general_id':7})
        self.assertEqual(response.status_code,200)
        self.assertFalse(any(sql.startswith('UPDATE hexes') for sql,_ in conn.calls))
        self.assertTrue(any(sql.startswith('INSERT INTO game_battles') for sql,_ in conn.calls))


if __name__ == '__main__':
    unittest.main()
