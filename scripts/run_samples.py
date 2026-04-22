"""Run the extraction pipeline against every sample PDF.

Usage: .venv/bin/python scripts/run_samples.py
Writes: out/<pdf_stem>.json per PDF, plus out/_summary.txt.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
OUT = ROOT / "out"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(SAMPLES.glob("*.pdf"))
    if not pdfs:
        print("no sample PDFs found", file=sys.stderr)
        return 1

    rows: list[str] = []
    for pdf in pdfs:
        out_path = OUT / f"{pdf.stem}.json"
        print(f"=== {pdf.name} ===", flush=True)
        t0 = time.time()
        proc = subprocess.run(
            [sys.executable, "-m", "hardware_sets", str(pdf), "--out", str(out_path)],
            cwd=ROOT,
        )
        elapsed = time.time() - t0

        if proc.returncode == 0 and out_path.exists():
            data = json.loads(out_path.read_text())
            sets = data.get("hardware_sets", [])
            warnings = data.get("diagnostics", {}).get("warnings", [])
            rows.append(
                f"{pdf.name:50s}  exit=0  sets={len(sets):3d}  "
                f"warnings={len(warnings)}  ({elapsed:.1f}s)"
            )
        else:
            rows.append(f"{pdf.name:50s}  exit={proc.returncode}  ({elapsed:.1f}s)")

    summary = OUT / "_summary.txt"
    summary.write_text("\n".join(rows) + "\n")
    print("\n" + "\n".join(rows))
    print(f"\nwrote {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
