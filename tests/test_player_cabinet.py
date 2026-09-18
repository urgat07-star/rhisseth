import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app/backend'))
from fastapi.testclient import TestClient
from main import app
from player_cabinet import statistics


class PlayerCabinetTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(app)
        self.user={'user_id':2,'user_login':'player','role_alias':'user','csrf':'test'}
        self.headers={'X-CSRF-Token':'test'}
        self.abandon={'barony_id':7,'confirmation':'Барония','confirmed':True}
        self.profile={'login':'player','email':'player@example.invalid','current_password':'synthetic',
                      'expected':{'login':'player','email':'player@example.invalid'}}

    def test_statistics_respect_zero_and_missing_values(self):
        result=statistics([{'Категория':'Суша','Плодородие':'0','Основной ресурс':'Дерево'},
                           {'Категория':'Побережье','Плодородие':'4','Остров':'Да'},
                           {'Плодородие':'NaN'},{'Плодородие':'99'}])
        self.assertEqual(result['hex_count'],4)
        self.assertEqual(result['islands'],1)
        self.assertEqual(result['ratings']['Плодородие']['mean'],2)
        self.assertEqual(result['ratings']['Плодородие']['missing'],2)
        self.assertIsNone(result['ratings']['Защита']['mean'])

    def test_confirmation_and_extra_fields_rejected_before_database(self):
        with patch('main.current_user',return_value=self.user),patch('player_cabinet.connect',side_effect=AssertionError('Invalid request reached DB')):
            for data in ({}, {**self.abandon,'confirmed':False}, {**self.abandon,'user_id':3}):
                self.assertEqual(self.client.request('DELETE','/api/cabinet/barony',json=data,headers=self.headers).status_code,400)
            self.assertEqual(self.client.patch('/api/cabinet/account',json={**self.profile,'role':'admin'},headers=self.headers).status_code,400)

    def test_all_changes_require_csrf(self):
        with patch('main.current_user',return_value=self.user),patch('player_cabinet.connect',side_effect=AssertionError('Invalid CSRF reached DB')):
            for method,path in (('PATCH','/api/cabinet/account'),('PATCH','/api/cabinet/barony/crest'),('PATCH','/api/cabinet/barony/name'),('DELETE','/api/cabinet/barony')):
                self.assertEqual(self.client.request(method,path,json={}).status_code,403)

    def test_rename_rejects_stale_or_foreign_barony_and_preserves_geography(self):
        data={'barony_id':7,'name':' Новая барония ','expected_name':'Барония'}
        for row,expected in (((7,'Барония'),200),((8,'Барония'),409),((7,'Другое название'),409),(None,409)):
            conn=MagicMock();conn.execute.return_value.fetchone.return_value=row
            with patch('main.current_user',return_value=self.user),patch('player_cabinet.connect') as connect:
                connect.return_value.__enter__.return_value=conn
                response=self.client.patch('/api/cabinet/barony/name',json=data,headers=self.headers)
            self.assertEqual(response.status_code,expected)
            if expected==200:
                call=next(c for c in conn.execute.call_args_list if c.args[0].startswith('UPDATE hexes'))
                self.assertEqual(call.args[1][1:],('2','7'))
                self.assertEqual(call.args[1][0].obj,{'Название баронии':'Новая барония'})
            else:self.assertFalse(any(c.args[0].startswith(('UPDATE','INSERT')) for c in conn.execute.call_args_list))

    def test_abandon_cannot_delete_another_or_replacement_barony(self):
        for row,data,code in (((8,'Барония'),self.abandon,409),((7,'Барония'),{**self.abandon,'confirmation':'wrong'},400),(None,self.abandon,409)):
            conn=MagicMock();conn.execute.return_value.fetchone.return_value=row
            with patch('main.current_user',return_value=self.user),patch('player_cabinet.connect') as connect:
                connect.return_value.__enter__.return_value=conn
                response=self.client.request('DELETE','/api/cabinet/barony',json=data,headers=self.headers)
            self.assertEqual(response.status_code,code)
            self.assertFalse(any(c.args[0].startswith(('UPDATE','DELETE','INSERT')) for c in conn.execute.call_args_list))

    def test_release_is_scoped_and_preserves_geography(self):
        conn=MagicMock();conn.execute.return_value.fetchone.return_value=(7,'Барония');conn.execute.return_value.rowcount=3
        with patch('main.current_user',return_value=self.user),patch('player_cabinet.connect') as connect:
            connect.return_value.__enter__.return_value=conn
            response=self.client.request('DELETE','/api/cabinet/barony',json=self.abandon,headers=self.headers)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['released_hexes'],3)
        call=next(c for c in conn.execute.call_args_list if c.args[0].startswith('UPDATE hexes'))
        self.assertEqual(call.args[1][1:],('2','7'))
        self.assertNotIn('Название территории',call.args[0])
        self.assertNotIn('Название территории',call.args[1][0].obj)
        self.assertIn('Цвет баронии',call.args[0])
        self.assertTrue(any(c.args[0].startswith('INSERT INTO player_barony_audit') for c in conn.execute.call_args_list))
        self.assertFalse(any(c.args[0].startswith('DELETE FROM users') for c in conn.execute.call_args_list))

    def test_crest_checks_current_owner_and_updates_only_their_hexes(self):
        for row,expected in (((7,),200),((8,),409),(None,409)):
            conn=MagicMock();conn.execute.return_value.fetchone.return_value=row
            with patch('main.current_user',return_value=self.user),patch('player_cabinet.connect') as connect:
                connect.return_value.__enter__.return_value=conn
                response=self.client.patch('/api/cabinet/barony/crest',json={'barony_id':7,'crest':'gerb_2.png','color':'#2355aa'},headers=self.headers)
            self.assertEqual(response.status_code,expected)
            if expected==200:
                call=next(c for c in conn.execute.call_args_list if c.args[0].startswith('UPDATE hexes'))
                self.assertEqual(call.args[1][1:],('2','7'))
            else: self.assertFalse(any(c.args[0].startswith('UPDATE') for c in conn.execute.call_args_list))

    def test_profile_requires_password_and_current_version(self):
        for valid,previous,expected in ((False,('player','player@example.invalid','hash'),403),(True,('changed','player@example.invalid','hash'),409)):
            conn=MagicMock();conn.execute.return_value.fetchone.return_value=previous
            with patch('main.current_user',return_value=self.user),patch('player_cabinet.connect') as connect,patch('player_cabinet.verify_password',return_value=valid):
                connect.return_value.__enter__.return_value=conn
                response=self.client.patch('/api/cabinet/account',json=self.profile,headers=self.headers)
            self.assertEqual(response.status_code,expected)
            self.assertFalse(any(c.args[0].startswith(('UPDATE','DELETE','INSERT')) for c in conn.execute.call_args_list))

    def test_profile_save_rotates_session_and_keeps_role_out_of_updates(self):
        conn=MagicMock();conn.execute.return_value.fetchone.return_value=('player','player@example.invalid','hash')
        with patch('main.current_user',return_value=self.user),patch('player_cabinet.connect') as connect,patch('player_cabinet.verify_password',return_value=True):
            connect.return_value.__enter__.return_value=conn
            response=self.client.patch('/api/cabinet/account',json=self.profile,headers=self.headers)
        self.assertEqual(response.status_code,200)
        self.assertIn('Secure',response.headers['set-cookie'])
        self.assertIn('HttpOnly',response.headers['set-cookie'])
        self.assertIn('csrf',response.json())
        self.assertFalse(any('role_id=' in c.args[0] for c in conn.execute.call_args_list))
        self.assertTrue(any(c.args[0].startswith('DELETE FROM user_sessions') for c in conn.execute.call_args_list))

    def test_read_returns_only_current_players_barony(self):
        conn=MagicMock();conn.execute.return_value.fetchone.side_effect=[('player','player@example.invalid'),(7,'Барония','Барон','gerb_1.png','#b51f24')]
        conn.execute.return_value.fetchall.return_value=[({'Q':'0','R':'0','Плодородие':'0'},)]
        with patch('main.current_user',return_value=self.user),patch('player_cabinet.connect') as connect:
            connect.return_value.__enter__.return_value=conn
            response=self.client.get('/api/cabinet')
        self.assertEqual(response.status_code,200)
        call=next(c for c in conn.execute.call_args_list if c.args[0].startswith('SELECT data FROM hexes'))
        self.assertEqual(call.args[1],('2','7'))
        self.assertNotIn('user_pass',str(response.json()))

if __name__=='__main__':unittest.main()
