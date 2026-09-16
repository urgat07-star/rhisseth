#!/usr/bin/env python3
"""Generate a muted military-wargame styled SVG terrain variant."""

from __future__ import annotations

import re
from pathlib import Path

import generate_textured_prototype


ROOT = Path(__file__).resolve().parent
BASE_PATH = ROOT / "hex-terrain-textured-prototype.svg"
OUTPUT_PATH = ROOT / "hex-terrain-final.svg"


COLOR_GRADE = {
    # Sea: muted slate blue similar to printed operational maps.
    "#b9e3f3": "#7894a0",
    "#73bfe2": "#587886",
    "#2878b8": "#3e5e6d",
    "#08306b": "#263f4d",
    # Land: olive, khaki and earth rather than bright atlas colours.
    "#79a987": "#596e48",
    "#84bd72": "#758253",
    "#a8d08d": "#7f8954",
    "#b8d68c": "#858a55",
    "#8fbd77": "#68794a",
    "#5c9660": "#3f5834",
    "#c8c7a5": "#8d896b",
    "#dbc58b": "#9b8750",
    "#c49a62": "#80643e",
    "#9b6a43": "#65462f",
    "#68452f": "#46342a",
}


PATTERNS = {
    "plain-pattern": """<pattern id="plain-pattern" width="105" height="84" patternUnits="userSpaceOnUse">
<path d="M-8 67 Q21 57 48 64 T111 58 M3 77 Q34 66 66 73 T113 69" fill="none" stroke="#c1bd78" stroke-opacity="0.14" stroke-width="3"/>
<path d="M14 57 l7 -13 M39 62 l6 -11 M73 53 l7 -14 M94 59 l5 -10" stroke="#41482d" stroke-opacity="0.22" stroke-width="3" stroke-linecap="round"/>
</pattern>""",
    "forest-pattern": """<pattern id="forest-pattern" width="112" height="92" patternUnits="userSpaceOnUse">
<g stroke="#263821" stroke-opacity="0.58" stroke-width="2">
<circle cx="18" cy="28" r="14" fill="#425d32"/><circle cx="37" cy="20" r="17" fill="#516a38"/><circle cx="58" cy="31" r="18" fill="#354d2d"/><circle cx="82" cy="20" r="15" fill="#5c713d"/><circle cx="103" cy="32" r="18" fill="#3c552f"/>
<circle cx="9" cy="62" r="18" fill="#334b2c"/><circle cx="32" cy="58" r="19" fill="#5a6d3c"/><circle cx="57" cy="66" r="17" fill="#405932"/><circle cx="79" cy="57" r="20" fill="#4a6335"/><circle cx="105" cy="66" r="19" fill="#30472a"/>
</g>
<g fill="#9aa360" fill-opacity="0.17"><circle cx="32" cy="14" r="6"/><circle cx="76" cy="15" r="5"/><circle cx="27" cy="52" r="6"/><circle cx="76" cy="50" r="7"/></g>
</pattern>""",
    "swamp-pattern": """<pattern id="swamp-pattern" width="125" height="86" patternUnits="userSpaceOnUse">
<path d="M8 57 Q28 42 51 54 T101 51 T135 54" fill="none" stroke="#263f38" stroke-opacity="0.52" stroke-width="6"/>
<ellipse cx="42" cy="61" rx="31" ry="10" fill="#415d58" fill-opacity="0.52"/><ellipse cx="98" cy="28" rx="23" ry="8" fill="#374f4c" fill-opacity="0.48"/>
<path d="M23 58 V28 M31 57 V19 M88 34 V9 M96 34 V17" stroke="#39462a" stroke-opacity="0.62" stroke-width="3"/>
</pattern>""",
    "hill-pattern": """<pattern id="hill-pattern" width="150" height="105" patternUnits="userSpaceOnUse">
<path d="M-15 91 Q28 35 72 89 Q108 43 165 92 Z" fill="#654e31" fill-opacity="0.30"/>
<path d="M-8 89 Q29 49 67 88 M77 89 Q110 57 153 90" fill="none" stroke="#c0a96c" stroke-opacity="0.20" stroke-width="7"/>
<path d="M-4 94 Q34 61 70 94 M82 94 Q113 69 157 94" fill="none" stroke="#30291f" stroke-opacity="0.32" stroke-width="3"/>
</pattern>""",
    "mountain-pattern": """<pattern id="mountain-pattern" width="175" height="128" patternUnits="userSpaceOnUse">
<path d="M-12 117 L43 38 L72 77 L105 21 L185 117 Z" fill="#4b3b2e" fill-opacity="0.78" stroke="#2d2924" stroke-width="4"/>
<path d="M43 38 L29 59 L44 54 L55 65 L64 66 M105 21 L84 51 L104 43 L119 59 L134 63" fill="#b3ac91" fill-opacity="0.58"/>
<path d="M43 41 L43 113 M105 25 L105 114" stroke="#201f1b" stroke-opacity="0.34" stroke-width="8"/>
</pattern>""",
}

