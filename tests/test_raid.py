import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app/backend'))
from battle import _pay_raid
from main import app


class Result:
    def __init__(self,one=None,many=None):self.one=one;self.many=many or []
    def fetchone(self):return self.one
    def fetchall(self):return self.many


class RaidConnection:
    def __init__(self,owner):self.owner=owner;self.calls=[]
    def execute(self,sql,args=None):
        self.calls.append((sql,args))
        if sql.startswith('SELECT data FROM hexes'):
            return Result(({'Тип владельца':'Игрок','Владелец':self.owner,'Уровень гекса':'0'},))
        if 'FROM raid_balance' in sql:return Result((1,10,40,10))
        if sql.startswith('SELECT q,r FROM hexes'):
            return Result(many=[(0,0),(1,0),(2,0),(3,0),(4,0)])
        return Result()


class RaidTests(unittest.TestCase):
    def battle(self,owner):
        return {'id':1,'target_q':0,'target_r':0,'target_owner_type':'Игрок',
                'target_owner_id':owner,'created_turn':3,'attacker_user_id':2,
                'general_id':7,'round_number':1}

    def test_own_raid_morale_wave_stops_after_three_rings(self):
        conn=RaidConnection('2')
        _pay_raid(conn,self.battle('2'))
        penalties=[args[-1] for sql,args in conn.calls if sql.startswith('INSERT INTO game_hex_morale')]
        self.assertEqual(penalties,[10,5,2.5,1.25])
        self.assertFalse(any(sql.startswith('INSERT INTO barony_peasant_reserve') for sql,_ in conn.calls))

    def test_enemy_raid_grants_nominal_percentage_without_morale_loss(self):
        conn=RaidConnection('3')
        _pay_raid(conn,self.battle('3'))
        grant=next(args for sql,args in conn.calls if sql.startswith('INSERT INTO barony_peasant_reserve'))
        self.assertEqual(grant,(2,4))
        self.assertFalse(any(sql.startswith('INSERT INTO game_hex_morale') for sql,_ in conn.calls))

    def test_winning_enemy_raid_can_destroy_one_building_level(self):
        conn=RaidConnection('3')
        original=conn.execute
        def execute(sql,args=None):
            if sql.startswith('SELECT data FROM hexes'):
                conn.calls.append((sql,args))
                return Result(({'Тип владельца':'Игрок','Владелец':'3','Уровень гекса':'2'},))
            return original(sql,args)
        conn.execute=execute
        battle={**self.battle('3'),'purpose':'raid','status':'attacker_won','destroyed_at':None}
        user={'user_id':2,'user_login':'player','role_alias':'user','csrf':'test'}
        with patch('main.current_user',return_value=user),patch('battle.connect') as connect,\
             patch('battle._battle',return_value=battle),patch('battle._state',return_value={'battle':battle}):
            connect.return_value.__enter__.return_value=conn
            response=TestClient(app).post('/api/game/battles/1/destroy',headers={'X-CSRF-Token':'test'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['new_level'],1)
        self.assertEqual(response.json()['building'],'Лагерь')
        patch_hex=next(args[0].obj for sql,args in conn.calls if sql.startswith('UPDATE hexes'))
        self.assertEqual(patch_hex['Уровень гекса'],'1')


if __name__=='__main__':unittest.main()
