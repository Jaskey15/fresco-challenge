# Hardware Sets PDF Parsing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI that extracts every door-hardware set from a Division 08 specbook PDF into structured JSON with per-set page + line-range location, surviving the four observed layouts.

**Architecture:** Five-module pipeline under `src/hardware_sets/` — `filter.py` picks candidate page regions, `layout.py` produces numbered-line page text via `pdftotext -layout`, `extract.py` runs a prompt-cached Claude Sonnet call with a tool schema, `resolve.py` adds vocabulary-match confidence scores, `cli.py` orchestrates. Types and vocabularies live in `types.py` / `vocab.py`. QA artifact is `scripts/run_samples.py` — no formal test suite per the spec, but two pure-logic modules (`filter.py` marker detection and `resolve.py` scoring) get ~10 lines of pytest each because they're cheap and high-signal during iteration.

**Tech Stack:** Python 3.14 (existing `.venv`), `anthropic` SDK for Claude Sonnet 4.6, `pypdf` for page counting, `pdfplumber` available as backup, Poppler's `pdftotext -layout` via subprocess for the canonical text extraction. Pytest for the two smoke test files.

**Spec reference:** `docs/superpowers/specs/2026-04-21-pdf-parsing-design.md` (authoritative; this plan tracks that document's section numbers).

---

## Task 1: Project skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/hardware_sets/__init__.py`
- Create: `src/hardware_sets/__main__.py`
- Create: `tests/__init__.py`
- Create: `scripts/.gitkeep`
- Create: `out/.gitkeep`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "hardware-sets"
version = "0.1.0"
description = "Extract door hardware sets from Division 08 specbooks."
requires-python = ">=3.12"
dependencies = [
    "anthropic>=0.40.0",
    "pdfplumber>=0.11",
    "pypdf>=5.0",
]

[project.optional-dependencies]
dev = ["pytest>=8"]

[project.scripts]
hardware-sets = "hardware_sets.cli:main_entry"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

- [ ] **Step 2: Write `.gitignore`**

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
out/*.json
out/_summary.txt
.DS_Store
*.egg-info/
dist/
build/
```

- [ ] **Step 3: Create empty package stubs**

```python
# src/hardware_sets/__init__.py
"""Door-hardware set extraction from Division 08 specbooks."""
```

```python
# src/hardware_sets/__main__.py
from hardware_sets.cli import main_entry

if __name__ == "__main__":
    main_entry()
```

```python
# tests/__init__.py
```

- [ ] **Step 4: Install project in editable mode**

Run: `.venv/bin/pip install -e ".[dev]"`
Expected: succeeds, installs `anthropic` plus existing deps; `hardware-sets` command becomes available.

- [ ] **Step 5: Sanity check**

Run: `.venv/bin/python -c "import hardware_sets; print(hardware_sets.__doc__)"`
Expected: prints the docstring.

Run: `.venv/bin/python -m hardware_sets` — will fail with an import error for `hardware_sets.cli` (expected; we wire that up later).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore src/ tests/ scripts/ out/
git commit -m "chore: scaffold hardware-sets package"
```

---

## Task 2: `types.py` — dataclasses

**Files:**
- Create: `src/hardware_sets/types.py`

- [ ] **Step 1: Write `types.py`**

```python
"""Dataclasses shared across the pipeline.

These map 1:1 to the JSON output schema in section 3 of the spec,
with the addition of `ScheduleRegion`, `PageLayout`, `NumberedLine`
as internal pipeline types.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NumberedLine:
    number: int           # 1-indexed from top of page
    text: str             # verbatim pdftotext -layout line


@dataclass
class PageLayout:
    page_number: int      # 1-indexed
    lines: list[NumberedLine]


@dataclass
class ScheduleRegion:
    start_page: int       # 1-indexed, inclusive
    end_page: int         # 1-indexed, inclusive
    start_marker: str     # which START_PATTERNS name matched (for debug)
    end_marker: str       # "END OF SECTION" | "new_section" | "eof"


@dataclass
class SetLocation:
    page: int             # 1-indexed
    line_range: tuple[int, int]  # (first, last), 1-indexed, inclusive


@dataclass
class Component:
    qty: int | None
    description: str | None
    catalog_number: str | None
    mfr: str | None
    finish: str | None
    notes: str | None
    confidence: dict[str, float] = field(default_factory=dict)


@dataclass
class HardwareSet:
    set_number: str
    description: str | None
    location: SetLocation
    components: list[Component] = field(default_factory=list)
    continued_on: list[SetLocation] = field(default_factory=list)
    is_not_used: bool = False
    confidence: float = 1.0
    notes: str | None = None
```

- [ ] **Step 2: Import-check**

Run: `.venv/bin/python -c "from hardware_sets.types import HardwareSet, Component, PageLayout, ScheduleRegion, NumberedLine, SetLocation; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add src/hardware_sets/types.py
git commit -m "feat: add core dataclasses"
```

---

## Task 3: `vocab.py` — vocabularies + patterns

**Files:**
- Create: `src/hardware_sets/vocab.py`

- [ ] **Step 1: Write `vocab.py`**

```python
"""Vocabulary sets and regex patterns for post-extraction validation.

Seeded from the four observed sample formats (Roselle bordered,
Commons Lanes bordered + prose, Shubenacadie unlabeled list,
Schulz labeled list + legend). Lowercase + uppercase entries are
stored directly; matching code normalizes to uppercase.
"""

from __future__ import annotations

import re

# Full names and short codes. Matching is case-insensitive — see _norm below.
GLOBAL_MFR_VOCAB: frozenset[str] = frozenset(
    s.upper()
    for s in {
        "IVE", "IVES",
        "VON", "VND", "VON DUPRIN",
        "SCH", "SCHLAGE",
        "LCN",
        "NGP",
        "ZER", "ZERO",
        "PEM", "PEMKO",
        "ROC", "ROCKWOOD",
        "GLY", "GJ", "GLYNN-JOHNSON",
        "HAG", "HAGER",
        "ADA", "ADAMS RITE",
        "TRI", "TRIMCO", "BBW",
        "ABH",
        "MED", "MEDECO",
        "SEN", "SENTRONIC",
        "ASS", "ASSA ABLOY",
        "SCE", "SECURITRON",
        "BLU", "BLUMCRAFT",
        "CRL", "C.R. LAURENCE",
        "KNX", "KNOX",
        "RIX", "RIXSON",
        "NOR", "NORTON",
        "ALUR",
        "TUBELITE",
    }
)

GLOBAL_FINISH_VOCAB: frozenset[str] = frozenset(
    s.upper()
    for s in {
        # BHMA 3-digit codes most common in samples
        "613", "626", "630", "652", "689", "691", "693", "622", "711",
        # US codes
        "US3", "US4", "US10", "US10B", "US26", "US26D", "US32", "US32D",
        # Color words
        "BLACK", "BSP", "OIL RUBBED BRONZE", "LIGHT BRONZE",
        "MILL ALUM", "PAINTED ENAMEL", "ALUMINUM",
    }
)

# BHMA 3-digit codes live in 600-695. US codes: US followed by 1-2 digits and an optional D/L.
_BHMA_RE = re.compile(r"^(6[0-9]{2})$")
_US_RE = re.compile(r"^US\d{1,2}[DLdl]?$")

FINISH_PATTERNS: tuple[re.Pattern[str], ...] = (_BHMA_RE, _US_RE)

MFR_SHORTCODE_RE = re.compile(r"^[A-Z]{2,4}$")


def norm(s: str | None) -> str | None:
    """Uppercase + strip; `None` passes through."""
    return s.strip().upper() if s else s


def looks_like_finish(value: str) -> bool:
    v = value.strip().upper()
    if v in GLOBAL_FINISH_VOCAB:
        return True
    for pat in FINISH_PATTERNS:
        m = pat.match(v)
        if not m:
            continue
        if pat is _BHMA_RE:
            code = int(m.group(1))
            return 600 <= code <= 695
        return True
    return False


def looks_like_mfr_code(value: str) -> bool:
    v = value.strip().upper()
    return v in GLOBAL_MFR_VOCAB or bool(MFR_SHORTCODE_RE.match(v))
```

- [ ] **Step 2: Import + smoke**

Run:
```bash
.venv/bin/python -c "
from hardware_sets.vocab import looks_like_finish, looks_like_mfr_code, norm
assert looks_like_finish('626')
assert looks_like_finish('US26D')
assert not looks_like_finish('SCH')
assert looks_like_mfr_code('SCH')
assert looks_like_mfr_code('IVES')
assert not looks_like_mfr_code('626')
assert norm(' schlage ') == 'SCHLAGE'
assert norm(None) is None
print('ok')
"
```
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add src/hardware_sets/vocab.py
git commit -m "feat: add manufacturer/finish vocab and helpers"
```

---

## Task 4: `filter.py` — schedule region detection

Implements spec §4.1. Single scan over pdftotext page output, tracking start/end markers.

**Files:**
- Create: `src/hardware_sets/filter.py`

- [ ] **Step 1: Write `filter.py`**

```python
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
            name = _match_start(text) or ("heuristic" if _heuristic_start(text) else None)
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
            if name:
                in_region = True
                start_page = page
                start_marker = name
                region_section = page_section

    if in_region:
        regions.append(ScheduleRegion(start_page, total, start_marker, "eof"))
    return regions
```

- [ ] **Step 2: Quick import check**

Run: `.venv/bin/python -c "from hardware_sets.filter import find_schedule_regions; print(find_schedule_regions.__doc__)"`
Expected: prints the docstring.

- [ ] **Step 3: Commit**

```bash
git add src/hardware_sets/filter.py
git commit -m "feat(filter): find schedule regions via start/end markers"
```

---

## Task 5: `filter.py` — pytest for pattern matching

The spec explicitly says "no formal test suite" but allows small pytest for pure-logic modules. Pattern matching is pure logic; 8 assertions in one file are cheap.

**Files:**
- Create: `tests/test_filter_patterns.py`

- [ ] **Step 1: Write the tests**

```python
"""Tests for filter.py pattern-matching helpers — pure string logic.

Covers the spec §4.1 start/end markers against realistic line snippets.
No PDF fixtures — those live in the sample-run script.
"""

from hardware_sets.filter import (
    _match_start,
    _heuristic_start,
    _current_section,
    END_OF_SECTION_RE,
)


def test_start_door_hardware_schedule():
    assert _match_start("DOOR HARDWARE SCHEDULE") == "door_hardware_schedule"


def test_start_hardware_sets_colon():
    assert _match_start("D. Hardware Sets:") == "hardware_sets_colon"


def test_start_schedule_section_3dot():
    assert _match_start("   3.01 SCHEDULE") == "schedule_section_3dot"


def test_start_group_1():
    assert _match_start("Hardware Group No. 01") == "group_1"
    assert _match_start("Hardware Set #1") == "group_1"


def test_start_no_match_on_narrative():
    assert _match_start("Hardware sets are indicated on Drawings.") is None


def test_end_of_section():
    assert END_OF_SECTION_RE.search("  END OF SECTION  ")


def test_current_section():
    assert _current_section("SECTION 08 71 00 — DOOR HARDWARE") == "087100"
    assert _current_section("SECTION 087100") == "087100"
    assert _current_section("hello world") is None


def test_heuristic_fallback_fires_on_three_signals():
    # bare SET token, QTY column, known mfr (SCH)
    text = "SET 1\n\nQTY  DESCRIPTION  MFR\n 1   Hinge        SCH"
    assert _heuristic_start(text)


def test_heuristic_does_not_fire_on_narrative():
    # Narrative paragraph with no SET/QTY/vocab signals
    assert not _heuristic_start(
        "The hardware sets specified in this section shall comply with the project requirements."
    )
```

- [ ] **Step 2: Run the tests**

Run: `.venv/bin/pytest tests/test_filter_patterns.py -v`
Expected: all 9 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_filter_patterns.py
git commit -m "test(filter): cover start/end marker patterns"
```

---

## Task 6: `filter.py` — smoke test on every sample PDF

Quick manual-eyeball check that region detection fires on real samples.

- [ ] **Step 1: Write an ad-hoc smoke script**

Create: `scripts/smoke_filter.py`

```python
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
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/python scripts/smoke_filter.py`
Expected: every sample PDF reports ≥1 region; regions land near the end of each PDF (hardware schedules are in the last 5–15 pages per spec §2). Note any PDF that reports 0 regions or a region spanning the entire PDF — those are signals to revisit patterns.

- [ ] **Step 3: If a sample reports 0 regions**

Open the sample with `pdftotext -layout <pdf> - | less`, find the actual schedule lead-in, and extend `START_PATTERNS` in `filter.py` with a named pattern that matches it. Re-run the smoke script. Commit the addition separately:

```bash
git add src/hardware_sets/filter.py tests/test_filter_patterns.py
git commit -m "fix(filter): cover <layout-name> lead-in"
```

- [ ] **Step 4: Commit the smoke script**

```bash
git add scripts/smoke_filter.py
git commit -m "chore(scripts): smoke-check filter.py on samples"
```

---

## Task 7: `layout.py` — numbered-line page extraction

Implements spec §4.2. One path: `pdftotext -layout` per page, drop blank lines, renumber contiguously.

**Files:**
- Create: `src/hardware_sets/layout.py`

- [ ] **Step 1: Write `layout.py`**

```python
"""Render one PDF page into a list of numbered lines for the LLM.

See spec §4.2. Blank lines are dropped; `L##` stays contiguous so a
human (or the LLM) can count lines in the rendered text and match
`location.line_range` back to the source PDF.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from hardware_sets.types import NumberedLine, PageLayout


def extract_layout(pdf_path: Path, page_num: int) -> PageLayout:
    """Return a PageLayout for 1-indexed `page_num` of `pdf_path`."""
    result = subprocess.run(
        ["pdftotext", "-layout", "-f", str(page_num), "-l", str(page_num), str(pdf_path), "-"],
        capture_output=True, text=True, check=False,
    )
    raw = result.stdout or ""

    lines: list[NumberedLine] = []
    counter = 1
    for raw_line in raw.splitlines():
        if not raw_line.strip():
            continue
        lines.append(NumberedLine(number=counter, text=raw_line.rstrip()))
        counter += 1

    return PageLayout(page_number=page_num, lines=lines)


def render_for_prompt(layout: PageLayout) -> str:
    """Render a PageLayout as the `=== PAGE N === / L01: ...` block the prompt uses."""
    header = f"=== PAGE {layout.page_number} ==="
    body = "\n".join(f"L{line.number:02d}: {line.text}" for line in layout.lines)
    return f"{header}\n{body}"
```

- [ ] **Step 2: Smoke check on one page**

Pick the first schedule page of one sample. Run:

```bash
.venv/bin/python -c "
from pathlib import Path
from hardware_sets.layout import extract_layout, render_for_prompt
pdf = Path('samples/div_08_Schulz.pdf')
layout = extract_layout(pdf, 20)  # adjust page if needed after filter smoke
print(f'{len(layout.lines)} lines on page {layout.page_number}')
print(render_for_prompt(layout)[:1000])
"
```

Expected: prints a page header plus ~30-80 numbered lines. Visually check against the PDF that the first/last rendered lines correspond to the topmost/bottommost visible text on the page. Adjust page number if the chosen one is blank/chrome-only.

- [ ] **Step 3: Commit**

```bash
git add src/hardware_sets/layout.py
git commit -m "feat(layout): render PDF pages as numbered lines"
```

---

## Task 8: `extract.py` — constants (system prompt + tool schema)

Split the `extract.py` module into two tasks so the prompt + schema are pinned before the runtime loop is built.

**Files:**
- Create: `src/hardware_sets/extract.py`

- [ ] **Step 1: Draft system prompt constant**

```python
"""LLM-driven structured extraction of hardware sets.

See spec §4.3. System prompt is cached via `cache_control: ephemeral`
so the vocabulary block is paid for once per run, not per region.
"""

from __future__ import annotations

# The system prompt is cached. Keep it stable — any tweak busts the cache.
SYSTEM_PROMPT = """\
You extract door hardware sets from construction specification books.

A hardware set is a named group of components (hinges, locksets, closers, etc.)
assigned to doors. The user will send one or more pages of rendered PDF text,
with every non-blank line prefixed `Lnn:`. Your job is to emit, for each set
you can see, the set number, description, the first and last line numbers the
set occupies, and the components with their fields (qty, description, catalog
number, manufacturer, finish, notes).

Known manufacturer vocabulary (these are legitimate mfr values; extend as
needed but prefer these canonical forms when a match is obvious):
IVE/IVES, VON/Von Duprin, SCH/SCHLAGE/Schlage, LCN, NGP, ZER/Zero,
PEM/Pemko, ROC/Rockwood, GLY/Glynn-Johnson, HAG/Hager, ADA/Adams Rite,
TRI/Trimco/BBW, ABH, MED/Medeco, SEN/Sentronic, ASS/Assa Abloy,
SCE/Securitron, BLU/Blumcraft, CRL/C.R. Laurence, KNX/Knox, RIX/Rixson,
NOR/Norton.

Known finish vocabulary:
BHMA three-digit codes 600-695 (notably 613, 626, 630, 652, 689),
US codes (US3, US4, US10, US26, US26D, US32D),
color words (BLACK, BSP, PAINTED ENAMEL, OIL RUBBED BRONZE, LIGHT BRONZE).

Disambiguation rule: resolve mfr vs finish by looking at the whole column,
not individual tokens. A column mostly containing MK/LCN/SCH is a manufacturer
column; one with US26D/630/BSP is a finish column. Codes like "PE" (Pemko vs
Painted Enamel) and "NO" (Norton vs the word "No.") follow column context.

Nulls and edges:
- Emit qty: null rather than guessing when absent.
- A set marked NOT USED, N/A, or similar is emitted with empty components
  and is_not_used: true; preserve the literal heading as the description.
- Ignore page headers/footers, project titles, and CSI section markers —
  those are page chrome, not set content.

Line-citing rule: for each set, cite the first and last line that belong
to it. If the set spans a page break, emit `continued_on` entries for
each additional page and its first/last lines on that page.
"""
```

- [ ] **Step 2: Add the tool schema**

Append to the same file:

```python
EMIT_HARDWARE_SETS_TOOL: dict = {
    "name": "emit_hardware_sets",
    "description": "Emit every hardware set visible in the provided pages.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sets": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "set_number": {"type": "string"},
                        "description": {"type": ["string", "null"]},
                        "location": {
                            "type": "object",
                            "properties": {
                                "page": {"type": "integer"},
                                "line_range": {
                                    "type": "array",
                                    "items": {"type": "integer"},
                                    "minItems": 2,
                                    "maxItems": 2,
                                },
                            },
                            "required": ["page", "line_range"],
                        },
                        "continued_on": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "page": {"type": "integer"},
                                    "line_range": {
                                        "type": "array",
                                        "items": {"type": "integer"},
                                        "minItems": 2,
                                        "maxItems": 2,
                                    },
                                },
                                "required": ["page", "line_range"],
                            },
                        },
                        "is_not_used": {"type": "boolean"},
                        "components": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "qty": {"type": ["integer", "null"]},
                                    "description": {"type": ["string", "null"]},
                                    "catalog_number": {"type": ["string", "null"]},
                                    "mfr": {"type": ["string", "null"]},
                                    "finish": {"type": ["string", "null"]},
                                    "notes": {"type": ["string", "null"]},
                                },
                                "required": ["qty", "description", "catalog_number", "mfr", "finish", "notes"],
                            },
                        },
                    },
                    "required": ["set_number", "description", "location", "continued_on", "is_not_used", "components"],
                },
            }
        },
        "required": ["sets"],
    },
}
```

- [ ] **Step 3: Import check**

Run: `.venv/bin/python -c "from hardware_sets.extract import SYSTEM_PROMPT, EMIT_HARDWARE_SETS_TOOL; print(len(SYSTEM_PROMPT), EMIT_HARDWARE_SETS_TOOL['name'])"`
Expected: prints roughly `(1500..2500, 'emit_hardware_sets')`.

- [ ] **Step 4: Commit**

```bash
git add src/hardware_sets/extract.py
git commit -m "feat(extract): pin system prompt and tool schema"
```

---

## Task 9: `extract.py` — extract_sets runtime loop

Implements spec §4.3 request/response handling, caching, retry.

**Files:**
- Modify: `src/hardware_sets/extract.py` (append)

- [ ] **Step 1: Add the runtime code**

Append:

```python
import json
import logging
from dataclasses import asdict

from anthropic import Anthropic, APIStatusError

from hardware_sets.layout import render_for_prompt
from hardware_sets.types import (
    Component,
    HardwareSet,
    PageLayout,
    ScheduleRegion,
    SetLocation,
)

log = logging.getLogger(__name__)


class ExtractionError(RuntimeError):
    """LLM returned something we couldn't parse even after a retry."""


DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8000


def _build_user_content(region: ScheduleRegion, layouts: list[PageLayout]) -> str:
    header = (
        f"Schedule region: pages {region.start_page}-{region.end_page} "
        f"(entered via {region.start_marker}).\n\n"
    )
    return header + "\n\n".join(render_for_prompt(lay) for lay in layouts)


def _coerce_sets(tool_input: dict) -> list[HardwareSet]:
    """Convert the tool-use JSON into HardwareSet dataclasses."""
    out: list[HardwareSet] = []
    for s in tool_input.get("sets", []):
        loc = SetLocation(page=s["location"]["page"],
                         line_range=tuple(s["location"]["line_range"]))  # type: ignore[arg-type]
        cont = [
            SetLocation(page=c["page"], line_range=tuple(c["line_range"]))  # type: ignore[arg-type]
            for c in s.get("continued_on", [])
        ]
        components = [
            Component(
                qty=c.get("qty"),
                description=c.get("description"),
                catalog_number=c.get("catalog_number"),
                mfr=c.get("mfr"),
                finish=c.get("finish"),
                notes=c.get("notes"),
            )
            for c in s.get("components", [])
        ]
        out.append(
            HardwareSet(
                set_number=s["set_number"],
                description=s.get("description"),
                location=loc,
                continued_on=cont,
                is_not_used=bool(s.get("is_not_used", False)),
                components=components,
            )
        )
    return out


def _call_model(
    client: Anthropic,
    model: str,
    user_content: str,
    retry_note: str | None = None,
) -> list[HardwareSet]:
    system_blocks = [
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }
    ]
    user_blocks: list[dict] = [{"type": "text", "text": user_content}]
    if retry_note:
        user_blocks.append({
            "type": "text",
            "text": f"\nNOTE: your previous response failed validation: {retry_note}. "
                    f"Re-emit correctly.",
        })

    resp = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=system_blocks,
        tools=[EMIT_HARDWARE_SETS_TOOL],
        tool_choice={"type": "tool", "name": EMIT_HARDWARE_SETS_TOOL["name"]},
        messages=[{"role": "user", "content": user_blocks}],
    )

    for block in resp.content:
        if block.type == "tool_use" and block.name == EMIT_HARDWARE_SETS_TOOL["name"]:
            try:
                return _coerce_sets(block.input)
            except (KeyError, TypeError, ValueError) as e:
                raise ExtractionError(f"tool_use payload malformed: {e}") from e
    raise ExtractionError("model did not call emit_hardware_sets")


def extract_sets(
    region: ScheduleRegion,
    layouts: list[PageLayout],
    *,
    model: str = DEFAULT_MODEL,
    client: Anthropic | None = None,
) -> list[HardwareSet]:
    """Extract every hardware set from `region` (see spec §4.3)."""
    if client is None:
        client = Anthropic()

    user_content = _build_user_content(region, layouts)

    try:
        return _call_model(client, model, user_content)
    except ExtractionError as e:
        log.warning("extract_sets: first attempt failed (%s); retrying once", e)
        try:
            return _call_model(client, model, user_content, retry_note=str(e))
        except ExtractionError:
            raise
    # APIStatusError and other SDK errors bubble up to the caller (cli exits 3).
```

- [ ] **Step 2: Import check**

Run: `.venv/bin/python -c "from hardware_sets.extract import extract_sets, ExtractionError; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add src/hardware_sets/extract.py
git commit -m "feat(extract): implement extract_sets with prompt caching and retry"
```

---

## Task 10: `extract.py` — large-region chunking guard

Spec §4.3 "Batching": chunk at 20-page boundaries with 2-page overlap when the region's input would exceed ~80K tokens.

**Files:**
- Modify: `src/hardware_sets/extract.py`

- [ ] **Step 1: Add a helper `_chunk_layouts`**

Append:

```python
TOKEN_CHUNK_THRESHOLD = 80_000
CHUNK_PAGES = 20
CHUNK_OVERLAP = 2


def _estimated_tokens(user_content: str) -> int:
    # Cheap char-based estimate; Anthropic exposes real token counting but
    # the char heuristic is precise enough at our scale (~4 chars/token).
    return len(user_content) // 4


def _chunk_layouts(layouts: list[PageLayout]) -> list[list[PageLayout]]:
    """Break `layouts` into 20-page windows with 2-page overlap."""
    if len(layouts) <= CHUNK_PAGES:
        return [layouts]
    chunks: list[list[PageLayout]] = []
    step = CHUNK_PAGES - CHUNK_OVERLAP
    for i in range(0, len(layouts), step):
        chunks.append(layouts[i:i + CHUNK_PAGES])
        if i + CHUNK_PAGES >= len(layouts):
            break
    return chunks


def _dedup_sets(sets: list[HardwareSet]) -> list[HardwareSet]:
    """Drop duplicates (same set_number + first_page) introduced by overlap."""
    seen: dict[tuple[str, int], HardwareSet] = {}
    for s in sets:
        key = (s.set_number, s.location.page)
        if key not in seen:
            seen[key] = s
    return list(seen.values())
```

- [ ] **Step 2: Wire chunking into `extract_sets`**

Replace the body of `extract_sets` with:

```python
def extract_sets(
    region: ScheduleRegion,
    layouts: list[PageLayout],
    *,
    model: str = DEFAULT_MODEL,
    client: Anthropic | None = None,
) -> list[HardwareSet]:
    if client is None:
        client = Anthropic()

    combined = _build_user_content(region, layouts)
    if _estimated_tokens(combined) <= TOKEN_CHUNK_THRESHOLD:
        batches = [layouts]
    else:
        batches = _chunk_layouts(layouts)

    collected: list[HardwareSet] = []
    for batch in batches:
        user_content = _build_user_content(region, batch)
        try:
            collected.extend(_call_model(client, model, user_content))
        except ExtractionError as e:
            log.warning("extract_sets: batch retry after %s", e)
            collected.extend(_call_model(client, model, user_content, retry_note=str(e)))
    return _dedup_sets(collected)
```

- [ ] **Step 3: Import check**

Run: `.venv/bin/python -c "from hardware_sets.extract import _chunk_layouts, _dedup_sets, TOKEN_CHUNK_THRESHOLD; print(TOKEN_CHUNK_THRESHOLD)"`
Expected: `80000`.

- [ ] **Step 4: Commit**

```bash
git add src/hardware_sets/extract.py
git commit -m "feat(extract): chunk oversized regions with overlap + dedup"
```

---

## Task 11: `extract.py` — single-region smoke test

Verify the LLM path end-to-end against one known sample page region. Costs ~$0.005 per run.

- [ ] **Step 1: Write an ad-hoc smoke script**

Create: `scripts/smoke_extract.py`

```python
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
```

- [ ] **Step 2: Run it**

Run: `ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY .venv/bin/python scripts/smoke_extract.py`
Expected: JSON with at least one set, each set has `set_number`, `location.page`, `location.line_range`, `components`. Eyeball 1–2 sets against the PDF to confirm the line range is close.

- [ ] **Step 3: Commit**

```bash
git add scripts/smoke_extract.py
git commit -m "chore(scripts): smoke-check extract.py on one region"
```

---

## Task 12: `resolve.py` — vocabulary-match confidence scoring

Implements spec §4.4. Purely additive, no PDF reads, no LLM calls.

**Files:**
- Create: `src/hardware_sets/resolve.py`

- [ ] **Step 1: Write `resolve.py`**

```python
"""Vocabulary-match confidence scoring for LLM-extracted sets.

See spec §4.4. **Never auto-corrects** — only annotates each field and
each set with a confidence number so a downstream UI can sort
"look at this first" items. Measures 'does the extracted value match
known vocabulary', not 'is the extraction correct'.
"""

from __future__ import annotations

from statistics import mean

from hardware_sets.types import Component, HardwareSet
from hardware_sets.vocab import (
    GLOBAL_FINISH_VOCAB,
    GLOBAL_MFR_VOCAB,
    MFR_SHORTCODE_RE,
    looks_like_finish,
    looks_like_mfr_code,
    norm,
)


def _score_mfr(value: str | None) -> float:
    if value is None:
        return 1.0
    v = norm(value) or ""
    if v in GLOBAL_MFR_VOCAB:
        return 1.0
    if looks_like_finish(v):
        return 0.2            # looks like a finish — swap risk
    if MFR_SHORTCODE_RE.match(v):
        return 0.7            # plausible short code not in vocab
    return 0.5


def _score_finish(value: str | None) -> float:
    if value is None:
        return 1.0
    v = norm(value) or ""
    if v in GLOBAL_FINISH_VOCAB:
        return 1.0
    if looks_like_finish(v):
        return 0.9
    if looks_like_mfr_code(v):
        return 0.2            # looks like a mfr — swap risk
    return 0.5


def _score_qty(value: int | None) -> float:
    return 1.0


def _score_component(comp: Component) -> Component:
    comp.confidence = {
        "mfr": _score_mfr(comp.mfr),
        "finish": _score_finish(comp.finish),
        "qty": _score_qty(comp.qty),
    }
    return comp


def _component_min(conf: dict[str, float]) -> float:
    return min(conf.values()) if conf else 1.0


def validate_and_score(sets: list[HardwareSet]) -> list[HardwareSet]:
    """Annotate every component with per-field confidences and every set with a mean."""
    for hw_set in sets:
        if hw_set.is_not_used or not hw_set.components:
            hw_set.confidence = 1.0
            continue
        for comp in hw_set.components:
            _score_component(comp)
        hw_set.confidence = mean(_component_min(c.confidence) for c in hw_set.components)
    return sets
```

- [ ] **Step 2: Import check**

Run: `.venv/bin/python -c "from hardware_sets.resolve import validate_and_score; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add src/hardware_sets/resolve.py
git commit -m "feat(resolve): per-field vocab-match confidence scoring"
```

---

## Task 13: `resolve.py` — pytest for scoring

**Files:**
- Create: `tests/test_resolve_scoring.py`

- [ ] **Step 1: Write the tests**

```python
"""Tests for resolve.py confidence scoring (pure logic)."""

from hardware_sets.resolve import validate_and_score
from hardware_sets.types import Component, HardwareSet, SetLocation


def _set(components: list[Component], *, is_not_used: bool = False) -> HardwareSet:
    return HardwareSet(
        set_number="1",
        description=None,
        location=SetLocation(page=1, line_range=(1, 10)),
        components=components,
        is_not_used=is_not_used,
    )


def _c(**kw) -> Component:
    defaults = dict(qty=1, description=None, catalog_number=None, mfr=None,
                    finish=None, notes=None)
    defaults.update(kw)
    return Component(**defaults)


def test_known_mfr_and_finish_score_high():
    s = _set([_c(mfr="SCH", finish="626")])
    [out] = validate_and_score([s])
    c = out.components[0]
    assert c.confidence["mfr"] == 1.0
    assert c.confidence["finish"] == 1.0
    assert out.confidence == 1.0


def test_mfr_that_looks_like_finish_scores_low():
    s = _set([_c(mfr="626", finish="SCH")])
    [out] = validate_and_score([s])
    c = out.components[0]
    assert c.confidence["mfr"] == 0.2
    assert c.confidence["finish"] == 0.2


def test_unknown_shortcode_mfr_plausible():
    s = _set([_c(mfr="XYZ", finish="US26D")])
    [out] = validate_and_score([s])
    c = out.components[0]
    assert c.confidence["mfr"] == 0.7
    assert c.confidence["finish"] == 1.0


def test_bhma_pattern_scores_finish_090():
    # 691 is in the US/BHMA range but (deliberately) also in our vocab.
    # Pick a BHMA code NOT in the vocab to hit the 0.9 branch.
    s = _set([_c(mfr="SCH", finish="615")])
    [out] = validate_and_score([s])
    assert out.components[0].confidence["finish"] == 0.9


def test_null_fields_score_full():
    s = _set([_c(mfr=None, finish=None)])
    [out] = validate_and_score([s])
    c = out.components[0]
    assert c.confidence["mfr"] == 1.0
    assert c.confidence["finish"] == 1.0


def test_not_used_set_confidence_is_one():
    s = _set([], is_not_used=True)
    [out] = validate_and_score([s])
    assert out.confidence == 1.0


def test_set_confidence_is_mean_of_component_mins():
    s = _set([
        _c(mfr="SCH", finish="626"),   # min 1.0
        _c(mfr="626", finish="SCH"),   # min 0.2
    ])
    [out] = validate_and_score([s])
    assert out.confidence == (1.0 + 0.2) / 2
```

- [ ] **Step 2: Run the tests**

Run: `.venv/bin/pytest tests/test_resolve_scoring.py -v`
Expected: all 7 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_resolve_scoring.py
git commit -m "test(resolve): cover confidence scoring"
```

---

## Task 14: `cli.py` — orchestration + argparse + exit codes

Implements spec §4.5.

**Files:**
- Create: `src/hardware_sets/cli.py`

- [ ] **Step 1: Write `cli.py`**

```python
"""Command-line entry point (spec §4.5)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict
from pathlib import Path

from pypdf import PdfReader

from hardware_sets import filter as filter_mod
from hardware_sets import layout as layout_mod
from hardware_sets import resolve as resolve_mod
from hardware_sets import extract as extract_mod
from hardware_sets.types import HardwareSet

log = logging.getLogger("hardware_sets")


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="hardware-sets", description="Extract door hardware sets from a specbook PDF.")
    p.add_argument("pdf_path", type=Path, help="PDF file to extract from")
    p.add_argument("-o", "--out", type=Path, default=None, help="Output JSON path (default: stdout)")
    p.add_argument("--model", default=extract_mod.DEFAULT_MODEL, help="Anthropic model id")
    p.add_argument("--no-score", action="store_true", help="Skip resolve.py confidence scoring")
    p.add_argument("--quiet", action="store_true", help="Suppress progress logs")
    return p.parse_args(argv)


def _setup_logging(quiet: bool) -> None:
    level = logging.WARNING if quiet else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        stream=sys.stderr,
    )


def _page_count(pdf: Path) -> int:
    return len(PdfReader(str(pdf)).pages)


def _emit(result: dict, out: Path | None) -> None:
    text = json.dumps(result, indent=2, default=str)
    if out:
        out.write_text(text + "\n")
    else:
        print(text)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    _setup_logging(args.quiet)

    if not args.pdf_path.is_file():
        print(f"error: pdf not found: {args.pdf_path}", file=sys.stderr)
        return 1
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: ANTHROPIC_API_KEY is not set", file=sys.stderr)
        return 1

    total_pages = _page_count(args.pdf_path)

    log.info("[1/3] filter: scanning %d pages of %s", total_pages, args.pdf_path.name)
    regions = filter_mod.find_schedule_regions(args.pdf_path)
    if not regions:
        log.warning("no schedule region found")
        _emit(
            {
                "source_pdf": args.pdf_path.name,
                "hardware_sets": [],
                "diagnostics": {
                    "pages_scanned": total_pages,
                    "regions_found": 0,
                    "pages_with_sets": 0,
                    "llm_calls": 0,
                    "warnings": ["no_schedule_found"],
                },
            },
            args.out,
        )
        return 2

    log.info("[1/3] filter: found %d region(s): %s",
             len(regions), ", ".join(f"pgs {r.start_page}-{r.end_page}" for r in regions))

    all_sets: list[HardwareSet] = []
    warnings: list[str] = []
    llm_calls = 0

    for i, region in enumerate(regions, start=1):
        log.info("[2/3] extract: region %d/%d pages %d-%d", i, len(regions), region.start_page, region.end_page)
        layouts = [
            layout_mod.extract_layout(args.pdf_path, p)
            for p in range(region.start_page, region.end_page + 1)
        ]
        try:
            sets = extract_mod.extract_sets(region, layouts, model=args.model)
            llm_calls += 1
            log.info("[2/3] extract: region %d/%d -> %d set(s)", i, len(regions), len(sets))
            all_sets.extend(sets)
        except extract_mod.ExtractionError as e:
            warnings.append(f"region {region.start_page}-{region.end_page}: {e}")
            log.warning("extract failed for region %d-%d: %s", region.start_page, region.end_page, e)
        except Exception as e:  # network / API / anything else
            log.error("unrecoverable error calling model: %s", e)
            return 3

    if not args.no_score:
        log.info("[3/3] resolve: scoring %d set(s)", len(all_sets))
        all_sets = resolve_mod.validate_and_score(all_sets)

    result = {
        "source_pdf": args.pdf_path.name,
        "hardware_sets": [asdict(s) for s in all_sets],
        "diagnostics": {
            "pages_scanned": total_pages,
            "regions_found": len(regions),
            "pages_with_sets": sum(r.end_page - r.start_page + 1 for r in regions),
            "llm_calls": llm_calls,
            "warnings": warnings,
        },
    }
    _emit(result, args.out)
    return 0


def main_entry() -> None:
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 2: Arg parsing sanity**

Run: `.venv/bin/python -m hardware_sets --help`
Expected: usage text listing `pdf_path`, `--out`, `--model`, `--no-score`, `--quiet`.

Run: `.venv/bin/python -m hardware_sets /nonexistent.pdf`
Expected: stderr `error: pdf not found: /nonexistent.pdf`, exit 1.

- [ ] **Step 3: Missing key check**

Run: `env -u ANTHROPIC_API_KEY .venv/bin/python -m hardware_sets samples/div_08_Schulz.pdf`
Expected: stderr `error: ANTHROPIC_API_KEY is not set`, exit 1.

- [ ] **Step 4: Commit**

```bash
git add src/hardware_sets/cli.py
git commit -m "feat(cli): orchestrate pipeline with exit codes and progress logs"
```

---

## Task 15: Full-pipeline smoke test on one sample

- [ ] **Step 1: Run the CLI on a small sample**

Pick one of the smaller sample PDFs — `div_08_Schulz.pdf` or `div_08_1.pdf` is typical. Run:

```bash
.venv/bin/python -m hardware_sets samples/div_08_Schulz.pdf --out out/schulz.json
```

Expected:
- exit 0
- stderr shows 3 progress lines
- `out/schulz.json` exists with:
  - `hardware_sets` list ≥1 entry
  - each set has `set_number`, `location.page`, `location.line_range`
  - each component has `qty`/`description`/`mfr`/`finish`/`confidence`
  - `diagnostics.llm_calls >= 1`

- [ ] **Step 2: Eyeball 2-3 sets against the PDF**

Open the PDF at the page each sampled set cites. Confirm:
- the `line_range` lands within ~2 lines of the rendered set boundaries (counting non-blank lines from the top)
- the mfr/finish pairings look right
- confidence scores are ≥ 0.7 for the common cases, lower only when genuinely ambiguous

- [ ] **Step 3: If problems — fix and commit**

If a field is consistently wrong (e.g., mfr/finish swapped in a specific layout), tweak `SYSTEM_PROMPT` in `extract.py`. Re-run. Commit the tweak with a message describing what the prompt edit addressed.

If line ranges are consistently off-by-N, check `layout.py` — most likely cause is a pre-schedule page with an unusual line count bumping the expectations (the LLM cites lines relative to each rendered page, which the layout numbering resets — so the issue is usually just the eyeball arithmetic, not a bug).

- [ ] **Step 4: No commit needed unless changes were made above**

---

## Task 16: `scripts/run_samples.py` — batch QA harness

Spec §8 lists this as "the QA artifact". Drives the demo-video recording.

**Files:**
- Create: `scripts/run_samples.py`

- [ ] **Step 1: Write the script**

```python
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
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/python scripts/run_samples.py`
Expected: one JSON per sample PDF under `out/`, a summary printed to stdout + written to `out/_summary.txt`. Total cost under ~$0.20 per full run (spec §10).

- [ ] **Step 3: Eyeball the summary**

Check `out/_summary.txt`. Every sample should have `exit=0` and a nonzero set count. Any exit=2 PDF is either a scanned-only file (acceptable) or a new-layout that needs a new start marker — investigate and add a pattern to `filter.py` if the latter.

- [ ] **Step 4: Commit**

```bash
git add scripts/run_samples.py
git commit -m "chore(scripts): batch QA harness over every sample PDF"
```

---

## Task 17: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# Hardware Sets — Division 08 Specbook Extractor

Extracts every door-hardware set from a construction Division 08 (Openings)
specbook PDF into structured JSON, including the page + line range where each
set lives.

## Setup

Requires Python 3.12+, Poppler's `pdftotext`, and an Anthropic API key.

```bash
# Poppler on macOS
brew install poppler

# Python deps (uses the repo's .venv)
.venv/bin/pip install -e ".[dev]"

export ANTHROPIC_API_KEY=sk-ant-...
```

## Run

```bash
.venv/bin/python -m hardware_sets path/to/specbook.pdf --out result.json
```

Flags:

| Flag | Default | Purpose |
|---|---|---|
| `pdf_path` | required | PDF to extract from |
| `--out` / `-o` | stdout | Where to write JSON |
| `--model` | `claude-sonnet-4-6` | Anthropic model id |
| `--no-score` | off | Skip vocabulary-match confidence scoring |
| `--quiet` | off | Suppress progress logs |

Exit codes: `0` success, `1` usage error / missing key, `2` no schedule
region found (includes scanned-only PDFs), `3` unrecoverable API error.

## Batch QA

```bash
.venv/bin/python scripts/run_samples.py
```

Runs the extractor against every PDF under `samples/`, writing one JSON per
PDF to `out/<stem>.json` plus `out/_summary.txt`.

## Architecture

Five-module pipeline under `src/hardware_sets/`:

- `filter.py` — locates contiguous schedule region(s) within the PDF (spec §4.1)
- `layout.py` — renders each page as a list of numbered lines via `pdftotext -layout` (§4.2)
- `extract.py` — one prompt-cached Claude Sonnet 4.6 call per region, emitting structured sets through a tool schema (§4.3)
- `resolve.py` — post-hoc vocabulary-match confidence scoring (§4.4). Never auto-corrects.
- `cli.py` — argparse + pipeline + JSON output (§4.5)

`types.py` and `vocab.py` are shared constants.

## Confidence scoring — what it means

A `confidence` field below 1.0 means "this value didn't exactly match our
built-in vocabulary." For finish codes that signal is reliable — BHMA codes
and `USnn[DL]?` patterns are ANSI-standard. For manufacturer short codes it's
weaker: each project uses its own legend (e.g., `IVE` vs `IVES`), so a
confidence below 0.7 on `mfr` could mean "real LLM error" or "legitimate
project-specific abbreviation we haven't seen yet." Review low-confidence
mfr values rather than trusting the drop.

## Tests

```bash
.venv/bin/pytest
```

Two small suites: `tests/test_filter_patterns.py` covers start/end marker
regex, `tests/test_resolve_scoring.py` covers confidence scoring. LLM
behavior is validated by running `scripts/run_samples.py` and eyeballing the
output, per spec §8.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README covering setup, run, architecture, scoring"
```

---

## Task 18: Final verification

- [ ] **Step 1: Run the full test suite**

Run: `.venv/bin/pytest -v`
Expected: all tests pass (`tests/test_filter_patterns.py` + `tests/test_resolve_scoring.py`).

- [ ] **Step 2: Fresh batch run**

Run: `.venv/bin/python scripts/run_samples.py`
Expected: every sample exits 0 with a nonzero `sets` count OR is a documented scanned-only case.

- [ ] **Step 3: Review `out/_summary.txt`**

- Sets extracted per sample match rough expectations (spec §2: 5–30 sets typical).
- Any sample reporting 0 sets or exit 2 is either:
  - a non-hardware Division 08 file (e.g., `088000-GLAZING*.pdf`) — acceptable, note in README
  - a scanned PDF (acceptable, noted in JSON warnings)
  - a layout we haven't covered — file an issue or add a start marker.

- [ ] **Step 4: Record demo material**

Note which 2-3 PDFs show off the pipeline best — typically one bordered
(Roselle-style), one list (Shubenacadie-style), one with legend (Schulz-style).
These are the ones to walk through in the demo video.

- [ ] **Step 5: Final commit / push**

```bash
git status  # should be clean
git log --oneline | head -20
```

If any drift remains, commit with a `chore: final cleanup` message.
