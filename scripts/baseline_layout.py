"""Baseline snapshot for layout.extract_layout().

Run:  .venv/bin/python scripts/baseline_layout.py
Diff: .venv/bin/python scripts/baseline_layout.py 2>/dev/null | diff scripts/baseline_layout.snapshot -
"""

import sys
sys.path.insert(0, "src")

from pathlib import Path
from hardware_sets.filter import find_schedule_regions
from hardware_sets.layout import extract_layout

MAX_LINE_WIDTH = 100

SAMPLES = [
    "Shubie_Center_08.pdf",
    "valor_acres_door_hardware.pdf",
    "roselle_public_library_08.pdf",
    "81-85_bridgeport.pdf",
    "SJC_Div_08.pdf",
    "jc_ryan_2.pdf",
    "morris_bank_08.pdf",
    "star_hardware_08.pdf",
]


def pick_pages(start: int, end: int) -> list[int]:
    """Return first, mid, last pages for a region (deduplicated)."""
    mid = (start + end) // 2
    pages = list(dict.fromkeys([start, mid, end]))
    return pages


def truncate(text: str) -> str:
    if len(text) > MAX_LINE_WIDTH:
        return text[:MAX_LINE_WIDTH] + "…"
    return text


for name in SAMPLES:
    path = Path("samples") / name
    if not path.exists():
        print(f"{name}: MISSING")
        continue
    regions = find_schedule_regions(path)
    if not regions:
        print(f"{name}: 0 regions — skipping layout")
        continue
    print(f"{name}: {len(regions)} regions")
    for ri, r in enumerate(regions):
        pages = pick_pages(r.start_page, r.end_page)
        print(f"  region {ri}: pages {r.start_page}-{r.end_page}")
        for pg in pages:
            layout = extract_layout(path, pg)
            n = len(layout.lines)
            print(f"    page {pg}: {n} lines")
            first3 = layout.lines[:3]
            last3 = layout.lines[-3:] if n > 6 else layout.lines[3:]
            for line in first3:
                print(f"      L{line.number:02d}: {truncate(line.text)}")
            if n > 6:
                print(f"      ...")
            for line in last3:
                print(f"      L{line.number:02d}: {truncate(line.text)}")
