import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import bcrypt
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / 'app/backend'))
from main import app
from import_users import load_archive, parse_dump
from site_auth import verify_password

class SiteAuthTests(unittest.TestCase):
    def test_login_opens_cabinet_for_every_role(self):
        client=TestClient(app)
        for role in ('user','moderator','admin'):
            session={'csrf':'test','user_id':10,'role_alias':role}
            with patch('site_auth.get_session',return_value=session):
                response=client.get('/index.php',follow_redirects=False)
            self.assertEqual(response.headers['location'],'/interactive-map/cabinet.html')
            conn=MagicMock();conn.execute.return_value.fetchone.return_value=(10,'synthetic-hash',role)
            with patch('site_auth.get_session',return_value={'csrf':'test'}),patch('site_auth.connect') as connect,patch('site_auth.verify_password',return_value=True),patch('site_auth.clear_session'),patch('site_auth.new_session',return_value=('a'*64,'new-csrf')):
                connect.return_value.__enter__.return_value=conn
                response=client.post('/index.php',data={'csrf':'test','login':'synthetic','password':'synthetic-password'},follow_redirects=False)
            self.assertEqual(response.status_code,303)
            self.assertEqual(response.headers['location'],'/interactive-map/cabinet.html')
            self.assertEqual(response.headers['cache-control'],'no-store')

    def test_php_hash_compatibility(self):
        stored = bcrypt.hashpw(b'synthetic-password',bcrypt.gensalt(rounds=4)).decode().replace('$2b$','$2y$',1)
        self.assertTrue(verify_password('synthetic-password',stored))
        self.assertFalse(verify_password('incorrect',stored))

    def test_archive_validation_without_executing_sql(self):
        archive = ROOT / 'temp/sql-bkp.zip'
        if archive.is_file():
            tables = load_archive(archive)
            self.assertEqual(len(tables['roles']),3)
            self.assertEqual(len(tables['users']),2)
            self.assertEqual({r['role_alias'] for r in tables['roles']},{'admin','moderator','user'})
        with self.assertRaises(ValueError):
            parse_dump("INSERT INTO `users` (`user_id`) VALUES (1);")

    def test_anonymous_and_viewer_access(self):
        client = TestClient(app)
        self.assertEqual(client.get('/api/hexes').status_code,401)
        self.assertEqual(client.get('/map/interactive-map/index.html',follow_redirects=False).headers['location'],'/interactive-map/')
        with patch('main.current_user',return_value={'user_id':10,'user_login':'synthetic','role_alias':'user','csrf':'test'}), patch('main.connect',side_effect=AssertionError('Forbidden update reached DB')):
            self.assertFalse(client.get('/api/me').json()['can_edit'])
            self.assertEqual(client.put('/api/hexes/0/0',json={'Комментарий':'blocked'},headers={'X-CSRF-Token':'test'}).status_code,403)
        with patch('main.current_user',return_value={'user_id':10,'user_login':'synthetic','role_alias':'admin','csrf':'test'}), patch('main.connect',side_effect=AssertionError('Missing CSRF reached DB')):
            self.assertEqual(client.put('/api/hexes/0/0',json={'Комментарий':'blocked'}).status_code,403)

if __name__ == '__main__':
    unittest.main()
