import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app/backend'))
from economy_rules import generated_food, grow_population


class EconomyRuleTests(unittest.TestCase):
    def test_food_uses_level_population_and_fertility(self):
        self.assertEqual(generated_food(4, 80, 3, 40), 24)
        self.assertEqual(generated_food(1, 3, 2, 3), 2)

    def test_q7r14_food_examples_round_up(self):
        self.assertEqual(generated_food(1, 3, 3, 2), 5)   # 9 / 2 = 4.5
        self.assertEqual(generated_food(2, 15, 3, 12), 8)  # 90 / 12 = 7.5

    def test_empty_territory_does_not_generate_food(self):
        self.assertEqual(generated_food(5, 120, 4, 0), 0)

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
