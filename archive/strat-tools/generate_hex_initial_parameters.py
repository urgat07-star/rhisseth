#!/usr/bin/env python3
"""Build a reproducible initial hex catalogue from the temporary SVG map."""

from __future__ import annotations

import csv
import hashlib
import math
import re
import urllib.request
from collections import deque
from pathlib import Path

from shapely import contains_xy
from shapely.geometry import Polygon
from shapely.ops import unary_union
from svg.path import Close, Move, parse_path


MAP_URL = "http://strat.elvizzz.ru/"
OUT_DIR = Path(__file__).resolve().parent
RADIUS = 80
WIDTH = math.sqrt(3) * RADIUS
HEIGHT = 2 * RADIUS
MIN_Q, MAX_Q = -2, 26
MIN_R, MAX_R = -2, 20
CANVAS_W, CANVAS_H = 3200, 2200
DIRECTIONS = ((1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1))


def stable_number(q: int, r: int, salt: str, modulo: int = 10000) -> int:
    raw = hashlib.sha256(f"strat-elvizzz-v1:{salt}:{q}:{r}".encode()).digest()
    return int.from_bytes(raw[:4], "big") % modulo


def fetch_land_geometry():
    request = urllib.request.Request(MAP_URL, headers={"User-Agent": "Strat.elvizzz-map-catalogue/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8")
    path_data = re.findall(r'<path\s+[^>]*d="([^"]+)"[^>]*fill="#D9D9D9"', html)
    if not path_data:
        raise RuntimeError("Light land contours were not found in the SVG map")
    polygons = []
    for data in path_data:
        parsed = parse_path(data)
        points: list[tuple[float, float]] = []
        for segment in parsed:
            if isinstance(segment, Move):
                if len(points) >= 3:
                    polygons.append(Polygon(points).buffer(0))
                points = [(segment.end.real, segment.end.imag)]
                continue
            # Flatten curves to short chords; straight segments need only their end.
            steps = max(1, min(40, math.ceil(segment.length(error=1e-3) / 8)))
            points.extend((segment.point(i / steps).real, segment.point(i / steps).imag) for i in range(1, steps + 1))
            if isinstance(segment, Close) and len(points) >= 3:
                polygons.append(Polygon(points).buffer(0))
                points = []
        if len(points) >= 3:
            polygons.append(Polygon(points).buffer(0))
    return unary_union([polygon for polygon in polygons if not polygon.is_empty])


def hex_center(q: int, r: int) -> tuple[float, float]:
    return WIDTH * (q + r / 2), HEIGHT * 3 / 4 * r


def land_share(geometry, q: int, r: int) -> tuple[float | None, int]:
    cx, cy = hex_center(q, r)
    land = total = 0
    # Sampling step 4 gives about 1,000 samples per full hex and stable coast ratios.
    for y in range(math.floor(cy - RADIUS), math.ceil(cy + RADIUS) + 1, 4):
        if not 0 <= y < CANVAS_H:
            continue
        dy = abs(y - cy)
        half_width = WIDTH / 2 if dy <= RADIUS / 2 else WIDTH * (RADIUS - dy) / RADIUS
        if half_width < 0:
            continue
        for x in range(math.floor(cx - half_width), math.ceil(cx + half_width) + 1, 4):
            if not 0 <= x < CANVAS_W:
                continue
            total += 1
            if contains_xy(geometry, x, y):
                land += 1
    return ((land / total) if total else None), total


def smooth_noise(q: int, r: int, salt: str) -> float:
    values = [stable_number(q, r, salt)]
    values.extend(stable_number(q + dq, r + dr, salt) for dq, dr in DIRECTIONS)
    return sum(values) / len(values) / 9999


def land_terrain(q: int, r: int) -> str:
    elevation = 0.65 * smooth_noise(q, r, "elevation") + 0.35 * smooth_noise(q // 2, r // 2, "massif")
    moisture = 0.65 * smooth_noise(q, r, "moisture") + 0.35 * smooth_noise(q // 2, r // 2, "watershed")
    latitude = r / max(1, MAX_R)
    if elevation > 0.70:
        return "Высокогорье" if elevation > 0.82 else "Горы"
    if elevation > 0.59:
        return "Холмы"
    if moisture > 0.72:
        return "Болото"
    if latitude < 0.10:
        return "Тундра"
    if moisture > 0.57:
        return "Густой лес"
    if moisture > 0.47:
        return "Редколесье"
    if moisture < 0.30:
        return "Полупустыня"
    return "Луг" if stable_number(q, r, "open-land", 2) else "Равнина"


LAND_RULES = {
    "Высокогорье": (5, 4, 0, 4, ["Железо", "Серебро", "Редкие металлы", "Камень"]),
    "Горы": (5, 4, 0, 3, ["Железо", "Медь", "Камень", "Уголь"]),
    "Холмы": (2, 2, 2, 2, ["Камень", "Уголь", "Железо", "Овцы"]),
    "Болото": (5, 3, 1, 4, ["Торф", "Лекарственные травы", "Рыба", "Тростник"]),
    "Тундра": (4, 1, 0, 3, ["Олени", "Меха", "Торф", "Рыба"]),
    "Густой лес": (3, 3, 2, 2, ["Древесина", "Дичь", "Смола", "Мёд"]),
    "Редколесье": (2, 1, 3, 1, ["Древесина", "Дичь", "Мёд", "Лён"]),
    "Полупустыня": (3, 0, 1, 3, ["Соль", "Медь", "Овцы", "Глина"]),
    "Луг": (1, 0, 4, 1, ["Скот", "Лошади", "Лён", "Лекарственные травы"]),
    "Равнина": (1, 0, 3, 1, ["Пшеница", "Рожь", "Лён", "Лошади"]),
}


def main() -> None:
    image = fetch_land_geometry()
    rows: list[dict[str, object]] = []
    by_coord: dict[tuple[int, int], dict[str, object]] = {}
    for r in range(MIN_R, MAX_R + 1):
        for q in range(MIN_Q, MAX_Q + 1):
            share, samples = land_share(image, q, r)
            if share is None:
                category = "Вне полотна"
            elif share <= 0.05:
                category = "Море"
            elif share >= 0.95:
                category = "Суша"
            else:
                category = "Побережье"
            # The small but clearly visible island in Q15,R2 occupies about 4%
            # of the cell. Keep it as a coastal/island hex despite the general
            # 5% noise threshold used for other contours.
            if (q, r) == (15, 2):
                category = "Побережье"
            row = {"q": q, "r": r, "share": share, "samples": samples, "category": category}
            rows.append(row)
            by_coord[(q, r)] = row

    # Distance to land/coast controls initial sea depth.
    distance: dict[tuple[int, int], int] = {}
    queue: deque[tuple[int, int]] = deque()
    for row in rows:
        if row["category"] in {"Суша", "Побережье"}:
            coord = (int(row["q"]), int(row["r"]))
            distance[coord] = 0
            queue.append(coord)
    while queue:
        q, r = queue.popleft()
        for dq, dr in DIRECTIONS:
            coord = (q + dq, r + dr)
            if coord in by_coord and coord not in distance:
                distance[coord] = distance[(q, r)] + 1
                queue.append(coord)

    output: list[dict[str, object]] = []
    for source in rows:
        q, r = int(source["q"]), int(source["r"])
        category = str(source["category"])
        share = source["share"]
        record: dict[str, object] = {
            "ID": f"Q{q:+03d}-R{r:+03d}", "Q": q, "R": r,
            "Категория": category,
            "Доля суши, %": "" if share is None else round(float(share) * 100),
            "Тип местности": "", "Проходимость": "", "Защита": "",
            "Плодородие": "", "Пресная вода": "", "Опасность": "",
            "Основной ресурс": "", "Богатство ресурса": "",
            "Глубина": "", "Течение": "", "Комментарий": "",
        }
        if category == "Вне полотна":
            record["Комментарий"] = "Гекс сгенерирован сеткой, но не попадает в SVG-полотно 3200×2200"
        elif category == "Море":
            dist = distance.get((q, r), 5)
            terrain = "Мелководье" if dist <= 1 else "Шельф" if dist == 2 else "Открытое море" if dist <= 4 else "Глубоководье"
            depth = {"Мелководье": 1, "Шельф": 2, "Открытое море": 3, "Глубоководье": 4}[terrain]
            resources = ["Рыба", "Моллюски", "Водоросли"] if depth <= 2 else ["Рыба", "Киты", "Нет"]
            resource = resources[stable_number(q, r, "sea-resource", len(resources))]
            record.update({
                "Тип местности": terrain, "Проходимость": 2 if terrain == "Мелководье" else 1,
                "Защита": 0, "Опасность": min(5, 1 + depth + stable_number(q, r, "waves", 2)),
                "Основной ресурс": resource,
                "Богатство ресурса": 0 if resource == "Нет" else 1 + stable_number(q, r, "sea-richness", 5),
                "Глубина": depth, "Течение": 1 + stable_number(q, r, "current", 6),
            })
        else:
            terrain = land_terrain(q, r)
            movement, defense, fertility, danger, resources = LAND_RULES[terrain]
            if category == "Побережье":
                coast_types = ["Песчаный берег", "Галечный берег", "Бухта", "Скалистый берег", "Дельта реки"]
                coast = coast_types[stable_number(q, r, "coast", len(coast_types))]
                resource_pool = ["Рыба", "Моллюски", "Соль"] + resources
                record["Тип местности"] = f"{coast} / {terrain}"
                movement = max(2, movement)
                danger = max(2, danger)
            else:
                resource_pool = resources
                record["Тип местности"] = terrain
            resource = resource_pool[stable_number(q, r, "land-resource", len(resource_pool))]
            has_resource = stable_number(q, r, "resource-presence", 100) < 72
            record.update({
                "Проходимость": movement, "Защита": defense, "Плодородие": fertility,
                "Пресная вода": min(5, max(0, round(5 * smooth_noise(q, r, "water")))),
                "Опасность": danger, "Основной ресурс": resource if has_resource else "Нет",
                "Богатство ресурса": 1 + stable_number(q, r, "land-richness", 5) if has_resource else 0,
                "Глубина": 1 if category == "Побережье" else "",
                "Течение": 1 + stable_number(q, r, "current", 6) if category == "Побережье" else "",
            })
            if (q, r) == (15, 2):
                record.update({
                    "Тип местности": "Островной берег / Луг",
                    "Проходимость": 2, "Защита": 1, "Плодородие": 2,
                    "Пресная вода": 1, "Опасность": 2,
                    "Основной ресурс": "Моллюски", "Богатство ресурса": 5,
                    "Глубина": 1, "Комментарий": "Малый остров; подтверждено ручной проверкой карты",
                })
        output.append(record)

    fields = list(output[0])
    csv_path = OUT_DIR / "hex-initial-parameters.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";")
        writer.writeheader()
        writer.writerows(output)

    counts = {name: sum(row["Категория"] == name for row in output) for name in ("Море", "Побережье", "Суша", "Вне полотна")}
    md_path = OUT_DIR / "hex-initial-parameters-review.md"
    with md_path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write("# Начальные параметры гексов — версия для рассмотрения\n\n")
        stream.write(f"Источник карты: <{MAP_URL}>. Дата формирования: 2026-09-15.\n\n")
        stream.write("## Сводка\n\n")
        stream.write("| Всего координат | Море | Побережье | Суша | Вне полотна |\n|---:|---:|---:|---:|---:|\n")
        stream.write(f"| {len(output)} | {counts['Море']} | {counts['Побережье']} | {counts['Суша']} | {counts['Вне полотна']} |\n\n")
        stream.write("Побережьем считается гекс, в котором доля суши составляет от 6 до 94 %. Классификация выполнена по площади светлого контура внутри гекса, а не только по цвету центральной точки. Значения являются стартовым предложением и не считаются утверждённым балансом.\n\n")
        stream.write("Полная редактируемая таблица находится в `hex-initial-parameters.csv`.\n\n")
        stream.write("## Полная таблица\n\n")
        selected = ["ID", "Q", "R", "Категория", "Доля суши, %", "Тип местности", "Проходимость", "Защита", "Плодородие", "Пресная вода", "Опасность", "Основной ресурс", "Богатство ресурса", "Глубина", "Течение"]
        stream.write("| " + " | ".join(selected) + " |\n")
        stream.write("|" + "|".join(["---"] * len(selected)) + "|\n")
        for row in output:
            stream.write("| " + " | ".join(str(row[key]) for key in selected) + " |\n")

    print(f"Generated {len(output)} rows: {counts}")
    print(csv_path)
    print(md_path)


if __name__ == "__main__":
    main()
