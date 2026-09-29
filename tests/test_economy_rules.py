import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app/backend'))
from economy_rules import generated_food, grow_population, settle_federal_food
from game_clock import _annual_resource_income


class EconomyRuleTests(unittest.TestCase):
    def test_food_is_fertility_times_population_minus_population(self):
        self.assertEqual(generated_food(3, 2), 4)
        self.assertEqual(generated_food(0, 2), -2)

    def test_empty_territory_does_not_generate_food(self):
        self.assertEqual(generated_food(4, 0), 0)

    def test_neutral_mountain_has_fixed_food(self):
        self.assertEqual(generated_food(0, 1, mountain=True, neutral=True), 3)
        self.assertEqual(generated_food(0, 1, mountain=True, neutral=False), -1)

    def test_federal_shortage_reduces_population(self):
        self.assertEqual(settle_federal_food(-5, 2, 4),
                         {'federal_food': 0, 'population': 1, 'famine_loss': 3})
        self.assertEqual(settle_federal_food(-8, 0, 3)['population'], 0)

    def test_population_grows_after_food_and_stops_at_level_limit(self):
        class FixedRandom:
            def randint(self, low, high):
                self.range = (low, high)
                return high
        rng = FixedRandom()
        self.assertEqual(grow_population(75, 80, 1, 12, rng), 80)
        self.assertEqual(rng.range, (1, 12))

    def test_annual_resources_merge_food_and_credit_other_stock(self):
        class Result:
            def __init__(self,one=None,many=None):self.one=one;self.many=many or []
            def fetchone(self):return self.one
            def fetchall(self):return self.many
        class Connection:
            def __init__(self):self.calls=[]
            def execute(self,sql,args=None):
                self.calls.append((sql,args))
                if 'to_regclass' in sql:return Result(('game_economy_years',))
                if 'INSERT INTO game_economy_years' in sql:return Result((0,))
                if 'SELECT code,name,is_food FROM game_resources' in sql:
                    return Result(many=[('wood','Дерево',False),('wheat','Пшеница',True)])
                if "SELECT (data->>'Владелец')::integer" in sql:
                    return Result(many=[(2,{'Основной ресурс':'Дерево','Богатство ресурса':'3'}),
                                        (2,{'Основной ресурс':'Пшеница','Богатство ресурса':'4'})])
                return Result()
        conn=Connection();_annual_resource_income(conn,0)
        credits=[args for sql,args in conn.calls if sql.startswith('INSERT INTO game_inventory')]
        self.assertIn((2,'wood',3),credits)
        self.assertIn((2,'food',4),credits)


if __name__ == '__main__':
    unittest.main()
