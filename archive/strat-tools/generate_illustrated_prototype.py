#!/usr/bin/env python3
"""Create an illustrated atlas-style variant of the textured SVG prototype."""

from __future__ import annotations

import csv
import math
import re
from pathlib import Path

import generate_textured_prototype


ROOT = Path(__file__).resolve().parent
BASE_PATH = ROOT / "hex-terrain-textured-prototype.svg"
OUTPUT_PATH = ROOT / "hex-terrain-illustrated-prototype.svg"


PATTERNS = {
    "plain-pattern": """<pattern id="plain-pattern" width="150" height="110" patternUnits="userSpaceOnUse">
<path d="M8 92 Q45 65 77 78 T145 64 M2 104 Q42 77 79 90 T151 76" fill="none" stroke="#6f8f3f" stroke-opacity="0.33" stroke-width="4"/>
<path d="M22 90 l9 -18 M48 80 l7 -17 M105 78 l8 -19 M130 68 l7 -16" stroke="#f4e4a1" stroke-opacity="0.55" stroke-width="4" stroke-linecap="round"/>
<path d="M31 72 l-7 -5 M31 72 l7 -7 M55 63 l-6 -6 M55 63 l7 -6 M113 59 l-7 -6 M113 59 l7 -7" fill="none" stroke="#769346" stroke-opacity="0.48" stroke-width="3"/>
</pattern>""",
    "forest-pattern": """<pattern id="forest-pattern" width="190" height="145" patternUnits="userSpaceOnUse">
<g stroke="#315f38" stroke-width="3" stroke-linejoin="round" opacity="0.68">
<path d="M42 115 V78"/><path d="M42 35 L21 80 H63 Z M42 54 L17 99 H67 Z" fill="#4e854e"/>
<path d="M137 119 V82"/><circle cx="137" cy="66" r="27" fill="#6a9d5d"/><circle cx="119" cy="76" r="19" fill="#5d9155"/><circle cx="155" cy="76" r="20" fill="#78a969"/>
</g><path d="M8 124 Q51 114 94 124 T184 122" fill="none" stroke="#365f39" stroke-opacity="0.22" stroke-width="4"/>
</pattern>""",
    "swamp-pattern": """<pattern id="swamp-pattern" width="145" height="100" patternUnits="userSpaceOnUse">
<ellipse cx="68" cy="72" rx="58" ry="17" fill="#477f78" fill-opacity="0.48" stroke="#285d57" stroke-width="3"/>
<path d="M13 75 Q40 64 70 73 T129 70" fill="none" stroke="#b6ddd0" stroke-opacity="0.65" stroke-width="3"/>
<g stroke="#365b34" stroke-width="4" stroke-linecap="round"><path d="M25 70 V28 M38 69 V18 M51 69 V36 M105 70 V25 M117 69 V39"/><path d="M38 35 l-10 -9 M38 43 l11 -10 M105 41 l-10 -9 M105 49 l12 -9"/></g>
<g fill="#8a6733"><ellipse cx="38" cy="17" rx="4" ry="10"/><ellipse cx="105" cy="24" rx="4" ry="10"/></g>
</pattern>""",
    "hill-pattern": """<pattern id="hill-pattern" width="170" height="115" patternUnits="userSpaceOnUse"></pattern>""",
    "mountain-pattern": """<pattern id="mountain-pattern" width="190" height="145" patternUnits="userSpaceOnUse">
<path d="M-12 132 L48 34 L79 82 L112 13 L202 132 Z" fill="#7d563d" stroke="#4a3025" stroke-width="5" stroke-linejoin="round"/>
<path d="M48 34 L31 63 L49 56 L61 68 L69 66 Z M112 13 L87 54 L110 43 L127 61 L142 62 Z" fill="#eee9dd" fill-opacity="0.92"/>
<path d="M48 34 L48 128 M112 13 L112 130" stroke="#3b281f" stroke-opacity="0.28" stroke-width="7"/>
<path d="M-3 132 Q45 119 91 132 T190 130" fill="none" stroke="#3e2b22" stroke-opacity="0.45" stroke-width="6"/>
</pattern>""",
}

