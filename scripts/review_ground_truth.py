"""Review extraction output against PDF source lines for ground truth verification.

Run:  .venv/bin/python scripts/review_ground_truth.py [sample_name]
      .venv/bin/python scripts/review_ground_truth.py Shubie_Center_08
      .venv/bin/python scripts/review_ground_truth.py all
"""

import json
import sys
sys.path.insert(0, "src")

from pathlib import Path
from hardware_sets.filter import find_schedule_regions
from hardware_sets.layout import extract_layout

GROUND_TRUTH_DIR = Path("samples/ground_truth")
SAMPLES_DIR = Path("samples")

SAMPLES = [
    "Shubie_Center_08",
    "roselle_public_library_08",
    "star_hardware_08",
]


def load_layouts(pdf_path: Path) -> dict[int, list]:
    """Build page->lines lookup from filter regions."""
    regions = find_schedule_regions(pdf_path)
    layouts = {}
    for region in regions:
        for pg in range(region.start_page, region.end_page + 1):
            if pg not in layouts:
                layout = extract_layout(pdf_path, pg)
                layouts[pg] = {line.number: line.text for line in layout.lines}
    return layouts


def get_source_lines(layouts: dict, page: int, line_range: list[int]) -> list[str]:
    """Extract source lines for a set's location."""
    page_lines = layouts.get(page, {})
    if not page_lines:
        return [f"  (page {page} not available)"]
    start, end = line_range
    out = []
    for ln in range(start, end + 1):
        text = page_lines.get(ln, "")
        out.append(f"  L{ln:02d}: {text[:120]}")
    return out


def review_sample(stem: str) -> None:
    gt_path = GROUND_TRUTH_DIR / f"{stem}.json"
    pdf_path = SAMPLES_DIR / f"{stem}.pdf"

    if not gt_path.exists():
        print(f"No ground truth file: {gt_path}")
        return
    if not pdf_path.exists():
        print(f"No PDF: {pdf_path}")
        return

    sets = json.loads(gt_path.read_text())
    print(f"\n{'='*80}")
    print(f" {stem} — {len(sets)} sets")
    print(f"{'='*80}")

    print(f"\nLoading PDF layouts...", file=sys.stderr)
    layouts = load_layouts(pdf_path)

    for s in sets:
        sn = s["set_number"]
        desc = s.get("description") or "(no description)"
        not_used = " [NOT USED]" if s.get("is_not_used") else ""
        components = s.get("components", [])
        loc = s["location"]
        uncertain = s.get("uncertain_fields", [])

        print(f"\n{'─'*80}")
        print(f"SET {sn}: {desc}{not_used}")
        print(f"Page {loc['page']}, lines {loc['line_range'][0]}-{loc['line_range'][1]} | {len(components)} components")

        if uncertain:
            print(f"⚠ UNCERTAIN: {'; '.join(uncertain)}")

        # Show source PDF lines
        print(f"\n  SOURCE:")
        for line in get_source_lines(layouts, loc["page"], loc["line_range"]):
            print(line)

        # Show continued_on pages
        for cont in s.get("continued_on", []):
            print(f"\n  CONTINUED (page {cont['page']}):")
            for line in get_source_lines(layouts, cont["page"], cont["line_range"]):
                print(line)

        # Show extracted components
        print(f"\n  EXTRACTED:")
        for i, c in enumerate(components):
            qty = c["qty"] if c["qty"] is not None else "?"
            desc_c = c.get("description") or "-"
            mfr = c.get("mfr") or "-"
            finish = c.get("finish") or "-"
            cat = c.get("catalog_number") or "-"
            notes = c.get("notes") or ""
            notes_str = f" [{notes}]" if notes else ""
            print(f"    {i+1}. {qty}x {desc_c}")
            print(f"       mfr={mfr}  finish={finish}  cat={cat}{notes_str}")

        print()


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "all"

    if target == "all":
        for s in SAMPLES:
            review_sample(s)
    else:
        stem = target.replace(".pdf", "").replace(".json", "")
        if stem in SAMPLES:
            review_sample(stem)
        else:
            print(f"Unknown sample: {stem}")
            print(f"Available: {', '.join(SAMPLES)}")
