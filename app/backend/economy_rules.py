"""Pure economy v0.4.0 formulas."""
import math


def generated_food(province_level, population_limit, fertility, current_population):
    """Calculate food at the end of the autumn turn from maximum and current population."""
    level = max(1, int(province_level))
    maximum = max(0, int(population_limit))
    people = max(0, int(current_population))
    soil = max(0, int(fertility))
    if people == 0:
        return 0
    return math.ceil(level * maximum * soil / people)


def grow_population(current_population, population_limit, growth_min, growth_max, rng):
    """Apply random annual growth after the autumn food calculation, capped by the level limit."""
    current = max(0, int(current_population))
    limit = max(0, int(population_limit))
    low, high = int(growth_min), int(growth_max)
    if low < 0 or high < low:
        raise ValueError('Некорректный диапазон прироста населения')
    return min(limit, current + rng.randint(low, high))
