"""Baseline snapshot for extract.extract_sets().

Run:  .venv/bin/python scripts/baseline_extract.py
Diff: .venv/bin/python scripts/baseline_extract.py 2>/dev/null | diff scripts/baseline_extract.snapshot -
"""

import json
import sys
sys.path.insert(0, "src")

from dotenv import load_dotenv
load_dotenv(".env.local")

from pathlib import Path
from hardware_sets.filter import find_schedule_regions
from hardware_sets.layout import extract_layout
from hardware_sets.extract import extract_sets

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

OUT_DIR = Path("out/baseline_extract")


def run_sample(name: str) -> None:
    path = Path("samples") / name
    if not path.exists():
        print(f"=== {name}: MISSING ===")
        return

    regions = find_schedule_regions(path)
    if not regions:
        print(f"=== {name}: 0 regions — skipping ===")
        return

    print(f"=== {name}: {len(regions)} region(s) ===")

    all_sets = []
    for ri, region in enumerate(regions):
        layouts = [
            extract_layout(path, pg)
            for pg in range(region.start_page, region.end_page + 1)
        ]
        sets = extract_sets(region, layouts)
        all_sets.extend(sets)

        not_used = sum(1 for s in sets if s.is_not_used)
        print(f"  region {ri}: pages {region.start_page}-{region.end_page} | {len(sets)} sets | {not_used} not_used")

        for s in sets:
            tag = " [NOT USED]" if s.is_not_used else ""
            desc = s.description or "(no description)"
            print(f"    {s.set_number}: {desc}{tag} — {len(s.components)} components")
            for c in s.components:
                qty = c.qty if c.qty is not None else "?"
                desc_c = c.description or "-"
                mfr = c.mfr or "-"
                finish = c.finish or "-"
                cat = c.catalog_number or "-"
                print(f"      {qty}x {desc_c} | mfr={mfr} | finish={finish} | cat={cat}")

    # Cache full JSON for later diffing / inspection
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = Path(name).stem
    out_path = OUT_DIR / f"{stem}.json"
    payload = []
    for s in all_sets:
        payload.append({
            "set_number": s.set_number,
            "description": s.description,
            "is_not_used": s.is_not_used,
            "location": {"page": s.location.page, "line_range": list(s.location.line_range)},
            "continued_on": [
                {"page": c.page, "line_range": list(c.line_range)}
                for c in s.continued_on
            ],
            "components": [
                {
                    "qty": c.qty,
                    "description": c.description,
                    "catalog_number": c.catalog_number,
                    "mfr": c.mfr,
                    "finish": c.finish,
                    "notes": c.notes,
                }
                for c in s.components
            ],
        })
    out_path.write_text(json.dumps(payload, indent=2) + "\n")


for name in SAMPLES:
    run_sample(name)
    print()
