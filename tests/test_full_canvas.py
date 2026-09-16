import sys
import math
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app/backend'))
from main import app
from fastapi.testclient import TestClient


class FullCanvasTests(unittest.TestCase):
    def test_canvas_samples_have_a_rendered_cell(self):
        width = math.sqrt(3) * 80
        cells = {(q, r) for r in range(math.ceil(2280 / 120))
                 for q in range(math.ceil(-0.5-r/2), math.floor(3200/width+0.5-r/2)+1)}
        for y in range(5, 2200, 10):
            for x in range(5, 3200, 10):
                r = y / 120
                q = x / width - r / 2
                s = -q-r
                rq, rr, rs = round(q), round(r), round(s)
                dq, dr, ds = abs(rq-q), abs(rr-r), abs(rs-s)
                if dq > dr and dq > ds:
                    rq = -rr-rs
                elif dr > ds:
                    rr = -rq-rs
                self.assertIn((rq, rr), cells)

    def test_missing_lower_left_cell_can_be_saved(self):
        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = ({'Q': '-9', 'R': '18', 'Комментарий': 'new'},)
        identity = {'user_id': 1, 'role_alias': 'moderator', 'csrf': 'test'}
        with patch('main.current_user', return_value=identity), patch('main.connect') as connect:
            connect.return_value.__enter__.return_value = connection
            response = TestClient(app).put('/api/hexes/-9/18', json={'Комментарий': 'new'}, headers={'X-CSRF-Token': 'test'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['row']['Q'], '-9')
        sql, values = connection.execute.call_args.args
        self.assertIn('ON CONFLICT', sql)
        self.assertEqual(values[2].obj, {'Q': '-9', 'R': '18', 'Комментарий': 'new'})
        self.assertEqual(values[3].obj, {'Комментарий': 'new'})

    def test_off_canvas_inserts_rejected_before_database(self):
        identity = {'user_id': 1, 'role_alias': 'admin', 'csrf': 'test'}
        with patch('main.current_user', return_value=identity), patch('main.connect', side_effect=AssertionError('Off-canvas insert')):
            for q, r in [(100, 0), (-1, 0), (0, -1), (0, 19), (-10, 18)]:
                response = TestClient(app).put(f'/api/hexes/{q}/{r}', json={}, headers={'X-CSRF-Token': 'test'})
                self.assertEqual(response.status_code, 404)
