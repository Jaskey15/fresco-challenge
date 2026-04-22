"""Run extract.py against the first region of a chosen sample PDF."""

import json
import sys
from dataclasses import asdict
from pathlib import Path

from hardware_sets.filter import find_schedule_regions
from hardware_sets.layout import extract_layout
from hardware_sets.extract import extract_sets


def main(pdf_rel: str = "samples/div_08_Schulz.pdf") -> None:
    pdf = Path(__file__).resolve().parents[1] / pdf_rel
    regions = find_schedule_regions(pdf)
    if not regions:
        print(f"no regions in {pdf}", file=sys.stderr)
        sys.exit(1)

    region = regions[0]
    layouts = [extract_layout(pdf, p) for p in range(region.start_page, region.end_page + 1)]
    sets = extract_sets(region, layouts)
    print(json.dumps([asdict(s) for s in sets], indent=2, default=str))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "samples/div_08_Schulz.pdf")
