import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app/backend'))
from fastapi.testclient import TestClient
from main import app


class MovementTests(unittest.TestCase):
    def test_frontend_converts_map_string_coordinates_before_move(self):
        source=(Path(__file__).resolve().parents[1]/'app/frontend/app.js').read_text(encoding='utf-8')
        self.assertIn('body:JSON.stringify({q:Number(row.Q),r:Number(row.R)})',source)

    def test_move_spends_target_passability(self):
        source={'Тип владельца':'Игрок','Владелец':'2','Категория':'Суша'}
        target={**source,'Проходимость':'3'}
        conn=MagicMock()
        conn.execute.return_value.fetchone.side_effect=[(1,0,'active',5),None,None,(source,),(target,)]
        with patch('main.current_user',return_value={'user_id':2,'user_login':'player','role_alias':'user','csrf':'test'}),\
             patch('movement.random.randint',return_value=1),\
             patch('movement._clock',return_value=(0,None,None)),\
             patch('movement.connect') as connect:
            connect.return_value.__enter__.return_value=conn
            response=TestClient(app).post('/api/game/generals/7/move',json={'q':0,'r':0},headers={'X-CSRF-Token':'test'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['logistics_left'],2)
        update=[call for call in conn.execute.call_args_list if call.args[0].startswith('UPDATE player_generals')]
        self.assertEqual(update[0].args[1],(0,0,3,0,7))

    def test_move_refuses_insufficient_logistics(self):
        source={'Тип владельца':'Игрок','Владелец':'2','Категория':'Суша'}
        conn=MagicMock()
        conn.execute.return_value.fetchone.side_effect=[(1,0,'active',2),None,None,(source,),({**source,'Проходимость':'3'},)]
        with patch('main.current_user',return_value={'user_id':2,'user_login':'player','role_alias':'user','csrf':'test'}),\
             patch('movement.random.randint',return_value=1),\
             patch('movement._clock',return_value=(0,None,None)),\
             patch('movement.connect') as connect:
            connect.return_value.__enter__.return_value=conn
            response=TestClient(app).post('/api/game/generals/7/move',json={'q':0,'r':0},headers={'X-CSRF-Token':'test'})
        self.assertEqual(response.status_code,409)
        self.assertFalse(any(call.args[0].startswith('UPDATE player_generals') for call in conn.execute.call_args_list))

    def test_entering_unbridged_river_uses_remaining_logistics(self):
        source={'Тип владельца':'Игрок','Владелец':'2','Категория':'Суша'}
        target={**source,'Проходимость':'2','Дополнительный объект':'Река'}
        conn=MagicMock()
        conn.execute.return_value.fetchone.side_effect=[(1,0,'active',7),None,None,(source,),(target,),None]
        with patch('main.current_user',return_value={'user_id':2,'user_login':'player','role_alias':'user','csrf':'test'}),\
             patch('movement.random.randint',return_value=1),\
             patch('movement._clock',return_value=(0,None,None)),\
             patch('movement.connect') as connect:
            connect.return_value.__enter__.return_value=conn
            response=TestClient(app).post('/api/game/generals/7/move',json={'q':0,'r':0},headers={'X-CSRF-Token':'test'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['cost'],7)
        self.assertEqual(response.json()['logistics_left'],0)

    def test_connected_river_halves_cost_rounding_down(self):
        river={'Тип владельца':'Игрок','Владелец':'2','Категория':'Суша',
               'Дополнительный объект':'Река','Проходимость':'3'}
        conn=MagicMock()
        conn.execute.return_value.fetchone.side_effect=[(1,0,'active',2),None,None,(river,),(river,),(1,)]
        with patch('main.current_user',return_value={'user_id':2,'user_login':'player','role_alias':'user','csrf':'test'}),\
             patch('movement.random.randint',return_value=1),\
             patch('movement._clock',return_value=(0,None,None)),\
             patch('movement.connect') as connect:
            connect.return_value.__enter__.return_value=conn
            response=TestClient(app).post('/api/game/generals/7/move',json={'q':0,'r':0},headers={'X-CSRF-Token':'test'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['cost'],1)
        self.assertEqual(response.json()['logistics_left'],1)

    def test_random_encounter_is_created_in_movement_transaction(self):
        source={'Тип владельца':'Игрок','Владелец':'2','Категория':'Суша'}
        target={**source,'Проходимость':'1','Опасность':'5'}
        conn=MagicMock()
        conn.execute.return_value.fetchone.side_effect=[(1,0,'active',5),None,None,(source,),(target,)]
        with patch('main.current_user',return_value={'user_id':2,'user_login':'player','role_alias':'user','csrf':'test'}),\
             patch('movement.random.randint',return_value=6),\
             patch('movement._clock',return_value=(0,None,None)),\
             patch('battle.create_encounter_battle',return_value={'battle':{'id':22}}) as created,\
             patch('movement.connect') as connect:
            connect.return_value.__enter__.return_value=conn
            response=TestClient(app).post('/api/game/generals/7/move',json={'q':0,'r':0},headers={'X-CSRF-Token':'test'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['battle']['battle']['id'],22)
        self.assertIs(created.call_args.args[0],conn)


if __name__=='__main__':unittest.main()
