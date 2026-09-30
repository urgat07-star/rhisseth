"""Prepare and validate the Rhisseth economy v0.4.0 hex resource catalogue."""
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE = ROOT / "data/import/hex-initial-parameters.csv"
PLACEMENT = ROOT / "data/import/economy-v0.4.0-resource-placement.csv"
PARAMETERS = ROOT / "data/import/economy-v0.4.0-hex-parameters.csv"
MIGRATION = ROOT / "data/migrations/036_economy_v040_hex_resources.sql"

FOREST_TERRAINS = ("Редколесье", "Густой лес", "Тайга")
WOOD_RESOURCES = {"Дерево", "Корабельный лес", "Строевой лес"}
FORBIDDEN_WOOD_TERRAINS = ("Степь", "Холмы", "Горы", "Высокогорье")
COAST_RESOURCES = {"Рыба", "Моллюски", "Соль", "Водоросли", "Песок", "Камень", "Жемчуг", "Кораллы"}
LAND_RULES = {
    "Плодородное поле": (1, 0, 5, {"Пшеница", "Рожь", "Ячмень", "Вино"}),
    "Речная долина": (1, 1, 4, {"Рис", "Рыба", "Моллюски", "Вино", "Пряности"}),
    "Каменистая пустошь": (2, 1, 0, {"Камень"}),
    "Вулканическая земля": (3, 1, 0, {"Камень", "Самоцветы"}),
    "Высокогорье": (5, 4, 1, {"Железо", "Камень", "Мрамор", "Золото", "Серебро", "Самоцветы"}),
    "Полупустыня": (3, 0, 0, {"Песок", "Лошади"}),
    "Густой лес": (3, 2, 3, {"Дерево", "Корабельный лес"}),
    "Редколесье": (2, 1, 2, {"Дерево", "Корабельный лес"}),
    "Равнина": (1, 0, 2, {"Пшеница", "Рожь", "Ячмень", "Лён", "Лошади"}),
    "Степь": (1, 0, 2, {"Лошади", "Лён"}),
    "Тайга": (4, 3, 3, {"Дерево", "Корабельный лес"}),
    "Холмы": (2, 2, 2, {"Камень", "Уголь", "Железо"}),
    "Горы": (4, 3, 1, {"Камень", "Железо", "Мрамор"}),
    "Болото": (5, 3, 2, {"Железо"}),
    "Пустыня": (4, 0, 0, {"Песок"}),
    "Тундра": (2, 0, 2, {"Ягоды"}),
    "Луг": (1, 0, 2, {"Лошади", "Лён"}),
    "Озеро": (2, 0, 5, {"Рыба"}),
}
SEA_RULES = {
    "Мелководье": (2, 0, None, "0–10 м", 2, {"Рыба", "Моллюски", "Водоросли"}),
    "Шельф": (1, 0, None, "10–30 м", 3, {"Рыба", "Жемчуг"}),
    "Открытое море": (1, 0, None, "50–200 м", 4, {"Рыба", "Киты"}),
    "Глубоководье": (1, 0, None, "200 м", 5, set()),
    "Подводная впадина": (2, 0, None, "300 м–∞", 5, set()),
    "Рифы": (4, 0, None, "+2–5 м", 4, {"Рыба", "Кораллы", "Жемчуг"}),
    "Ледовые воды": (5, 0, None, "Любая", 4, {"Рыба", "Киты"}),
    "Штормовой район": (4, 0, None, "Любая", 5, set()),
    "Промысловая зона": (1, 0, None, "10–30 м", 3, {"Рыба", "Киты", "Моллюски"}),
}
COAST_RULES = {
    "Песчаный пляж": (2, 0, 2), "Песчаный берег": (2, 0, 2), "Галечный берег": (2, 0, 2),
    "Скалы": (4, 4, 2), "Бухта": (2, 2, 3), "Дельта реки": (1, 2, 4),
    "Прибрежное болото": (5, 3, 2), "Дюны": (4, 1, 0), "Фьорд": (3, 4, 1),
    "Островной берег": (2, 0, 2), "Побережье": (2, 0, None),
}


def is_forest(terrain):
    return any(name in terrain for name in FOREST_TERRAINS)


def land_kind(terrain):
    return next((name for name in LAND_RULES if name in terrain), "")


def sea_kind(terrain):
    return next((name for name in SEA_RULES if name in terrain), "")


def coast_kind(terrain):
    return next((name for name in COAST_RULES if name in terrain), "Побережье")


