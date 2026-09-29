import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app/backend'))
from fastapi.testclient import TestClient
from main import app


class AdminBuildingTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(app)
        self.player={'user_id':2,'user_login':'player','role_alias':'user','csrf':'test'}
        self.admin={'user_id':1,'user_login':'admin','role_alias':'admin','csrf':'test'}
        self.headers={'X-CSRF-Token':'test'}

    def test_player_cannot_open_building_administration(self):
        with patch('main.current_user',return_value=self.player):
            self.assertEqual(self.client.get('/admin/buildings').status_code,403)
            self.assertEqual(self.client.get('/api/admin/buildings').status_code,403)

    def test_catalogue_keeps_empty_unused_image_path(self):
        row=('port','Порт','Плодородие +1','Плодородие +2','Плодородие +3','','Берег',True)
        conn=MagicMock();conn.execute.return_value.fetchall.return_value=[row]
        with patch('admin_buildings.connect') as connect,patch('main.current_user',return_value=self.admin):
            connect.return_value.__enter__.return_value=conn
            response=self.client.get('/api/admin/buildings')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()[0]['image_path'],'')

    def test_edit_accepts_blank_image_path(self):
        conn=MagicMock();conn.execute.return_value.fetchone.return_value=('port',)
        payload={'name':'Порт','level_1_effect':'Плодородие +1','level_2_effect':'',
                 'level_3_effect':'','image_path':'','note':'Берег','active':True}
        with patch('admin_buildings.connect') as connect,patch('main.current_user',return_value=self.admin):
            connect.return_value.__enter__.return_value=conn
            response=self.client.patch('/api/admin/buildings/port',json=payload,headers=self.headers)
        self.assertEqual(response.status_code,200)


if __name__ == '__main__':
    unittest.main()
