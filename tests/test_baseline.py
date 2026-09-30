import sys
import unittest
import importlib.util
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app/backend'))
from import_csv import read_rows
from main import app
from fastapi.testclient import TestClient

economy_spec = importlib.util.spec_from_file_location('economy_v040', ROOT / 'scripts/prepare-economy-v040.py')
economy_v040 = importlib.util.module_from_spec(economy_spec)
economy_spec.loader.exec_module(economy_v040)

class BaselineTests(unittest.TestCase):
    def test_source_coordinates(self):
        rows = read_rows(ROOT / 'data/import/hex-initial-parameters.csv')
        self.assertGreater(len(rows), 0)
        for row in rows:
            self.assertEqual(row['Q'], str(int(row['Q'])))
            self.assertEqual(row['R'], str(int(row['R'])))
        visible={(q,r) for r in range(19) for q in range(__import__('math').ceil(-.5-r/2),__import__('math').floor(3200/(__import__('math').sqrt(3)*80)+.5-r/2)+1)}
        by_coord={(int(row['Q']),int(row['R'])):row for row in rows}
        self.assertTrue(all(by_coord[c]['Категория'] in ('Суша','Побережье','Море') for c in visible))
        self.assertTrue(all(field in rows[0] for field in ('Уровень гекса','Постройка','Дорога','Водная переправа','Объекты гекса')))
        self.assertEqual(by_coord[(-4,16)]['Категория'], 'Побережье')
        self.assertEqual(by_coord[(7,16)]['Категория'], 'Море')
        self.assertEqual(by_coord[(7,16)]['Тип местности'], 'Мелководье')
        self.assertEqual(by_coord[(7,16)]['Плодородие'], '')

    def test_v6_migration_preserves_ownership_fields(self):
        migration=(ROOT/'data/migrations/016_v6_hex_metadata.sql').read_text(encoding='utf-8')
        self.assertIn("data=(hexes.data - ARRAY[",migration)
        self.assertNotIn("'Тип владельца'",migration)
        self.assertNotIn("'Владелец'",migration)
        self.assertNotIn("'ID территории'",migration)

    def test_economy_v040_forest_resources(self):
        rows = read_rows(ROOT / 'data/import/hex-initial-parameters.csv')
        self.assertFalse(any(row['Основной ресурс']=='Скот' for row in rows))
        forests = ('Редколесье','Густой лес','Тайга')
        woods = {'Дерево','Корабельный лес'}
        forbidden = ('Степь','Холмы','Горы','Высокогорье')
        forest_rows = [row for row in rows if any(name in row['Тип местности'] for name in forests)]
        self.assertGreater(len(forest_rows), 0)
        self.assertTrue(all(row['Основной ресурс'] in woods for row in forest_rows))
        self.assertTrue(all(int(row['Богатство ресурса']) >= 1 for row in forest_rows))
        self.assertFalse(any(row['Основной ресурс'] in woods and
                             any(name in row['Тип местности'] for name in forbidden)
                             for row in rows))
        self.assertFalse(any(row['Основной ресурс'] in woods and
                             not any(name in row['Тип местности'] for name in forests)
                             for row in rows))
        economy_v040.validate(rows)
        for row in rows:
            if row['Категория'] not in ('Суша','Побережье','Море'):
                continue
            movement, defense, fertility, depth, danger = economy_v040.expected_parameters(row)
            self.assertEqual(row['Проходимость'], str(movement), row['ID'])
            self.assertEqual(row['Защита'], str(defense), row['ID'])
            self.assertEqual(row['Плодородие'], '' if fertility is None else str(fertility), row['ID'])
            self.assertEqual(row['Глубина'], '' if depth is None else str(depth), row['ID'])
            self.assertEqual(row['Опасность'], str(danger), row['ID'])
        migration=(ROOT/'data/migrations/036_economy_v040_hex_resources.sql').read_text(encoding='utf-8')
        self.assertNotIn('"Основной ресурс":"Скот"', migration)
        self.assertNotIn('Владелец', migration)
        self.assertNotIn('Тип владельца', migration)
        self.assertNotIn('Название баронии', migration)

    def test_interface_and_invalid_updates(self):
        client = TestClient(app)
        self.assertEqual(client.get('/',follow_redirects=False).headers['location'], '/index.php')
        self.assertEqual(client.get('/interactive-map/',follow_redirects=False).status_code, 303)
        with patch('main.current_user',return_value={'user_id':1,'role_alias':'admin','csrf':'test'}):
            self.assertEqual(client.get('/interactive-map/app.js').status_code, 200)
        self.assertEqual(client.get('/data/import/hex-initial-parameters.csv').status_code, 404)
        with patch('main.connect', side_effect=AssertionError('Invalid request reached DB')), patch('main.current_user',return_value={'user_id':1,'role_alias':'admin','csrf':'test'}):
            for payload in [{'Q': '4'}, {'Защита': '99'}, {'Защита': '1.5'}, {'Комментарий': None}]:
                self.assertEqual(client.put('/api/hexes/0/0', json=payload,headers={'X-CSRF-Token':'test'}).status_code, 400)
            self.assertEqual(client.put('/api/hexes/0/0', content='invalid',headers={'X-CSRF-Token':'test'}).status_code, 400)
            self.assertEqual(client.put('/api/hexes/0/0', content='x' * 64001,headers={'X-CSRF-Token':'test'}).status_code, 413)

    def test_finished_battle_selects_next_unused_general(self):
        script=(ROOT/'app/frontend/app.js').read_text(encoding='utf-8')
        self.assertIn("const nextGeneral=game.armies.find(general=>general.last_moved_turn!==currentGlobalTurn)",script)
        self.assertIn("if(nextGeneral)selectGeneral(nextGeneral.id)",script)

if __name__ == '__main__':
    unittest.main()
