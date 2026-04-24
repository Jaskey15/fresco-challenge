"""Locate contiguous schedule regions within a PDF.

Exposes `find_schedule_regions(pdf_path)` returning a list of
`ScheduleRegion`. Does NOT parse set content — that is extract.py's job.
"""

from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from hardware_sets.types import ScheduleRegion

# -----------------------------------------------------------------------------
# Start patterns — checked in order; first match wins.
# (name, regex, needs_tabular_guard)
# -----------------------------------------------------------------------------

START_PATTERNS: list[tuple[str, re.Pattern[str], bool]] = [
    # High confidence — specific set/group markers; bypass tabular guard
    ("group_or_set",    re.compile(r"Hardware\s+(?:Group|Set)(?:/Set)?\s*(?:No\.?|#)\s*\S+", re.I), False),
    ("hw_number",       re.compile(r"\bHW\s+\d+", re.I), False),
    ("set_label",       re.compile(r"\bSet[:\s]+(?:EX-?)?\d", re.I), False),
    ("set_hash",        re.compile(r"\bSet\s+#\s*\S+", re.I), False),
    ("heading_number",  re.compile(r"\bHeading\s+#\s*\d+", re.I), False),
    # Low confidence — generic section headers; require tabular guard
    ("door_hardware_schedule", re.compile(r"DOOR\s+HARDWARE\s+SCHEDULE", re.I), True),
    ("hardware_sets_colon",    re.compile(r"\bHardware\s+Sets\s*:", re.I), True),
    ("schedule_section_3dot",  re.compile(r"^\s*3\.\d+\s+(?:HARDWARE\s+)?SCHEDULE", re.I | re.M), True),
    ("hardware_schedule_head", re.compile(r"(?:^|\n)\s*Hardware\s+Schedule\s*$", re.I | re.M), True),
]

END_OF_SECTION_RE = re.compile(r"END\s+OF\s+SECTION", re.I)
CSI_HEADER_RE = re.compile(r"SECTION\s+(\d{2})\s*[-\s]?\s*(\d{2})\s*[-\s]?\s*(\d{2})")

# Heuristic fallback signals — all 3 categories required.
_SET_LINE_RE = re.compile(r"^\s*SET\b", re.I | re.M)
_QTY_KEYWORD_RE = re.compile(r"\bQTY\b|\bQUANTITY\b|\bEA\b", re.I)
_NUMBER_LEADING_LINE_RE = re.compile(r"^\s*\d+\s+[A-Z]", re.M)

# Tabular guards — any one passing confirms schedule content.
_QTY_UNIT_ROW_RE = re.compile(r"\b\d+\s+(?:EA(?:-[A-Z])?|Ea\.|Set|Pr)\b", re.I | re.M)
_INDENTED_NUMBER_LINE_RE = re.compile(r"^\s+\d+\s+\w", re.M)
_DASH_NOTATION_RE = re.compile(r"(?:^|\s)--\s+\w", re.M)
_HW_COMPONENT_RE = re.compile(
    r"\d+.*(?:HINGE|CLOSER|LOCKSET|STRIKE|BOLT|THRESHOLD|GASKETING|SWEEP|CYLINDER|STOP|PANIC|EXIT\s+DEVICE)",
    re.I,
)


def _has_tabular_content(text: str) -> bool:
    """Check whether a page contains tabular schedule data (not just prose)."""
    if _QTY_UNIT_ROW_RE.search(text):
        return True
    if len(_INDENTED_NUMBER_LINE_RE.findall(text)) >= 3:
        return True
    if len(_NUMBER_LEADING_LINE_RE.findall(text)) >= 3:
        return True
    if _DASH_NOTATION_RE.search(text) and _NUMBER_LEADING_LINE_RE.search(text):
        return True
    if len(_HW_COMPONENT_RE.findall(text)) >= 12:
        return True
    return False


def _current_section(text: str) -> str | None:
    m = CSI_HEADER_RE.search(text)
    if not m:
        return None
    return f"{m.group(1)}{m.group(2)}{m.group(3)}"


def _match_start(text: str) -> tuple[str | None, bool]:
    """Return (name, needs_guard) for the first matching pattern, else (None, False)."""
    for name, pat, needs_guard in START_PATTERNS:
        if pat.search(text):
            return name, needs_guard
    return None, False


def _detect_schedule_start(text: str) -> str | None:
    """Return the start marker name if this page begins a schedule region, else None.

    Tries named patterns first (with tabular guard for low-confidence ones),
    then falls back to the heuristic signal check.
    """
    name, needs_guard = _match_start(text)
    if name and needs_guard and not _has_tabular_content(text):
        name = None
    if not name and _heuristic_start(text):
        name = "heuristic"
    return name


def _heuristic_start(text: str) -> bool:
    """Fallback: all 3 of (SET at line start, QTY/EA keyword, high quantity-line density)."""
    signals = 0
    if _SET_LINE_RE.search(text):
        signals += 1
    if _QTY_KEYWORD_RE.search(text):
        signals += 1
    if len(_NUMBER_LEADING_LINE_RE.findall(text)) >= 5:
        signals += 1
    return signals >= 3


def find_schedule_regions(pdf_path: Path) -> list[ScheduleRegion]:
    """Return every contiguous schedule region in `pdf_path`.

    Scanned PDFs (no extractable text) yield `[]`. Regions without an
    explicit end marker close at EOF.
    """
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        regions: list[ScheduleRegion] = []

        in_region = False
        start_page = 0
        start_marker = ""
        region_section: str | None = None

        for page in range(1, total + 1):
            text = pdf.pages[page - 1].extract_text(layout=True) or ""
            if not text.strip():
                continue

            page_section = _current_section(text)

            if not in_region:
                name = _detect_schedule_start(text)
                if name:
                    in_region = True
                    start_page = page
                    start_marker = name
                    region_section = page_section
                # Don't check end conditions on the page that opens a region
                continue

            if END_OF_SECTION_RE.search(text):
                regions.append(ScheduleRegion(start_page, page, start_marker, "END OF SECTION"))
                in_region = False
                region_section = None
                continue

            if page_section and region_section and page_section != region_section:
                regions.append(ScheduleRegion(start_page, page - 1, start_marker, "new_section"))
                in_region = False
                name = _detect_schedule_start(text)
                if name:
                    in_region = True
                    start_page = page
                    start_marker = name
                    region_section = page_section

        if in_region:
            regions.append(ScheduleRegion(start_page, total, start_marker, "eof"))
        return regions
