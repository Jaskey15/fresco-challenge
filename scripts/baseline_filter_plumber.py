"""A/B test: compare find_schedule_regions output using pdftotext vs pdfplumber.

Run:
    .venv/bin/python scripts/baseline_filter_plumber.py

Prints side-by-side diff. No diff = safe to swap.
"""

import sys
sys.path.insert(0, "src")

import re
import subprocess
from pathlib import Path

import pdfplumber
from pypdf import PdfReader

from hardware_sets.filter import (
    find_schedule_regions,
    _has_tabular_content,
    _current_section,
    _match_start,
    _heuristic_start,
    END_OF_SECTION_RE,
)
from hardware_sets.types import ScheduleRegion


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


# --- pdfplumber page text replacement ---

def _page_text_plumber(pdf_path: Path, page: int) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        return pdf.pages[page - 1].extract_text(layout=True) or ""


def _page_count_plumber(pdf_path: Path) -> int:
    with pdfplumber.open(pdf_path) as pdf:
        return len(pdf.pages)


def find_schedule_regions_plumber(pdf_path: Path) -> list[ScheduleRegion]:
    """Same logic as find_schedule_regions but uses pdfplumber for text."""
    total = _page_count_plumber(pdf_path)
    regions: list[ScheduleRegion] = []

    in_region = False
    start_page = 0
    start_marker = ""
    region_section = None

    for page in range(1, total + 1):
        text = _page_text_plumber(pdf_path, page)
        if not text.strip():
            continue

        page_section = _current_section(text)

        if not in_region:
            name, needs_guard = _match_start(text)
            if name and needs_guard and not _has_tabular_content(text):
                name = None
            if not name and _heuristic_start(text):
                name = "heuristic"
            if name:
                in_region = True
                start_page = page
                start_marker = name
                region_section = page_section
            continue

        if END_OF_SECTION_RE.search(text):
            regions.append(ScheduleRegion(start_page, page, start_marker, "END OF SECTION"))
            in_region = False
            region_section = None
            continue

        if page_section and region_section and page_section != region_section:
            regions.append(ScheduleRegion(start_page, page - 1, start_marker, "new_section"))
            in_region = False
            name, needs_guard = _match_start(text)
            if name and needs_guard and not _has_tabular_content(text):
                name = None
            if name:
                in_region = True
                start_page = page
                start_marker = name
                region_section = page_section

    if in_region:
        regions.append(ScheduleRegion(start_page, total, start_marker, "eof"))
    return regions


def fmt(name: str, regions: list[ScheduleRegion]) -> list[str]:
    lines = [f"{name}: {len(regions)} regions"]
    for r in regions:
        lines.append(f"  {r.start_page}-{r.end_page}  {r.start_marker}  {r.end_marker}")
    return lines


# --- Run both and compare ---

all_match = True
for name in SAMPLES:
    path = Path("samples") / name
    if not path.exists():
        print(f"{name}: MISSING")
        continue

    orig = find_schedule_regions(path)
    plumb = find_schedule_regions_plumber(path)

    orig_lines = fmt(name, orig)
    plumb_lines = fmt(name, plumb)

    if orig_lines == plumb_lines:
        print(f"OK  {name}")
    else:
        all_match = False
        print(f"DIFF  {name}")
        orig_set = set(orig_lines)
        plumb_set = set(plumb_lines)
        for l in orig_lines:
            marker = "  " if l in plumb_set else "- "
            print(f"  {marker}{l}")
        for l in plumb_lines:
            if l not in orig_set:
                print(f"  + {l}")

print()
print("RESULT:", "ALL MATCH — safe to swap" if all_match else "DIFFERENCES FOUND — review before swapping")
