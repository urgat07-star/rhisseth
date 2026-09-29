"""Pure economy v0.4.0 formulas."""


def generated_food(fertility, current_population, *, mountain=False, neutral=False):
    """Annual food delta; neutral mountains receive a fixed subsistence supply."""
    people = max(0, int(current_population))
    soil = max(0, int(fertility))
    if mountain and neutral:
        return 3
    return soil * people - people


def settle_federal_food(food_delta, federal_food, current_population, extra_consumption=0):
    """Apply production/consumption to the federal stock; uncovered deficit causes famine."""
    net = int(food_delta) - max(0, int(extra_consumption))
    stock = max(0, int(federal_food))
    people = max(0, int(current_population))
    if net >= 0:
        return {'federal_food': stock + net, 'population': people, 'famine_loss': 0}
    shortage = max(0, -net - stock)
    return {'federal_food': max(0, stock + net),
            'population': max(0, people - shortage),
            'famine_loss': min(people, shortage)}


def grow_population(current_population, population_limit, growth_min, growth_max, rng):
    """Apply random annual growth after the autumn food calculation, capped by the level limit."""
    current = max(0, int(current_population))
    limit = max(0, int(population_limit))
    low, high = int(growth_min), int(growth_max)
    if low < 0 or high < low:
        raise ValueError('Некорректный диапазон прироста населения')
    return min(limit, current + rng.randint(low, high))