def resource_allowed(row):
    terrain, resource, category = row["Тип местности"], row["Основной ресурс"], row["Категория"]
    if resource in {"", "Нет"}:
        return True
    if is_forest(terrain):
        return resource in WOOD_RESOURCES
    if category == "Море":
        return resource in SEA_RULES[sea_kind(terrain)][5]
    allowed = set(LAND_RULES.get(land_kind(terrain), (0, 0, None, set()))[3])
    if category == "Побережье":
        allowed.update(COAST_RESOURCES)
    return resource in allowed


def replacement_for(row):
    terrain, category = row["Тип местности"], row["Категория"]
    if category == "Море":
        choices = tuple(sorted(SEA_RULES[sea_kind(terrain)][5])) or ("Нет",)
    else:
        choices = tuple(sorted(LAND_RULES.get(land_kind(terrain), (0, 0, None, set()))[3]))
        if category == "Побережье":
            choices += tuple(sorted(COAST_RESOURCES))
        choices = choices or ("Нет",)
    index = (int(row["Q"]) * 31 + int(row["R"]) * 17) % len(choices)
    return choices[index]


def expected_parameters(row):
    terrain, category = row["Тип местности"], row["Категория"]
    if category == "Море":
        movement, defense, fertility, depth, danger, _ = SEA_RULES[sea_kind(terrain)]
        return movement, defense, fertility, depth, danger
    kind = land_kind(terrain)
    movement, defense, fertility, _ = LAND_RULES[kind]
    danger = 1 if kind in {"Равнина", "Плодородное поле", "Луг", "Степь", "Речная долина"} else 2
    if category == "Побережье":
        coast_movement, coast_defense, coast_fertility = COAST_RULES[coast_kind(terrain)]
        movement, defense, danger = max(movement, coast_movement), max(defense, coast_defense), max(danger, 2)
        if coast_fertility is not None:
            fertility = coast_fertility
        return movement, defense, fertility, "0–10 м", danger
    return movement, defense, fertility, None, danger


def prepare(rows):
    changes = []
    for row in rows:
        terrain = row["Тип местности"]
        resource = row["Основной ресурс"]
        if row["Категория"] not in {"Суша", "Побережье", "Море"}:
            continue
        movement, defense, fertility, depth, danger = expected_parameters(row)
        row["Проходимость"] = str(movement)
        row["Защита"] = str(defense)
        row["Плодородие"] = "" if fertility is None else str(fertility)
        row["Глубина"] = "" if depth is None else str(depth)
        row["Опасность"] = str(danger)
        if row["Категория"] == "Суша":
            row["Течение"] = ""
        elif row["Течение"] not in {"1", "2", "3", "4", "5", "6"}:
            row["Течение"] = str((int(row["Q"]) * 31 + int(row["R"]) * 17) % 6 + 1)
        if "Дельта реки" in terrain:
            row["Дополнительный объект"] = "Река"
        if is_forest(terrain):
            richness = max(1, int(row["Богатство ресурса"] or 0))
            # The workbook marks ship timber as a scarce forest-only resource.
            # Dense forest with richness 4-5 is the reproducible v0.4.0 rule.
            replacement = "Корабельный лес" if "Густой лес" in terrain and richness >= 4 else "Дерево"
            row["Основной ресурс"] = replacement
            row["Богатство ресурса"] = str(richness)
        elif resource in WOOD_RESOURCES:
            row["Основной ресурс"] = "Нет"
            row["Богатство ресурса"] = "0"
        elif not resource_allowed(row):
            row["Основной ресурс"] = replacement_for(row)
            row["Богатство ресурса"] = str(max(1, int(row["Богатство ресурса"] or 0)))
        if (resource, row["Основной ресурс"]) != (row["Основной ресурс"], row["Основной ресурс"]):
            changes.append((row["ID"], resource, row["Основной ресурс"]))
    return changes