SEA_PATTERN = """<pattern id="wargame-sea-pattern" width="210" height="115" patternUnits="userSpaceOnUse">
<path d="M-20 31 Q25 18 69 30 T158 29 T247 31 M-42 74 Q4 61 49 73 T139 72 T229 74 M-4 103 Q39 93 82 102 T169 101 T256 103" fill="none" stroke="#adc0c3" stroke-opacity="0.17" stroke-width="5"/>
<path d="M18 36 Q43 29 67 35 M111 78 Q137 70 161 77" fill="none" stroke="#d2dcda" stroke-opacity="0.12" stroke-width="2"/>
</pattern>"""


def replace_pattern(svg: str, pattern_id: str, replacement: str) -> str:
    expression = rf'<pattern id="{re.escape(pattern_id)}".*?</pattern>'
    result, count = re.subn(expression, replacement, svg, count=1, flags=re.DOTALL)
    if count != 1:
        raise RuntimeError(f"Pattern not found: {pattern_id}")
    return result


def main() -> None:
    generate_textured_prototype.main()
    svg = BASE_PATH.read_text(encoding="utf-8")
    for source, target in COLOR_GRADE.items():
        svg = svg.replace(source, target)
    for pattern_id, replacement in PATTERNS.items():
        svg = replace_pattern(svg, pattern_id, replacement)
    svg = svg.replace("</defs>", SEA_PATTERN + "\n</defs>", 1)
    sea_overlay = '<rect width="3200" height="2200" fill="url(#wargame-sea-pattern)" opacity="0.68" mask="url(#sea-mask)"/>'
    svg = svg.replace('<g clip-path="url(#land-clip)" filter="url(#land-surface)">', sea_overlay + '\n<g clip-path="url(#land-clip)" filter="url(#land-surface)">', 1)
    # Tone down the broad decorative wave strokes from the colourful prototype.
    svg = svg.replace('<g mask="url(#sea-mask)" opacity="0.19">', '<g mask="url(#sea-mask)" opacity="0.07">', 1)
    svg = svg.replace('stroke="#d8f3f8" stroke-opacity="0.78" stroke-width="25"', 'stroke="#d2d0b8" stroke-opacity="0.58" stroke-width="18"', 1)
    svg = svg.replace('stroke="#172b3a" stroke-opacity="0.48" stroke-width="2"', 'stroke="#1d2928" stroke-opacity="0.68" stroke-width="3"', 1)
    svg = svg.replace("Текстурированный прототип карты", "Военно-картографический прототип карты", 1)
    svg = svg.replace("Текстурированный прототип</text>", "Приглушённый военно-картографический стиль</text>", 1)
    svg = svg.replace("прототип 0.2", "вариант 0.4", 1)
    # A subtle translucent wash unifies the procedural layers like a printed map.
    svg = svg.replace('<g id="hex-grid"', '<rect width="3200" height="2200" fill="#393b24" opacity="0.055" pointer-events="none"/>\n<g id="hex-grid"', 1)
    # The approved final map is supplied without the explanatory legend.
    svg, legend_count = re.subn(
        r'<g id="legend".*?</g>', "", svg, count=1, flags=re.DOTALL
    )
    if legend_count != 1:
        raise RuntimeError("Legend group was not found in the base prototype")
    OUTPUT_PATH.write_text(svg, encoding="utf-8")
    print(f"Generated {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
