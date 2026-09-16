import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app/backend'))
from import_csv import read_rows
from main import app
from fastapi.testclient import TestClient

class BaselineTests(unittest.TestCase):
    def test_source_coordinates(self):
        rows = read_rows(ROOT / 'data/import/hex-initial-parameters.csv')
        self.assertGreater(len(rows), 0)
        for row in rows:
            self.assertEqual(row['Q'], str(int(row['Q'])))
            self.assertEqual(row['R'], str(int(row['R'])))

    def test_interface_and_invalid_updates(self):
        client = TestClient(app)
        self.assertEqual(client.get('/').status_code, 200)
        self.assertEqual(client.get('/interactive-map/app.js').status_code, 200)
        self.assertEqual(client.get('/data/import/hex-initial-parameters.csv').status_code, 404)
        with patch('main.connect', side_effect=AssertionError('Invalid request reached DB')):
            for payload in [{'Q': '4'}, {'Защита': '99'}, {'Защита': '1.5'}, {'Комментарий': None}]:
                self.assertEqual(client.put('/api/hexes/0/0', json=payload).status_code, 400)
            self.assertEqual(client.put('/api/hexes/0/0', content='invalid').status_code, 400)
            self.assertEqual(client.put('/api/hexes/0/0', content='x' * 64001).status_code, 413)

if __name__ == '__main__':
    unittest.main()
