import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app/backend'))
from fastapi.testclient import TestClient
from main import app
from game_start import free_cells, candidates
from hex_rules import connected


class PlayerOnboardingTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.user = {'user_id': 2, 'user_login': 'player', 'role_alias': 'user', 'csrf': 'test'}
        self.payload = {'name': 'Барония', 'crest': 'gerb_1.png',
                        'color': '#b51f24', 'agreement': True, 'cells': [[0,0],[1,0],[2,0]]}

    def test_land_sea_island_and_occupied_filter(self):
        conn = MagicMock()
        conn.execute.return_value.__iter__.return_value = iter([
            (0,0,{'Категория':'Суша'}), (1,0,{'Категория':'Море'}),
            (2,0,{'Категория':'Море','Остров':'Да'}),
            (3,0,{'Категория':'Побережье','Тип владельца':'Игрок'}), (4,0,{}),
            (5,0,{'Категория':'Суша','Владелец':'3'}),
            (6,0,{'Категория':'Суша','ID территории':'7'}),
            (7,0,{'Категория':'Суша','Тип владельца':'Компьютерное владение'})])
        self.assertEqual(free_cells(conn), {(0,0),(2,0)})

    def test_reject_invalid_selection_and_missing_agreement_before_database(self):
        changes = [{'cells':[[0,0],[2,0]]}, {'cells':[[0,0],[0,0]]}, {'agreement':False},
                   {'crest':'../gerb_1.png'}, {'color':'red'}, {'name':' '},
                   {'cells':[[True,0],[1,0]]}, {'cells':[[0,0]]}]
        with patch('main.current_user',return_value=self.user), patch('game_start.connect',side_effect=AssertionError('Invalid request reached database')):
            for change in changes:
                with self.subTest(change=change):
                    response = self.client.post('/api/start',json={**self.payload,**change},headers={'X-CSRF-Token':'test'})
                    self.assertEqual(response.status_code,400)

    def test_connected_chain_not_in_suggested_options_can_be_saved(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.side_effect = [None, (7,)]
        with patch('main.current_user',return_value=self.user), patch('game_start.connect') as connect, \
             patch('game_start.candidates',return_value=[((0,0),(1,0))]), \
             patch('game_start.free_cells',return_value={(0,0),(1,0),(2,0)}):
            connect.return_value.__enter__.return_value = conn
            response = self.client.post('/api/start',json=self.payload,headers={'X-CSRF-Token':'test'})
        self.assertEqual(response.status_code,200)
        updates = [call.args[1][0].obj for call in conn.execute.call_args_list if call.args[0].startswith('UPDATE hexes')]
        self.assertEqual(len(updates),3)
        self.assertNotIn('Название территории',updates[0])
        self.assertEqual(updates[0]['Название баронии'],'Барония')
        self.assertEqual(updates[0]['Цвет баронии'],'#b51f24')

    def test_occupied_or_sea_selection_is_rejected_atomically(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.side_effect = [None]
        with patch('main.current_user',return_value=self.user), patch('game_start.connect') as connect, \
             patch('game_start.candidates',return_value=[((0,0),(1,0))]), \
             patch('game_start.free_cells',return_value={(0,0),(1,0)}):
            connect.return_value.__enter__.return_value = conn
            response = self.client.post('/api/start',json=self.payload,headers={'X-CSRF-Token':'test'})
        self.assertEqual(response.status_code,409)
        self.assertFalse(any(c.args[0].startswith(('INSERT','UPDATE')) for c in conn.execute.call_args_list))

    def test_random_candidates_include_pairs_and_triples_only_on_free_land(self):
        free={(0,0),(1,0),(2,0),(4,0)}
        with patch('game_start.free_cells',return_value=free):
            choices=candidates(MagicMock())
        self.assertEqual({len(c) for c in choices},{2,3})
        self.assertIn(((0,0),(1,0),(2,0)),choices)
        self.assertTrue(all(connected(c) and set(c)<=free for c in choices))
        self.assertTrue(all((4,0) not in c for c in choices))

    def test_random_preview_refreshes_free_land_and_does_not_allocate(self):
        conn=MagicMock()
        conn.execute.return_value.fetchone.return_value=None
        with patch('main.current_user',return_value=self.user), patch('game_start.connect') as connect, \
             patch('game_start.free_cells',return_value={(0,0),(1,0),(2,0)}), \
             patch('game_start.secrets.choice',side_effect=lambda choices:choices[-1]):
            connect.return_value.__enter__.return_value=conn
            response=self.client.get('/api/start/options?random=true')
        self.assertEqual(response.status_code,200)
        cells=response.json()['random_cells']
        self.assertIn(len(cells),(2,3))
        self.assertTrue(connected([tuple(c) for c in cells]))
        self.assertFalse(any(c.args[0].startswith(('INSERT','UPDATE')) for c in conn.execute.call_args_list))

    def test_registration_creates_session_and_redirects_to_cabinet(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.side_effect = [(3,), (2,)]
        with patch('site_auth.get_session',return_value={'csrf':'test'}), patch('site_auth.connect') as connect, \
             patch('site_auth.clear_session'), patch('site_auth.new_session',return_value=('a'*64,'csrf')):
            connect.return_value.__enter__.return_value = conn
            response = self.client.post('/register.php',data={'csrf':'test','login':'new-player',
                'email':'synthetic@example.org','password':'synthetic-password','password_confirm':'synthetic-password'},follow_redirects=False)
        self.assertEqual(response.status_code,303)
        self.assertEqual(response.headers['location'],'/interactive-map/cabinet.html')
        self.assertIn('rhisseth_session=',response.headers['set-cookie'])

    def test_private_pages_require_login(self):
        for path in ('/interactive-map/create-barony.html','/interactive-map/cabinet.html'):
            response = self.client.get(path,follow_redirects=False)
            self.assertEqual(response.status_code,303)


if __name__ == '__main__':
    unittest.main()
