#!/usr/bin/env python3
"""Generate the textured, smoothly blended SVG prototype proposed in section 8."""

from __future__ import annotations

import csv
import html
from pathlib import Path

from generate_hex_visualization import (
    CSV_PATH,
    LAND_COLORS,
    MAP_URL,
    ROOT,
    SEA_COLORS,
    fetch_land_paths,
    land_type,
    polygon_points,
)


OUTPUT_PATH = ROOT / "hex-terrain-textured-prototype.svg"

TEXTURE_GROUPS = {
    "plains": {"Равнина", "Луг", "Редколесье", "Тундра", "Полупустыня"},
    "forest": {"Густой лес", "Редколесье"},
    "swamp": {"Болото"},
    "hills": {"Холмы"},
    "mountains": {"Горы", "Высокогорье"},
}


def polygons_for(rows: list[dict[str, str]], terrain_names: set[str]) -> list[str]:
    result = []
    for row in rows:
        if row["Категория"] in {"Суша", "Побережье"} and land_type(row["Тип местности"]) in terrain_names:
            result.append(f'<polygon points="{polygon_points(int(row["Q"]), int(row["R"]))}" fill="white"/>')
    return result


def generate(rows: list[dict[str, str]], land_paths: list[str]) -> None:
    out: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1100" viewBox="0 0 3200 2200" role="img" aria-labelledby="title description">',
        '<title id="title">Текстурированный прототип карты Strat.elvizzz</title>',
        '<desc id="description">Плавная гипсометрическая и батиметрическая карта с текстурами природных зон и игровой гекс-сеткой.</desc>',
        '<defs>',
        '<clipPath id="land-clip">',
    ]
    for path in land_paths:
        out.append(f'<path d="{html.escape(path, quote=True)}"/>')
    out.extend([
        '</clipPath>',
        '<mask id="sea-mask" maskUnits="userSpaceOnUse" x="0" y="0" width="3200" height="2200">',
        '<rect width="3200" height="2200" fill="white"/>',
    ])
    for path in land_paths:
        out.append(f'<path d="{html.escape(path, quote=True)}" fill="black"/>')
    out.extend([
        '</mask>',
        '<filter id="sea-surface" x="-5%" y="-5%" width="110%" height="110%">',
        '<feGaussianBlur in="SourceGraphic" stdDeviation="24" result="smooth"/>',
        '<feTurbulence type="fractalNoise" baseFrequency="0.006 0.025" numOctaves="3" seed="27" result="waves"/>',
        '<feColorMatrix in="waves" values="1 0 0 0 0  0 1 0 0 0.05  0 0 1 0 0.12  0 0 0 0.23 0" result="soft-waves"/>',
        '<feBlend in="smooth" in2="soft-waves" mode="soft-light"/>',
        '</filter>',
        '<filter id="land-surface" x="-5%" y="-5%" width="110%" height="110%">',
        '<feGaussianBlur in="SourceGraphic" stdDeviation="22" result="smooth"/>',
        '<feTurbulence type="fractalNoise" baseFrequency="0.018" numOctaves="4" seed="41" result="grain"/>',
        '<feColorMatrix in="grain" values="0.8 0 0 0 0.1  0 0.75 0 0 0.08  0 0 0.6 0 0.04  0 0 0 0.18 0" result="earth-grain"/>',
        '<feBlend in="smooth" in2="earth-grain" mode="soft-light"/>',
        '</filter>',
        '<filter id="soft-mask" x="-5%" y="-5%" width="110%" height="110%"><feGaussianBlur stdDeviation="18"/></filter>',
        '<filter id="legend-shadow" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="5" stdDeviation="8" flood-opacity="0.35"/></filter>',
        '<pattern id="plain-pattern" width="34" height="34" patternUnits="userSpaceOnUse"><path d="M3 27 Q12 19 22 25 T34 20" fill="none" stroke="#f5e9b8" stroke-opacity="0.23" stroke-width="3"/></pattern>',
        '<pattern id="forest-pattern" width="52" height="45" patternUnits="userSpaceOnUse"><circle cx="13" cy="14" r="7" fill="#245c35" fill-opacity="0.25"/><circle cx="35" cy="28" r="9" fill="#174d2b" fill-opacity="0.22"/><circle cx="47" cy="7" r="5" fill="#d4e7b2" fill-opacity="0.15"/></pattern>',
        '<pattern id="swamp-pattern" width="62" height="38" patternUnits="userSpaceOnUse"><path d="M0 12 Q15 4 31 12 T62 12 M8 29 Q23 21 39 29 T70 29" fill="none" stroke="#285f58" stroke-opacity="0.34" stroke-width="3"/></pattern>',
        '<pattern id="hill-pattern" width="75" height="55" patternUnits="userSpaceOnUse"><path d="M2 45 Q20 8 38 45 Q55 15 73 45" fill="none" stroke="#744926" stroke-opacity="0.23" stroke-width="4"/></pattern>',
        '<pattern id="mountain-pattern" width="82" height="70" patternUnits="userSpaceOnUse"><path d="M3 61 L27 17 L42 42 L57 8 L80 61" fill="none" stroke="#4b2e20" stroke-opacity="0.34" stroke-width="5"/><path d="M21 28 L27 17 L33 29 M50 20 L57 8 L64 23" fill="none" stroke="#f3eadc" stroke-opacity="0.36" stroke-width="4"/></pattern>',
    ])

    for name, terrains in TEXTURE_GROUPS.items():
        out.append(f'<mask id="{name}-mask" maskUnits="userSpaceOnUse" x="0" y="0" width="3200" height="2200">')
        out.append('<rect width="3200" height="2200" fill="black"/>')
        out.append('<g filter="url(#soft-mask)">')
        out.extend(polygons_for(rows, terrains))
        out.extend(['</g>', '</mask>'])
    out.append('</defs>')

    # Smooth bathymetry. Coastal cells are always treated as shallow water.
    out.append('<rect width="3200" height="2200" fill="#08306b"/>')
    out.append('<g mask="url(#sea-mask)" filter="url(#sea-surface)">')
    for row in rows:
        if row["Категория"] not in {"Море", "Побережье"}:
            continue
        terrain = "Мелководье" if row["Категория"] == "Побережье" else row["Тип местности"]
        fill = SEA_COLORS.get(terrain, SEA_COLORS["Открытое море"])
        out.append(f'<polygon points="{polygon_points(int(row["Q"]), int(row["R"]))}" fill="{fill}"/>')
    out.append('</g>')

    # Subtle additional wave streaks, confined to water.
    out.extend([
        '<g mask="url(#sea-mask)" opacity="0.19">',
        '<path d="M-100 280 Q420 220 900 310 T1900 290 T3300 330 M-100 740 Q500 650 1080 760 T2200 720 T3350 780 M-100 1260 Q430 1180 980 1270 T2080 1230 T3350 1280 M-100 1800 Q520 1710 1120 1820 T2320 1770 T3350 1840" fill="none" stroke="#d7f3ff" stroke-width="10" stroke-linecap="round"/>',
        '</g>',
    ])

    # Smooth hypsometry clipped by the exact source coastline.
    out.append('<g clip-path="url(#land-clip)" filter="url(#land-surface)">')
    for row in rows:
        if row["Категория"] not in {"Суша", "Побережье"}:
            continue
        fill = LAND_COLORS.get(land_type(row["Тип местности"]), LAND_COLORS["Равнина"])
        out.append(f'<polygon points="{polygon_points(int(row["Q"]), int(row["R"]))}" fill="{fill}"/>')
    out.append('</g>')

    # Biome-specific textures have blurred masks, so they do not end at hex borders.
    pattern_by_group = {
        "plains": "plain-pattern", "forest": "forest-pattern", "swamp": "swamp-pattern",
        "hills": "hill-pattern", "mountains": "mountain-pattern",
    }
    for group, pattern in pattern_by_group.items():
        opacity = "0.70" if group in {"forest", "mountains"} else "0.52"
        out.append(f'<rect width="3200" height="2200" fill="url(#{pattern})" opacity="{opacity}" clip-path="url(#land-clip)" mask="url(#{group}-mask)"/>')

    # A soft near-shore highlight follows the original vector coastline.
    out.append('<g mask="url(#sea-mask)" fill="none" stroke="#d8f3f8" stroke-opacity="0.78" stroke-width="25">')
    for path in land_paths:
        out.append(f'<path d="{html.escape(path, quote=True)}"/>')
    out.append('</g>')
    out.append('<g fill="none" stroke="#405567" stroke-opacity="0.35" stroke-width="3">')
    for path in land_paths:
        out.append(f'<path d="{html.escape(path, quote=True)}"/>')
    out.append('</g>')

    # The gameplay grid stays crisp and independent from the visual blending.
    out.append('<g id="hex-grid" fill="none" stroke="#172b3a" stroke-opacity="0.48" stroke-width="2">')
    for row in rows:
        if row["Категория"] != "Вне полотна":
            q, r = int(row["Q"]), int(row["R"])
            title = html.escape(f"Q={q}, R={r}; {row['Категория']}; {row['Тип местности']}; ресурс: {row['Основной ресурс']}")
            out.append(f'<polygon points="{polygon_points(q, r)}"><title>{title}</title></polygon>')
    out.append('</g>')

    # Legend remains in the free lower-left sea area.
    out.extend([
        '<g id="legend" transform="translate(55 1460)" font-family="Segoe UI, Arial, sans-serif" filter="url(#legend-shadow)">',
        '<rect width="650" height="650" rx="24" fill="#ffffff" fill-opacity="0.93" stroke="#334155" stroke-width="3"/>',
        '<text x="34" y="55" font-size="34" font-weight="700" fill="#172033">Высоты и глубины</text>',
        '<text x="34" y="90" font-size="21" fill="#475569">Текстурированный прототип</text>',
    ])
    legend = [
        ("Мелководье", SEA_COLORS["Мелководье"]), ("Шельф", SEA_COLORS["Шельф"]),
        ("Открытое море", SEA_COLORS["Открытое море"]), ("Глубоководье", SEA_COLORS["Глубоководье"]),
        ("Низменности и луга", LAND_COLORS["Луг"]), ("Леса", LAND_COLORS["Густой лес"]),
        ("Сухие равнины", LAND_COLORS["Полупустыня"]), ("Холмы", LAND_COLORS["Холмы"]),
        ("Горы", LAND_COLORS["Горы"]), ("Высокогорье", LAND_COLORS["Высокогорье"]),
    ]
    for index, (label, color) in enumerate(legend):
        y = 125 + index * 48
        out.append(f'<rect x="35" y="{y}" width="62" height="32" rx="4" fill="{color}" stroke="#334155"/>')
        out.append(f'<text x="116" y="{y + 25}" font-size="23" fill="#172033">{label}</text>')
    out.extend([
        '<line x1="35" y1="615" x2="615" y2="615" stroke="#94a3b8"/>',
        f'<text x="35" y="640" font-size="17" fill="#475569">Источник: {MAP_URL} · прототип 0.2</text>',
        '</g>', '</svg>',
    ])
    OUTPUT_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> None:
    with Path(CSV_PATH).open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter=";"))
    land_paths = fetch_land_paths()
    generate(rows, land_paths)
    print(f"Generated {OUTPUT_PATH} from {len(rows)} coordinate rows")


if __name__ == "__main__":
    main()
