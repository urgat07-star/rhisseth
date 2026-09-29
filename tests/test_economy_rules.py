import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app/backend'))
from economy_rules import generated_food, grow_population, settle_federal_food


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


if __name__ == '__main__':
    unittest.main()
