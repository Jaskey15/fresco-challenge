"""Baseline snapshot for filter.find_schedule_regions().

Run:  .venv/bin/python tests/baseline_filter.py
Diff: .venv/bin/python tests/baseline_filter.py | diff tests/baseline_filter.snapshot -
"""

import sys
sys.path.insert(0, "src")

from pathlib import Path
from hardware_sets.filter import find_schedule_regions

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

for name in SAMPLES:
    path = Path("samples") / name
    if not path.exists():
        print(f"{name}: MISSING")
        continue
    regions = find_schedule_regions(path)
    print(f"{name}: {len(regions)} regions")
    for r in regions:
        print(f"  {r.start_page}-{r.end_page}  {r.start_marker}  {r.end_marker}")
