# Release review 2026-09-18 (0.0.2): Regression checks for hex metadata.
# Details: docs/releases/0.0.2-changes-2026-09-18.md.
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app/backend'))
from fastapi.testclient import TestClient
from main import app
from hex_rules import coordinates, connected, category_from_share

class HexMetadataTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(app)
        self.admin={'user_id':1,'user_login':'admin','role_alias':'admin','csrf':'test'}
        self.player={**self.admin,'user_id':2,'role_alias':'user'}
        self.headers={'X-CSRF-Token':'test'}

    def test_categories_and_connectivity(self):
        self.assertEqual(len(coordinates()),465)
        self.assertEqual([category_from_share(v) for v in ('0','0.5','100')],['Море','Побережье','Суша'])
        self.assertTrue(connected([(0,0),(1,0),(0,1)]))
        self.assertFalse(connected([(0,0),(2,2)]))

    def test_admin_interface_is_restricted_on_server(self):
        with patch('main.current_user',return_value=self.player),patch('main.connect',side_effect=AssertionError('Forbidden read')):
            for url in ('/admin/hexes','/api/admin/owners','/api/admin/hexes/export'):
                self.assertEqual(self.client.get(url).status_code,403)

    def test_invalid_categories_water_and_landscape_rejected(self):
        invalid=[{'Категория':'Вне полотна'},{'Пресная вода':'1'}, {'Доля суши, %':'NaN'},
                 {'Доля суши, %':'50','Категория':'Море'},
                 {'Состав ландшафта':'[{"name":"Лес","percent":70}]'},
                 {'Состав ландшафта':'[{"name":"Лес","percent":true}]'},
                 {'Тип владельца':'Игрок'}, {'Владелец':'2'}, {'Название территории':'x'*201}]
        with patch('main.current_user',return_value=self.admin),patch('main.connect',side_effect=AssertionError('Invalid update')):
            for data in invalid:
                with self.subTest(data=data):
                    self.assertEqual(self.client.put('/api/hexes/0/0',json=data,headers=self.headers).status_code,400)

    def test_player_can_only_rename_owned_territory(self):
        conn=MagicMock()
        for owner,expected in (('2',200),('3',403)):
            conn.execute.return_value.fetchone.return_value=({'Q':'0','R':'0','Тип владельца':'Игрок','Владелец':owner},)
            with patch('main.current_user',return_value=self.player),patch('main.connect') as connect:
                connect.return_value.__enter__.return_value=conn
                response=self.client.patch('/api/hexes/0/0/territory-name',json={'Название территории':'Барония'},headers=self.headers)
                self.assertEqual(response.status_code,expected)
        with patch('main.current_user',return_value=self.player),patch('main.connect',side_effect=AssertionError('Geographic rename forbidden')):
            self.assertEqual(self.client.put('/api/hexes/0/0',json={'Название':'Горы'},headers=self.headers).status_code,403)

    def test_territory_rename_cannot_smuggle_characteristics(self):
        with patch('main.current_user',return_value=self.player),patch('main.connect',side_effect=AssertionError('Invalid body')):
            self.assertEqual(self.client.patch('/api/hexes/0/0/territory-name',json={'Название территории':'x','Категория':'Суша'},headers=self.headers).status_code,400)
            self.assertEqual(self.client.patch('/api/hexes/0/0/territory-name',json={'Название территории':'x'}).status_code,403)

    def test_disconnected_ai_territory_rejected(self):
        with patch('main.current_user',return_value=self.admin),patch('main.connect',side_effect=AssertionError('Invalid territory')):
            for cells in ([[0,0]],[[0,0],[3,3]],[[0,0],[0,0]]):
                response=self.client.post('/api/admin/territories',json={'name':'Княжество','cells':cells},headers=self.headers)
                self.assertEqual(response.status_code,400)

    def test_start_requires_csrf_and_rejects_repeat(self):
        conn=MagicMock();conn.execute.return_value.fetchone.return_value=(1,)
        with patch('main.current_user',return_value=self.player),patch('game_start.connect') as connect:
            connect.return_value.__enter__.return_value=conn
            self.assertEqual(self.client.post('/api/start',json={'name':'Барония','crest':'gerb_1.webp','color':'#b51f24','agreement':True},headers=self.headers).status_code,409)
            self.assertEqual(self.client.post('/api/start',json={}).status_code,403)

    def test_landscape_and_names_are_independent(self):
        conn=MagicMock();conn.execute.return_value.fetchone.side_effect=[None,({'Q':'0','R':'0','Название':'Горы'},)]
        with patch('main.current_user',return_value=self.admin),patch('main.connect') as connect:
            connect.return_value.__enter__.return_value=conn
            response=self.client.put('/api/hexes/0/0',json={'Название':'Горы','Состав ландшафта':'[{"name":"Лес","percent":70},{"name":"Река","percent":30}]'},headers=self.headers)
            self.assertEqual(response.status_code,200)
            payload=conn.execute.call_args.args[1][3].obj
            self.assertEqual(payload['Тип местности'],'Лес / Река')
            self.assertEqual(payload['Название'],'Горы')

if __name__=='__main__':unittest.main()