OCEAN_PATTERN = """<pattern id="ocean-wave-pattern" width="180" height="105" patternUnits="userSpaceOnUse">
<path d="M5 38 Q28 18 51 38 T97 38 T143 38 T189 38 M-22 82 Q1 62 24 82 T70 82 T116 82 T162 82" fill="none" stroke="#e5f7ff" stroke-opacity="0.62" stroke-width="6" stroke-linecap="round"/>
<path d="M16 43 Q28 34 40 43 M82 87 Q94 78 106 87" fill="none" stroke="#ffffff" stroke-opacity="0.42" stroke-width="3"/>
</pattern>"""


def replace_pattern(svg: str, pattern_id: str, replacement: str) -> str:
    expression = rf'<pattern id="{re.escape(pattern_id)}".*?</pattern>'
    updated, count = re.subn(expression, replacement, svg, count=1, flags=re.DOTALL)
    if count != 1:
        raise RuntimeError(f"Pattern not found in base prototype: {pattern_id}")
    return updated


def main() -> None:
    # Rebuild the base first so both variants always use the current CSV values.
    generate_textured_prototype.main()
    svg = BASE_PATH.read_text(encoding="utf-8")
    for pattern_id, replacement in PATTERNS.items():
        svg = replace_pattern(svg, pattern_id, replacement)
    svg = svg.replace("</defs>", OCEAN_PATTERN + "\n</defs>", 1)
    water_symbols = '<rect width="3200" height="2200" fill="url(#ocean-wave-pattern)" opacity="0.48" mask="url(#sea-mask)"/>'
    marker = '<g clip-path="url(#land-clip)" filter="url(#land-surface)">'
    svg = svg.replace(marker, water_symbols + "\n" + marker, 1)
    with Path(generate_textured_prototype.CSV_PATH).open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter=";"))
    hill_symbols = ['<g id="hill-symbols" clip-path="url(#land-clip)" opacity="0.72">']
    for row in rows:
        if row["Категория"] not in {"Суша", "Побережье"} or row["Тип местности"].rsplit(" / ", 1)[-1] != "Холмы":
            continue
        q, r = int(row["Q"]), int(row["R"])
        cx = math.sqrt(3) * 80 * (q + r / 2)
        cy = 120 * r
        hill_symbols.append(
            f'<g transform="translate({cx:.2f} {cy:.2f})">'
            '<path d="M-57 38 Q0 -40 57 38 Z" fill="#b98249" fill-opacity="0.62" stroke="#6e492e" stroke-width="4"/>'
            '<path d="M-43 32 Q0 -21 42 32" fill="none" stroke="#ead5a7" stroke-opacity="0.68" stroke-width="7"/>'
            '<path d="M-29 28 Q0 -8 29 28" fill="none" stroke="#795132" stroke-opacity="0.45" stroke-width="3"/>'
            '</g>'
        )
    hill_symbols.append('</g>')
    svg = svg.replace('<g id="hex-grid"', "\n".join(hill_symbols) + '\n<g id="hex-grid"', 1)
    svg = svg.replace('opacity="0.70" clip-path="url(#land-clip)" mask="url(#forest-mask)"', 'opacity="0.42" clip-path="url(#land-clip)" mask="url(#forest-mask)"', 1)
    svg = svg.replace("Текстурированный прототип карты", "Иллюстративный прототип карты", 1)
    svg = svg.replace("Текстурированный прототип</text>", "Иллюстративный атласный вариант</text>", 1)
    svg = svg.replace("прототип 0.2", "вариант 0.3", 1)
    OUTPUT_PATH.write_text(svg, encoding="utf-8")
    print(f"Generated {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
