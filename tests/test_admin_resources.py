import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app/backend'))
from fastapi.testclient import TestClient
from main import app


class AdminResourceTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(app)
        self.player={'user_id':2,'user_login':'player','role_alias':'user','csrf':'test'}
        self.admin={'user_id':1,'user_login':'admin','role_alias':'admin','csrf':'test'}
        self.headers={'X-CSRF-Token':'test'}

    def connection(self,conn):
        context=patch('admin_resources.connect')
        mocked=context.start();self.addCleanup(context.stop)
        mocked.return_value.__enter__.return_value=conn

    def test_player_cannot_open_resource_administration(self):
        with patch('main.current_user',return_value=self.player),patch('admin_resources.connect',side_effect=AssertionError('No DB')):
            self.assertEqual(self.client.get('/admin/resources').status_code,403)
            self.assertEqual(self.client.get('/api/admin/resources').status_code,403)

    def test_catalogues_are_returned_separately(self):
        result=MagicMock();result.fetchall.side_effect=[[('wood','Дерево','Лес','Строительство',True)],[('steel','Сталь','Железо + уголь','','Найм',True)]]
        conn=MagicMock();conn.execute.return_value=result;self.connection(conn)
        with patch('main.current_user',return_value=self.admin):
            response=self.client.get('/api/admin/resources')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['extractable'][0]['name'],'Дерево')
        self.assertEqual(response.json()['produced'][0]['name'],'Сталь')

    def test_create_and_edit_validate_complete_payload(self):
        conn=MagicMock();conn.execute.return_value.fetchone.return_value=('steel',);self.connection(conn)
        with patch('main.current_user',return_value=self.admin):
            bad=self.client.post('/api/admin/resources/produced',json={'code':'Steel'},headers=self.headers)
            good=self.client.patch('/api/admin/resources/produced/steel',json={
                'name':'Сталь','ingredients':'Железо + уголь','required_building':'Кузница',
                'purpose':'Найм','active':True},headers=self.headers)
        self.assertEqual(bad.status_code,400)
        self.assertEqual(good.status_code,200)


if __name__ == '__main__':
    unittest.main()