def validate(rows):
    errors = []
    for row in rows:
        terrain, resource = row["Тип местности"], row["Основной ресурс"]
        if row["Категория"] not in {"Суша", "Побережье", "Море"}:
            continue
        try:
            movement, defense, fertility, depth, danger = expected_parameters(row)
        except (KeyError, StopIteration):
            errors.append(f'{row["ID"]}: no rule for {row["Категория"]} / {terrain}')
            continue
        share = int(row["Доля суши, %"])
        expected_category = "Море" if share <= 5 else "Суша" if share >= 95 else "Побережье"
        if row["Категория"] != expected_category:
            errors.append(f'{row["ID"]}: category {row["Категория"]!r}, expected {expected_category!r} for share {share}')
        expected = {
            "Проходимость": str(movement), "Защита": str(defense),
            "Плодородие": "" if fertility is None else str(fertility),
            "Глубина": "" if depth is None else str(depth), "Опасность": str(danger),
        }
        for field, value in expected.items():
            if row[field] != value:
                errors.append(f'{row["ID"]}: {field}={row[field]!r}, expected {value!r}')
        if row["Категория"] == "Суша" and row["Течение"]:
            errors.append(f'{row["ID"]}: land hex has sea current')
        if row["Категория"] != "Суша" and row["Течение"] not in {"1", "2", "3", "4", "5", "6"}:
            errors.append(f'{row["ID"]}: invalid current direction')
        if is_forest(terrain) and resource not in {"Дерево", "Корабельный лес"}:
            errors.append(f'{row["ID"]}: forest has {resource!r}')
        if resource in WOOD_RESOURCES and not is_forest(terrain):
            errors.append(f'{row["ID"]}: wood is outside forest ({terrain})')
        if resource in WOOD_RESOURCES and any(name in terrain for name in FORBIDDEN_WOOD_TERRAINS):
            errors.append(f'{row["ID"]}: wood is on forbidden terrain ({terrain})')
        if not resource_allowed(row):
            errors.append(f'{row["ID"]}: {resource!r} is incompatible with {terrain!r}')
        richness = int(row["Богатство ресурса"] or 0)
        if not 0 <= richness <= 5:
            errors.append(f'{row["ID"]}: resource richness is outside 0-5')
        if resource == "Нет" and richness != 0:
            errors.append(f'{row["ID"]}: empty resource has non-zero richness')
        if resource != "Нет" and richness == 0:
            errors.append(f'{row["ID"]}: resource has zero richness')
    if errors:
        raise ValueError("\n".join(errors))


def write_catalogue(rows, fieldnames):
    with CATALOGUE.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter=";", quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)


def write_placement(rows):
    active = [row for row in rows if row["Категория"] in {"Суша", "Побережье", "Море"}]
    with PLACEMENT.open("w", encoding="utf-8-sig", newline="") as stream:
        fields = ["ID", "Q", "R", "Категория", "Тип местности", "Основной ресурс", "Богатство ресурса"]
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows({name: row[name] for name in fields} for row in active)

    with PARAMETERS.open("w", encoding="utf-8-sig", newline="") as stream:
        fields = ["ID", "Q", "R", "Категория", "Доля суши, %", "Тип местности",
                  "Дополнительный объект", "Проходимость", "Защита", "Плодородие",
                  "Опасность", "Основной ресурс", "Богатство ресурса", "Глубина", "Течение"]
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows({name: row[name] for name in fields} for row in active)


def write_migration(rows):
    patches = []
    for row in rows:
        terrain, resource = row["Тип местности"], row["Основной ресурс"]
        if row["Категория"] in {"Суша", "Побережье", "Море"}:
            patch = {key: row[key] for key in ("Тип местности", "Дополнительный объект", "Проходимость",
                     "Защита", "Плодородие", "Опасность", "Основной ресурс", "Богатство ресурса",
                     "Глубина", "Течение") if row[key] != ""}
            value = json.dumps(patch, ensure_ascii=False, separators=(",", ":")).replace("'", "''")
            patches.append(
                f"({int(row['Q'])},{int(row['R'])},'{value}'::jsonb)"
            )
    MIGRATION.write_text(
        "-- Economy v0.4.0: terrain rules and compatible resources; ownership is not changed.\n"
        "WITH parameter_patch(q,r,patch) AS (VALUES\n  "
        + ",\n  ".join(patches)
        + "\n)\nUPDATE hexes h SET data=(h.data - ARRAY['Дополнительный объект','Плодородие','Глубина','Течение']) || p.patch, updated_at=now()\n"
        "FROM parameter_patch p WHERE h.q=p.q AND h.r=p.r;\n",
        encoding="utf-8",
        newline="\n",
    )


def main():
    with CATALOGUE.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        fieldnames = reader.fieldnames
        rows = list(reader)
    changes = prepare(rows)
    validate(rows)
    write_catalogue(rows, fieldnames)
    write_placement(rows)
    write_migration(rows)
    forest = Counter(row["Основной ресурс"] for row in rows if is_forest(row["Тип местности"]))
    print(f"rows={len(rows)} changes={len(changes)} forest={dict(forest)}")


if __name__ == "__main__":
    main()
