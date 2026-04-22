"""Dump detected schedule regions for every sample PDF to stdout."""

from pathlib import Path

from hardware_sets.filter import find_schedule_regions

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def main() -> None:
    for pdf in sorted(SAMPLES.glob("*.pdf")):
        regions = find_schedule_regions(pdf)
        print(f"{pdf.name}: {len(regions)} region(s)")
        for r in regions:
            print(f"   pages {r.start_page}-{r.end_page} "
                  f"(start={r.start_marker}, end={r.end_marker})")


if __name__ == "__main__":
    main()
