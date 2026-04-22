"""Locate contiguous schedule regions within a PDF.

See spec §4.1. The module exposes `find_schedule_regions(pdf_path)`
returning a list of `ScheduleRegion`. It does NOT parse any set
content — that is extract.py's job.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from pypdf import PdfReader

from hardware_sets.types import ScheduleRegion

# -----------------------------------------------------------------------------
# Patterns. Named so that `ScheduleRegion.start_marker` is debuggable.
# -----------------------------------------------------------------------------

START_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("door_hardware_schedule", re.compile(r"DOOR\s+HARDWARE\s+SCHEDULE", re.I)),
    ("hardware_sets_colon",    re.compile(r"\bD\.\s*Hardware\s+Sets:", re.I)),
    ("schedule_section_3dot",  re.compile(r"^\s*3\.\d+\s+SCHEDULE", re.I | re.M)),
    ("group_1",                re.compile(r"Hardware\s+(?:Group|Set)(?:/Set)?\s*(?:No\.?|#)?\s*0*1\b", re.I)),
]

END_OF_SECTION_RE = re.compile(r"END\s+OF\s+SECTION", re.I)
CSI_HEADER_RE = re.compile(r"SECTION\s+(\d{2})\s*[-\s]?\s*(\d{2})\s*[-\s]?\s*(\d{2})")

# Heuristic fallback signals (spec §4.1 marker #4).
_QTY_HDR_RE = re.compile(r"\bQTY\b|\bQUANTITY\b", re.I)
_EA_RE = re.compile(r"\bEA\b", re.I)
_SET_TOKEN_RE = re.compile(r"^\s*SET\b", re.I | re.M)
# A known-mfr or known-finish code presence is checked against vocab.

# Tabular schedule row anchor: "N EA ..." (e.g., "1 EA HINGE", "3 EA-R ACTUATOR").
# Presence of at least one is the strongest single signal that a page holds
# real table rows rather than prose that mentions "door hardware schedule".
_QTY_EA_ROW_RE = re.compile(r"\b\d+\s+EA(?:-[A-Z])?\b", re.I | re.M)


def _page_text(pdf_path: Path, page: int) -> str:
    """Return `pdftotext -layout` output for 1-indexed `page`."""
    result = subprocess.run(
        ["pdftotext", "-layout", "-f", str(page), "-l", str(page), str(pdf_path), "-"],
        capture_output=True, text=True, check=False,
    )
    # pdftotext returns nonzero for weird PDFs but still writes stdout; tolerate.
    return result.stdout or ""


def _page_count(pdf_path: Path) -> int:
    return len(PdfReader(str(pdf_path)).pages)


def _current_section(text: str) -> str | None:
    m = CSI_HEADER_RE.search(text)
    if not m:
        return None
    return f"{m.group(1)}{m.group(2)}{m.group(3)}"


def _match_start(text: str) -> str | None:
    """Return the name of the first matching START_PATTERNS entry, else None."""
    for name, pat in START_PATTERNS:
        if pat.search(text):
            return name
    return None


def _heuristic_start(text: str) -> bool:
    """Spec §4.1 fallback: 3+ of (bare SET, QTY/EA column, known mfr/finish code)."""
    from hardware_sets.vocab import GLOBAL_MFR_VOCAB, GLOBAL_FINISH_VOCAB

    signals = 0
    if _SET_TOKEN_RE.search(text):
        signals += 1
    if _QTY_HDR_RE.search(text) or _EA_RE.search(text):
        signals += 1
    # Tokenize uppercase words and look for vocab hits
    tokens = {t.upper() for t in re.findall(r"[A-Za-z0-9]{2,}", text)}
    if tokens & GLOBAL_MFR_VOCAB:
        signals += 1
    if tokens & GLOBAL_FINISH_VOCAB:
        signals += 1
    return signals >= 3


def find_schedule_regions(pdf_path: Path) -> list[ScheduleRegion]:
    """Return every contiguous schedule region in `pdf_path`.

    Scanned PDFs (no extractable text) yield `[]`. Regions without an
    explicit end marker close at EOF.
    """
    total = _page_count(pdf_path)
    regions: list[ScheduleRegion] = []

    in_region = False
    start_page = 0
    start_marker = ""
    region_section: str | None = None

    for page in range(1, total + 1):
        text = _page_text(pdf_path, page)
        if not text.strip():
            continue

        page_section = _current_section(text)

        if not in_region:
            name = _match_start(text)
            # A named pattern match in narrative prose (submittal sections, cross-
            # references) produces costly false regions. Require a tabular row
            # anchor on the same page before entering.
            if name and not _QTY_EA_ROW_RE.search(text):
                name = None
            if not name and _heuristic_start(text):
                name = "heuristic"
            if name:
                in_region = True
                start_page = page
                start_marker = name
                region_section = page_section
            continue

        # in_region: check end conditions
        if END_OF_SECTION_RE.search(text):
            regions.append(ScheduleRegion(start_page, page, start_marker, "END OF SECTION"))
            in_region = False
            region_section = None
            continue

        if page_section and region_section and page_section != region_section:
            regions.append(ScheduleRegion(start_page, page - 1, start_marker, "new_section"))
            in_region = False
            # The current page could itself start a new region
            name = _match_start(text)
            if name and not _QTY_EA_ROW_RE.search(text):
                name = None
            if name:
                in_region = True
                start_page = page
                start_marker = name
                region_section = page_section

    if in_region:
        regions.append(ScheduleRegion(start_page, total, start_marker, "eof"))
    return regions
