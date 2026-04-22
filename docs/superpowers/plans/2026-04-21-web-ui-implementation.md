# Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap the existing Python hardware-sets extractor in a streaming FastAPI backend (Fly.io) and a Next.js + Blueprint-themed frontend (Vercel) that lets a reviewer drag-drop a specbook PDF, watch extraction stream live, edit results inline alongside a bbox-highlighted PDF pane, and export corrected JSON.

**Architecture:** Monorepo with three trees — existing `src/hardware_sets/` (untouched except for bbox additions), new `src/hardware_sets_api/` (FastAPI wrapper that imports the pipeline), and new `frontend/` (Next.js 15 app). The single load-bearing pipeline change is adding per-line pixel bboxes via pdfplumber word clustering, surfaced on `Location.bbox`. Backend streams typed SSE events; frontend consumes them incrementally.

**Tech Stack:** Python 3.12 · FastAPI · pdfplumber · `anthropic` SDK · Next.js 15 · TypeScript · Tailwind · `react-pdf` · vitest · pytest · Docker · Fly.io · Vercel

---

## File plan

**New backend files:**
- `src/hardware_sets_api/__init__.py`
- `src/hardware_sets_api/main.py` — FastAPI app, CORS, endpoints
- `src/hardware_sets_api/session.py` — in-memory PDF cache with TTL
- `src/hardware_sets_api/sse.py` — SSE streaming generator + event helpers
- `tests/test_layout_bbox.py` — pdfplumber word-clustering unit test
- `Dockerfile` — poppler + Python image for Fly.io
- `fly.toml` — Fly app config
- `.dockerignore`

**New frontend files:**
- `frontend/package.json`, `frontend/tsconfig.json`, `frontend/next.config.mjs`, `frontend/tailwind.config.ts`, `frontend/postcss.config.mjs`, `frontend/.env.local.example`
- `frontend/app/layout.tsx` — root layout, font loading
- `frontend/app/globals.css` — Blueprint tokens
- `frontend/app/page.tsx` — landing
- `frontend/app/extract/page.tsx` — streaming results + editor
- `frontend/app/components/BlueprintChrome.tsx`
- `frontend/app/components/DropZone.tsx`
- `frontend/app/components/StreamLog.tsx`
- `frontend/app/components/SetCard.tsx`
- `frontend/app/components/ComponentRow.tsx`
- `frontend/app/components/ConfidenceBadge.tsx`
- `frontend/app/components/EvidencePane.tsx`
- `frontend/app/components/EvidenceTextTab.tsx`
- `frontend/app/components/ExportMenu.tsx`
- `frontend/app/components/ErrorPanel.tsx`
- `frontend/lib/types.ts`
- `frontend/lib/sse.ts`
- `frontend/lib/storage.ts`
- `frontend/lib/corrections.ts`
- `frontend/lib/corrections.test.ts`
- `frontend/lib/hashPdf.ts`

**Modified existing files:**
- `src/hardware_sets/types.py` — add optional `bbox` to `NumberedLine` and `SetLocation`; add `page_width`/`page_height` to `PageLayout`
- `src/hardware_sets/layout.py` — attach bboxes via pdfplumber
- `src/hardware_sets/cli.py` — populate `SetLocation.bbox` from line_range union
- `pyproject.toml` — add FastAPI + uvicorn + pdfplumber (already present) deps and new optional-extra for `api`
- `README.md` — dev + deploy instructions for both platforms
- `.gitignore` — add `frontend/node_modules/`, `frontend/.next/`, `frontend/out/`

---

# Phase 1 — Backend: bbox extraction

Aim: `SetLocation.bbox` populated end-to-end, covered by one unit test, with existing JSON output staying backward-compatible.

## Task 1: Extend dataclasses with optional bbox fields

**Files:**
- Modify: `src/hardware_sets/types.py`

- [ ] **Step 1: Add `BBox` type alias and extend three dataclasses**

Replace the existing `types.py` body with:

```python
"""Dataclasses shared across the pipeline.

These map 1:1 to the JSON output schema in section 3 of the spec,
with the addition of `ScheduleRegion`, `PageLayout`, `NumberedLine`
as internal pipeline types.
"""

from __future__ import annotations

from dataclasses import dataclass, field

BBox = tuple[float, float, float, float]  # (x0, top, x1, bottom) in PDF points


@dataclass
class NumberedLine:
    number: int                      # 1-indexed from top of page
    text: str                        # verbatim pdftotext -layout line
    bbox: BBox | None = None         # pdfplumber-derived; None if clustering failed


@dataclass
class PageLayout:
    page_number: int                 # 1-indexed
    lines: list[NumberedLine]
    page_width: float = 0.0          # PDF points; 0 means unknown
    page_height: float = 0.0


@dataclass
class ScheduleRegion:
    start_page: int                  # 1-indexed, inclusive
    end_page: int                    # 1-indexed, inclusive
    start_marker: str
    end_marker: str                  # "END OF SECTION" | "new_section" | "eof"


@dataclass
class SetLocation:
    page: int                        # 1-indexed
    line_range: tuple[int, int]      # (first, last), 1-indexed, inclusive
    bbox: BBox | None = None         # union of NumberedLine bboxes in line_range


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

- [ ] **Step 2: Run existing tests to confirm no breakage from new optional fields**

Run: `pytest tests/ -v`
Expected: PASS (all existing tests, ~6-8 passing). The added optional fields default sensibly so no existing constructor call breaks.

- [ ] **Step 3: Commit**

```bash
git add src/hardware_sets/types.py
git commit -m "types: add optional bbox fields for UI evidence pane"
```

## Task 2: Word-clustering helper + unit test (TDD)

**Files:**
- Create: `tests/test_layout_bbox.py`
- Modify: `src/hardware_sets/layout.py`

The function `cluster_words_into_lines` takes pdfplumber word dicts and returns one bbox per line, top-down. Font height tolerance: words whose `top` values are within `y_tol` of each other belong to one line.

- [ ] **Step 1: Write the failing test**

Create `tests/test_layout_bbox.py`:

```python
"""Tests for layout.cluster_words_into_lines — pure math, no PDFs.

Hand-crafted word dicts mimic pdfplumber's `extract_words()` output.
Catches silent failures in the bbox highlighting that would otherwise
surface as 'highlight drawn in the wrong place'.
"""

from hardware_sets.layout import cluster_words_into_lines


def _w(text: str, x0: float, top: float, x1: float, bottom: float) -> dict:
    return {"text": text, "x0": x0, "top": top, "x1": x1, "bottom": bottom}


def test_three_distinct_lines_cluster_into_three_bboxes():
    words = [
        _w("SET", 50, 100, 75, 110),
        _w("1.1", 80, 100, 98, 110),
        _w("HINGE", 50, 120, 90, 130),
        _w("FOOTER", 50, 700, 100, 710),
    ]
    lines = cluster_words_into_lines(words, y_tol=2.0)

    assert len(lines) == 3
    # First line: union of two words at top=100
    assert lines[0] == (50.0, 100.0, 98.0, 110.0)
    # Second line
    assert lines[1] == (50.0, 120.0, 90.0, 130.0)
    # Third line
    assert lines[2] == (50.0, 700.0, 100.0, 710.0)


def test_words_within_tolerance_merge_into_same_line():
    # top values 100.0 and 100.8 should cluster together with y_tol=2.0
    words = [
        _w("A", 10, 100.0, 20, 110),
        _w("B", 25, 100.8, 35, 110.5),
    ]
    lines = cluster_words_into_lines(words, y_tol=2.0)
    assert len(lines) == 1
    assert lines[0] == (10.0, 100.0, 35.0, 110.5)


def test_empty_input_returns_empty():
    assert cluster_words_into_lines([], y_tol=2.0) == []


def test_output_is_sorted_top_down():
    # Feed words out of order; expect top-down output
    words = [
        _w("C", 10, 300, 20, 310),
        _w("A", 10, 100, 20, 110),
        _w("B", 10, 200, 20, 210),
    ]
    lines = cluster_words_into_lines(words, y_tol=2.0)
    assert len(lines) == 3
    tops = [b[1] for b in lines]
    assert tops == sorted(tops)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_layout_bbox.py -v`
Expected: FAIL with `ImportError: cannot import name 'cluster_words_into_lines' from 'hardware_sets.layout'`

- [ ] **Step 3: Implement `cluster_words_into_lines` in `layout.py`**

Add at the top of `src/hardware_sets/layout.py`, after the existing imports:

```python
from typing import Iterable

from hardware_sets.types import BBox


def cluster_words_into_lines(
    words: Iterable[dict],
    *,
    y_tol: float = 3.0,
) -> list[BBox]:
    """Cluster pdfplumber word dicts by `top` coordinate into line bboxes.

    Each returned bbox is `(min_x0, min_top, max_x1, max_bottom)` in PDF points
    for one rendered line. Output is sorted top-down.

    `y_tol` controls line grouping: words whose `top` values are within
    `y_tol` of a running cluster top merge into that cluster. 3.0 points
    handles typical 10-12pt body text.
    """
    items = sorted(words, key=lambda w: (w["top"], w["x0"]))
    clusters: list[list[dict]] = []
    for w in items:
        placed = False
        for c in clusters:
            if abs(c[0]["top"] - w["top"]) <= y_tol:
                c.append(w)
                placed = True
                break
        if not placed:
            clusters.append([w])

    bboxes: list[BBox] = []
    for c in clusters:
        x0 = min(w["x0"] for w in c)
        top = min(w["top"] for w in c)
        x1 = max(w["x1"] for w in c)
        bottom = max(w["bottom"] for w in c)
        bboxes.append((float(x0), float(top), float(x1), float(bottom)))
    bboxes.sort(key=lambda b: b[1])
    return bboxes
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_layout_bbox.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_layout_bbox.py src/hardware_sets/layout.py
git commit -m "layout: add word-clustering helper with unit test"
```

## Task 3: Wire bboxes into `extract_layout`

**Files:**
- Modify: `src/hardware_sets/layout.py`

`extract_layout` currently uses `pdftotext -layout` (subprocess). Now: also open the PDF with pdfplumber, extract words for the same page, cluster into line bboxes, and attach 1:1 to the pdftotext line list when counts match. When counts disagree, leave bboxes as `None` and log a debug message.

- [ ] **Step 1: Rewrite `extract_layout` to attach bboxes**

Replace the current `extract_layout` in `src/hardware_sets/layout.py` with:

```python
import logging

import pdfplumber

log = logging.getLogger(__name__)


def extract_layout(pdf_path: Path, page_num: int) -> PageLayout:
    """Return a PageLayout for 1-indexed `page_num` of `pdf_path`.

    Text comes from `pdftotext -layout` (the format the LLM sees and cites).
    Per-line bboxes are derived from pdfplumber word clustering and attached
    to each NumberedLine in order. If the two tools disagree on line count,
    bboxes are left `None` on that page — the UI degrades to "scroll to line,
    no highlight".
    """
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

    page_w, page_h = 0.0, 0.0
    line_bboxes: list[BBox] = []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            if 1 <= page_num <= len(pdf.pages):
                page = pdf.pages[page_num - 1]
                page_w = float(page.width)
                page_h = float(page.height)
                words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
                line_bboxes = cluster_words_into_lines(words, y_tol=3.0)
    except Exception as e:
        log.debug("pdfplumber bbox extraction failed for page %d: %s", page_num, e)

    if line_bboxes and len(line_bboxes) == len(lines):
        for nl, bb in zip(lines, line_bboxes):
            nl.bbox = bb
    elif line_bboxes:
        log.debug(
            "page %d: line count mismatch (pdftotext=%d, pdfplumber=%d); bboxes skipped",
            page_num, len(lines), len(line_bboxes),
        )

    return PageLayout(
        page_number=page_num,
        lines=lines,
        page_width=page_w,
        page_height=page_h,
    )
```

Ensure the top of the file has the `BBox` import: add `from hardware_sets.types import BBox, NumberedLine, PageLayout` at the top (replacing the existing shorter import).

- [ ] **Step 2: Manually verify on one sample PDF**

Run:
```bash
python -c "
from pathlib import Path
from hardware_sets.layout import extract_layout
lay = extract_layout(Path('samples/div_08_1.pdf'), 40)
print(f'page {lay.page_number}: {len(lay.lines)} lines, page dims {lay.page_width}x{lay.page_height}')
with_bbox = sum(1 for nl in lay.lines if nl.bbox)
print(f'{with_bbox}/{len(lay.lines)} lines have bboxes')
if lay.lines and lay.lines[0].bbox:
    print(f'first line: L{lay.lines[0].number}: {lay.lines[0].text[:60]!r} bbox={lay.lines[0].bbox}')
"
```
Expected: nonzero line count, matching bbox count (or a clear skip message), sensible page dims (e.g. 612 x 792 for US letter).

- [ ] **Step 3: Run the full test suite**

Run: `pytest tests/ -v`
Expected: all tests pass (existing + the new bbox test).

- [ ] **Step 4: Commit**

```bash
git add src/hardware_sets/layout.py
git commit -m "layout: attach pdfplumber bboxes to NumberedLine and PageLayout"
```

## Task 4: Compute `SetLocation.bbox` as union of line bboxes

**Files:**
- Modify: `src/hardware_sets/cli.py`
- Modify: `src/hardware_sets/extract.py`

`extract.py` returns `HardwareSet` objects whose `SetLocation` has no bbox. `cli.py` can walk the returned sets, look up bboxes in the `PageLayout` list by page + line_range, and populate `SetLocation.bbox` on both `location` and every `continued_on` entry. We keep it in `cli.py` so `extract.py` stays a pure LLM wrapper.

- [ ] **Step 1: Add a bbox-union helper to `extract.py`**

Add to `src/hardware_sets/extract.py` (near the bottom, before `extract_sets`):

```python
def _union_bbox(layouts: list[PageLayout], page: int, line_range: tuple[int, int]) -> tuple | None:
    """Union of bboxes for `line_range` on `page`. None if any line lacks a bbox."""
    page_layout = next((l for l in layouts if l.page_number == page), None)
    if not page_layout:
        return None
    first, last = line_range
    selected = [nl for nl in page_layout.lines if first <= nl.number <= last and nl.bbox]
    if not selected or len(selected) != (last - first + 1):
        return None
    x0 = min(nl.bbox[0] for nl in selected)
    top = min(nl.bbox[1] for nl in selected)
    x1 = max(nl.bbox[2] for nl in selected)
    bottom = max(nl.bbox[3] for nl in selected)
    return (float(x0), float(top), float(x1), float(bottom))


def attach_bboxes(sets: list[HardwareSet], layouts: list[PageLayout]) -> list[HardwareSet]:
    """Mutate `sets` in place, populating `SetLocation.bbox` on location and continued_on."""
    for s in sets:
        s.location.bbox = _union_bbox(layouts, s.location.page, s.location.line_range)
        for cont in s.continued_on:
            cont.bbox = _union_bbox(layouts, cont.page, cont.line_range)
    return sets
```

- [ ] **Step 2: Call `attach_bboxes` from `cli.py` after `extract_sets`**

In `src/hardware_sets/cli.py`, inside the `for i, region in enumerate(regions, start=1):` loop, right after `sets = extract_mod.extract_sets(region, layouts, model=args.model)`, add:

```python
            sets = extract_mod.attach_bboxes(sets, layouts)
```

- [ ] **Step 3: Verify JSON now contains bbox fields**

Run (requires `ANTHROPIC_API_KEY`):
```bash
python -m hardware_sets samples/div_08_1.pdf --out /tmp/div08_1.json --quiet
python -c "
import json
d = json.load(open('/tmp/div08_1.json'))
for s in d['hardware_sets'][:2]:
    print(s['set_number'], '->', s['location'])
"
```
Expected: each `location` dict includes a `bbox` field (either a 4-tuple or `null`), plus the existing `page` and `line_range`.

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/hardware_sets/extract.py src/hardware_sets/cli.py
git commit -m "extract: populate SetLocation.bbox from line-range union"
```

---

# Phase 2 — FastAPI wrapper

Aim: `POST /extract` streams typed SSE events mirroring the pipeline; `GET /pdf/{session_id}` serves the uploaded PDF back for in-browser rendering; Dockerfile + fly.toml ready to deploy.

## Task 5: Package scaffold + dependencies

**Files:**
- Create: `src/hardware_sets_api/__init__.py`
- Create: `src/hardware_sets_api/main.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add API dependencies to `pyproject.toml`**

Replace `pyproject.toml` body with:

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
api = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "python-multipart>=0.0.9",
]

[project.scripts]
hardware-sets = "hardware_sets.cli:main_entry"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

- [ ] **Step 2: Install the API extras**

Run: `pip install -e '.[api,dev]'`
Expected: installs fastapi, uvicorn, python-multipart alongside existing deps.

- [ ] **Step 3: Create the package files**

Create `src/hardware_sets_api/__init__.py`:

```python
"""FastAPI wrapper around the hardware_sets pipeline.

See docs/superpowers/specs/2026-04-21-web-ui-design.md §3.
"""
```

Create `src/hardware_sets_api/main.py`:

```python
"""FastAPI app — health endpoint scaffold. SSE + PDF endpoints land in later tasks."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def _allowed_origins() -> list[str]:
    raw = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000")
    return [o.strip() for o in raw.split(",") if o.strip()]


app = FastAPI(title="hardware-sets API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 4: Smoke-test the scaffold**

Run: `uvicorn hardware_sets_api.main:app --port 8000 &` (background), then `curl -s http://localhost:8000/health`
Expected: `{"status":"ok"}`. Then kill uvicorn.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/hardware_sets_api/
git commit -m "api: scaffold FastAPI app with CORS and health endpoint"
```

## Task 6: Session cache module

**Files:**
- Create: `src/hardware_sets_api/session.py`

Simple in-memory dict keyed by UUID4 hex, storing `(pdf_bytes, filename, expires_at_epoch)`. Lazy eviction on every access. TTL default 600 seconds.

- [ ] **Step 1: Write `session.py`**

```python
"""In-memory PDF session cache with TTL (spec §3).

Not persistent: we accept that a pod restart drops active sessions. Keys
are UUID4 hex. Eviction is lazy on every `get` / `put` call — no background
task so the module stays safe to import in any context.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

DEFAULT_TTL_SECONDS = 600  # 10 minutes


@dataclass
class SessionEntry:
    pdf_bytes: bytes
    filename: str
    expires_at: float


class SessionStore:
    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, SessionEntry] = {}

    def _evict_expired(self, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        dead = [sid for sid, e in self._store.items() if e.expires_at <= now]
        for sid in dead:
            self._store.pop(sid, None)

    def put(self, pdf_bytes: bytes, filename: str) -> str:
        self._evict_expired()
        sid = uuid.uuid4().hex
        self._store[sid] = SessionEntry(
            pdf_bytes=pdf_bytes,
            filename=filename,
            expires_at=time.time() + self._ttl,
        )
        return sid

    def get(self, session_id: str) -> SessionEntry | None:
        self._evict_expired()
        return self._store.get(session_id)


# Module-level singleton — one FastAPI process, one store.
store = SessionStore()
```

- [ ] **Step 2: Commit**

```bash
git add src/hardware_sets_api/session.py
git commit -m "api: add in-memory session cache with TTL"
```

## Task 7: SSE streaming helper

**Files:**
- Create: `src/hardware_sets_api/sse.py`

This module provides event formatting and the pipeline-to-events generator. Keeping it separate from `main.py` means `main.py` stays a routing file.

- [ ] **Step 1: Write `sse.py`**

```python
"""SSE event formatting + pipeline → events generator (spec §5).

The generator yields already-formatted SSE text chunks so the FastAPI
endpoint can just `StreamingResponse` over it. A 15s comment heartbeat
prevents intermediary proxy timeouts (Fly's edge, Cloudflare, etc.).
"""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from typing import AsyncIterator

from hardware_sets import filter as filter_mod
from hardware_sets import layout as layout_mod
from hardware_sets import extract as extract_mod
from hardware_sets import resolve as resolve_mod
from hardware_sets.types import HardwareSet

log = logging.getLogger(__name__)

HEARTBEAT_SECONDS = 15


def format_event(event: str, data: dict | list | str) -> str:
    """Format one SSE event. `data` is JSON-encoded verbatim."""
    payload = data if isinstance(data, str) else json.dumps(data, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


async def _run_sync(func, *args, **kwargs):
    """Run a blocking callable on the default executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


async def stream_extract(
    pdf_bytes: bytes,
    filename: str,
    session_id: str,
    *,
    model: str = extract_mod.DEFAULT_MODEL,
) -> AsyncIterator[str]:
    """Yield SSE-formatted chunks matching the spec §5 protocol."""
    yield format_event("session_started", {"session_id": session_id, "filename": filename})

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fh:
        fh.write(pdf_bytes)
        pdf_path = Path(fh.name)

    try:
        # filter ---------------------------------------------------------
        try:
            regions = await _run_sync(filter_mod.find_schedule_regions, pdf_path)
        except Exception as e:
            log.exception("filter crashed")
            yield format_event("error", {"code": "parse_error", "message": str(e)})
            return

        if not regions:
            yield format_event(
                "error",
                {"code": "no_schedule", "message": "Division 08 hardware schedule not detected."},
            )
            return

        for r in regions:
            yield format_event("region_found", {
                "page_start": r.start_page,
                "page_end": r.end_page,
                "marker": r.start_marker,
            })

        # extract --------------------------------------------------------
        all_sets: list[HardwareSet] = []
        llm_calls = 0
        warnings: list[str] = []

        for idx, region in enumerate(regions):
            yield format_event("extracting", {
                "region_index": idx,
                "total_regions": len(regions),
                "page_start": region.start_page,
                "page_end": region.end_page,
            })

            layouts = await _run_sync(
                lambda: [
                    layout_mod.extract_layout(pdf_path, p)
                    for p in range(region.start_page, region.end_page + 1)
                ]
            )

            try:
                sets = await _run_sync(
                    extract_mod.extract_sets, region, layouts, model=model
                )
                sets = extract_mod.attach_bboxes(sets, layouts)
                llm_calls += 1
            except extract_mod.ExtractionError as e:
                warnings.append(f"region {region.start_page}-{region.end_page}: {e}")
                yield format_event("warning", {"message": f"region skipped: {e}"})
                continue
            except Exception as e:
                log.exception("extract crashed")
                yield format_event("error", {"code": "api_error", "message": str(e)})
                return

            for s in sets:
                all_sets.append(s)
                yield format_event("set_extracted", asdict(s))

        # resolve --------------------------------------------------------
        scored = resolve_mod.validate_and_score(all_sets)
        for i, s in enumerate(scored):
            yield format_event("scored", {"set_index": i, "confidence": s.confidence})

        yield format_event("done", {
            "total_sets": len(scored),
            "llm_calls": llm_calls,
            "warnings": warnings,
        })

    finally:
        try:
            pdf_path.unlink(missing_ok=True)
        except Exception:
            pass


async def heartbeat_merge(inner: AsyncIterator[str]) -> AsyncIterator[str]:
    """Wrap an inner async iterator and emit a comment heartbeat every HEARTBEAT_SECONDS."""
    q: asyncio.Queue[str | None] = asyncio.Queue()

    async def pump():
        try:
            async for chunk in inner:
                await q.put(chunk)
        finally:
            await q.put(None)

    task = asyncio.create_task(pump())
    last = time.monotonic()
    try:
        while True:
            try:
                chunk = await asyncio.wait_for(q.get(), timeout=HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                last = time.monotonic()
                continue
            if chunk is None:
                return
            yield chunk
            last = time.monotonic()
    finally:
        task.cancel()
```

- [ ] **Step 2: Commit**

```bash
git add src/hardware_sets_api/sse.py
git commit -m "api: SSE pipeline-to-events generator with heartbeats"
```

## Task 8: `/extract` and `/pdf/{session_id}` endpoints

**Files:**
- Modify: `src/hardware_sets_api/main.py`

- [ ] **Step 1: Add endpoints to `main.py`**

Replace `src/hardware_sets_api/main.py` with:

```python
"""FastAPI app — health + extract (SSE) + pdf serving."""

from __future__ import annotations

import os

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

from hardware_sets_api.session import store
from hardware_sets_api.sse import heartbeat_merge, stream_extract

MAX_PDF_BYTES = 25 * 1024 * 1024  # 25 MB


def _allowed_origins() -> list[str]:
    raw = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000")
    return [o.strip() for o in raw.split(",") if o.strip()]


app = FastAPI(title="hardware-sets API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/extract")
async def extract(file: UploadFile = File(...)) -> StreamingResponse:
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="empty upload")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="pdf exceeds 25 MB")

    filename = file.filename or "upload.pdf"
    session_id = store.put(pdf_bytes, filename)

    async def gen():
        async for chunk in heartbeat_merge(
            stream_extract(pdf_bytes, filename, session_id)
        ):
            yield chunk

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/pdf/{session_id}")
def pdf(session_id: str) -> Response:
    entry = store.get(session_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="session expired or not found")
    return Response(
        content=entry.pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{entry.filename}"',
            "Cache-Control": "private, max-age=300",
        },
    )
```

- [ ] **Step 2: Manual smoke test — SSE stream**

Run uvicorn in one terminal: `ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY uvicorn hardware_sets_api.main:app --port 8000`

In another: `curl -N -F "file=@samples/div_08_1.pdf" http://localhost:8000/extract | head -40`

Expected: SSE events streaming — `event: session_started`, `event: region_found`, `event: extracting`, `event: set_extracted` (containing a full HardwareSet JSON including bbox), eventually `event: done`.

- [ ] **Step 3: Manual smoke test — PDF endpoint**

Copy the `session_id` from the first event above, then: `curl -I http://localhost:8000/pdf/<session_id>`
Expected: `HTTP/1.1 200 OK`, `Content-Type: application/pdf`, `Content-Disposition: inline; filename="div_08_1.pdf"`.

Kill uvicorn.

- [ ] **Step 4: Commit**

```bash
git add src/hardware_sets_api/main.py
git commit -m "api: add /extract SSE and /pdf endpoints"
```

## Task 9: Dockerfile + fly.toml

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`
- Create: `fly.toml`

- [ ] **Step 1: Write the Dockerfile**

```dockerfile
# syntax=docker/dockerfile:1.6
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends poppler-utils \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

RUN pip install --upgrade pip \
 && pip install .[api]

ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn hardware_sets_api.main:app --host 0.0.0.0 --port ${PORT}"]
```

- [ ] **Step 2: Write `.dockerignore`**

```
.git
.venv
__pycache__
*.pyc
.pytest_cache
.superpowers
docs
frontend
out
samples
tests
.env*
```

- [ ] **Step 3: Write `fly.toml`**

```toml
app = "hardware-sets-api"
primary_region = "iad"

[build]

[env]
  PORT = "8080"

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = "stop"
  auto_start_machines = true
  min_machines_running = 0

[[vm]]
  size = "shared-cpu-1x"
  memory = "1gb"
```

- [ ] **Step 4: Local Docker smoke test**

Run:
```bash
docker build -t hardware-sets-api .
docker run -d --rm -p 8080:8080 -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY --name hw-api hardware-sets-api
sleep 3
curl -s http://localhost:8080/health
docker stop hw-api
```
Expected: `{"status":"ok"}`.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore fly.toml
git commit -m "deploy: Dockerfile + fly.toml for backend"
```

---

# Phase 3 — Frontend scaffold + Blueprint landing

Aim: a Next.js 15 app with Blueprint chrome renders the hero landing page; drag-drop produces a file that navigates to `/extract?session=<id>`.

## Task 10: Next.js scaffold

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/next.config.mjs`
- Create: `frontend/postcss.config.mjs`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/.env.local.example`
- Create: `frontend/.gitignore`
- Create: `frontend/app/layout.tsx`
- Create: `frontend/app/globals.css`
- Modify: `.gitignore` (root)

- [ ] **Step 1: Write `frontend/package.json`**

```json
{
  "name": "hardware-sets-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "typecheck": "tsc --noEmit",
    "test": "vitest run"
  },
  "dependencies": {
    "next": "^15.0.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-pdf": "^9.1.1",
    "pdfjs-dist": "^4.4.168"
  },
  "devDependencies": {
    "@types/node": "^20.12.0",
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "autoprefixer": "^10.4.19",
    "postcss": "^8.4.38",
    "tailwindcss": "^3.4.4",
    "typescript": "^5.5.0",
    "vitest": "^1.6.0"
  }
}
```

- [ ] **Step 2: Write `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

- [ ] **Step 3: Write `frontend/next.config.mjs`**

```js
/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  webpack: (config) => {
    // Required by pdfjs-dist when used via react-pdf
    config.resolve.alias.canvas = false;
    return config;
  },
};
export default nextConfig;
```

- [ ] **Step 4: Write `frontend/postcss.config.mjs`**

```js
export default {
  plugins: { tailwindcss: {}, autoprefixer: {} },
};
```

- [ ] **Step 5: Write `frontend/tailwind.config.ts`**

```ts
import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#081a34",
        paper2: "#0c2548",
        ink: "#e3edff",
        "ink-dim": "rgba(227,237,255,0.55)",
        cyan: "#7ac9ff",
        "cyan-dim": "rgba(122,201,255,0.4)",
      },
      fontFamily: {
        serif: ["var(--font-fraunces)", "ui-serif", "serif"],
        mono: ["var(--font-jetbrains)", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
```

- [ ] **Step 6: Write `frontend/.env.local.example`**

```
# Point this at your deployed Fly app in production. Defaults to local dev.
NEXT_PUBLIC_API_URL=http://localhost:8000
```

- [ ] **Step 7: Write `frontend/.gitignore`**

```
node_modules/
.next/
out/
.env.local
.env*.local
```

- [ ] **Step 8: Append frontend paths to root `.gitignore`**

Append to `/Users/jacobaskey/Development/fresco-challenge/.gitignore`:

```
frontend/node_modules/
frontend/.next/
frontend/out/
```

- [ ] **Step 9: Write `frontend/app/layout.tsx`**

```tsx
import type { Metadata } from "next";
import { Fraunces, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-fraunces",
  style: ["normal", "italic"],
  display: "swap",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  weight: ["300", "400", "600"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Hardware Sets, located.",
  description:
    "Extract Division 08 door hardware sets from specbook PDFs with pixel-precise source citations.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${fraunces.variable} ${jetbrains.variable}`}>
      <body>{children}</body>
    </html>
  );
}
```

- [ ] **Step 10: Write `frontend/app/globals.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --paper: #081a34;
  --paper-2: #0c2548;
  --ink: #e3edff;
  --ink-dim: rgba(227, 237, 255, 0.55);
  --cyan: #7ac9ff;
  --cyan-dim: rgba(122, 201, 255, 0.4);
  --grid: rgba(122, 201, 255, 0.08);
  --grid-minor: rgba(122, 201, 255, 0.04);
}

html, body {
  height: 100%;
}

body {
  background-color: var(--paper);
  color: var(--ink);
  font-family: var(--font-jetbrains), ui-monospace, monospace;
  background-image:
    linear-gradient(var(--grid) 1px, transparent 1px),
    linear-gradient(90deg, var(--grid) 1px, transparent 1px),
    linear-gradient(var(--grid-minor) 1px, transparent 1px),
    linear-gradient(90deg, var(--grid-minor) 1px, transparent 1px);
  background-size: 80px 80px, 80px 80px, 16px 16px, 16px 16px;
}

.chrome-border {
  border: 1px solid var(--cyan-dim);
}
```

- [ ] **Step 11: Install + typecheck + build**

Run (from `frontend/`):
```bash
cd frontend
npm install
npm run typecheck
npm run build
```
Expected: clean install, no type errors, `next build` succeeds.

- [ ] **Step 12: Commit**

```bash
git add frontend/ .gitignore
git commit -m "frontend: scaffold Next.js 15 + Tailwind + Blueprint tokens"
```

## Task 11: `BlueprintChrome` component

**Files:**
- Create: `frontend/app/components/BlueprintChrome.tsx`

The chrome wraps every page: top title strip (`DWG·01  REV·A  SHT·1·1`), bottom strip (timestamp / rev), corner crosshairs. Grid background comes from `body` in globals.css.

- [ ] **Step 1: Write the component**

```tsx
"use client";

import React from "react";

type Props = {
  title?: string;       // shown in the top strip after "DWG·"
  rev?: string;         // "A", "B", ...
  sheet?: string;       // "1·1"
  children: React.ReactNode;
};

export function BlueprintChrome({ title = "01", rev = "A", sheet = "1·1", children }: Props) {
  return (
    <div className="relative min-h-screen">
      {/* top strip */}
      <div className="fixed top-0 left-0 right-0 z-20 h-8 px-4 flex items-center justify-between text-[10px] tracking-[0.25em] uppercase text-ink-dim border-b border-cyan-dim bg-paper/80 backdrop-blur">
        <div className="flex items-center gap-3">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-cyan animate-pulse" />
          <span>HARDWARE·SETS</span>
          <span>DWG·{title}</span>
          <span>REV·{rev}</span>
          <span>SHT·{sheet}</span>
        </div>
        <span>SCALE 1:1</span>
      </div>

      {/* corner crosshairs */}
      <Crosshair className="top-8 left-0" />
      <Crosshair className="top-8 right-0" />
      <Crosshair className="bottom-8 left-0" />
      <Crosshair className="bottom-8 right-0" />

      {/* body */}
      <main className="pt-8 pb-8 min-h-screen">{children}</main>

      {/* bottom strip */}
      <div className="fixed bottom-0 left-0 right-0 z-20 h-8 px-4 flex items-center justify-between text-[10px] tracking-[0.25em] uppercase text-ink-dim border-t border-cyan-dim bg-paper/80 backdrop-blur">
        <span>FRESCO · DIV·08 · HARDWARE SCHEDULES</span>
        <span>{new Date().toISOString().slice(0, 10)}</span>
      </div>
    </div>
  );
}

function Crosshair({ className = "" }: { className?: string }) {
  return (
    <div className={`pointer-events-none absolute ${className}`} aria-hidden="true">
      <div className="relative w-6 h-6">
        <div className="absolute top-1/2 left-0 w-full h-px bg-cyan-dim" />
        <div className="absolute top-0 left-1/2 w-px h-full bg-cyan-dim" />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/components/BlueprintChrome.tsx
git commit -m "frontend: BlueprintChrome component (title strip, crosshairs)"
```

## Task 12: `DropZone` component

**Files:**
- Create: `frontend/app/components/DropZone.tsx`

A large italic-serif framed area with dimension callouts. Accepts PDF only. Shows hover-lift and drag-over states. On file selection, calls `onFile(file)`.

- [ ] **Step 1: Write the component**

```tsx
"use client";

import React, { useCallback, useRef, useState } from "react";

type Props = {
  onFile: (file: File) => void;
  disabled?: boolean;
};

export function DropZone({ onFile, disabled }: Props) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    (file: File | undefined) => {
      if (!file) return;
      if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
        alert("Please drop a PDF.");
        return;
      }
      onFile(file);
    },
    [onFile],
  );

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (disabled) return;
    handleFile(e.dataTransfer.files?.[0]);
  };

  return (
    <div className="relative mx-auto w-full max-w-[860px] px-8">
      {/* dimension callouts top */}
      <div className="flex items-center justify-center gap-3 text-[10px] tracking-[0.3em] uppercase text-ink-dim mb-3">
        <span>↔</span>
        <span>860 PX</span>
        <span>↔</span>
      </div>

      {/* glow halo */}
      <div
        className="absolute inset-8 -z-10 blur-3xl opacity-50"
        style={{
          background:
            "radial-gradient(closest-side, rgba(122,201,255,0.35), transparent 70%)",
        }}
      />

      <button
        type="button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`group relative w-full aspect-[1.7/1] border rounded-sm transition-all duration-200
          ${dragging ? "border-cyan bg-paper2/70" : "border-cyan-dim hover:border-cyan hover:-translate-y-0.5"}
          ${disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}
          flex items-center justify-center`}
      >
        <span className="font-serif text-5xl md:text-6xl tracking-tight">
          Drop your <em className="text-cyan">specbook.</em>
        </span>

        <span className="absolute bottom-4 left-1/2 -translate-x-1/2 text-[10px] tracking-[0.3em] uppercase text-ink-dim">
          or click to browse · PDF · up to 25 MB
        </span>
      </button>

      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        className="sr-only"
        onChange={(e) => handleFile(e.target.files?.[0])}
      />

      {/* dimension callouts bottom */}
      <div className="flex items-center justify-center gap-3 text-[10px] tracking-[0.3em] uppercase text-ink-dim mt-3">
        <span>↕</span>
        <span>SCALE 1:1</span>
        <span>↕</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/components/DropZone.tsx
git commit -m "frontend: DropZone with drag-over state and PDF validation"
```

## Task 13: Landing page + upload flow

**Files:**
- Create: `frontend/app/page.tsx`
- Create: `frontend/lib/hashPdf.ts`

- [ ] **Step 1: Write `lib/hashPdf.ts`**

```ts
/** SHA-256 hex of a File's bytes, via Web Crypto. */
export async function hashPdf(file: File): Promise<string> {
  const buf = await file.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", buf);
  return [...new Uint8Array(digest)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
```

- [ ] **Step 2: Write `app/page.tsx`**

```tsx
"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { BlueprintChrome } from "./components/BlueprintChrome";
import { DropZone } from "./components/DropZone";
import { hashPdf } from "@/lib/hashPdf";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function Landing() {
  const router = useRouter();
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = useCallback(
    async (file: File) => {
      setUploading(true);
      setError(null);
      try {
        const pdfHash = await hashPdf(file);

        // Push the bytes directly to /extract — backend returns an SSE stream,
        // so we kick off the request on the /extract page via POST + ReadableStream.
        // Here we only stash the file in sessionStorage as a handoff, along with its hash.
        const buffer = await file.arrayBuffer();
        const base64 = btoa(
          String.fromCharCode(...new Uint8Array(buffer)),
        );
        sessionStorage.setItem(
          "pending_pdf",
          JSON.stringify({
            name: file.name,
            hash: pdfHash,
            base64,
          }),
        );
        router.push("/extract");
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : String(e));
        setUploading(false);
      }
    },
    [router],
  );

  return (
    <BlueprintChrome title="01" rev="A" sheet="1·1">
      <div className="min-h-[calc(100vh-4rem)] flex flex-col items-center justify-center px-6 py-16">
        <h1 className="font-serif text-4xl md:text-6xl text-center mb-16 tracking-tight">
          Hardware Sets, <em className="text-cyan">located.</em>
        </h1>

        <DropZone onFile={handleFile} disabled={uploading} />

        {error && (
          <p className="mt-6 text-sm text-red-300 font-mono">{error}</p>
        )}

        {/* v2 samples chip row placeholder — layout slot only */}
        <div className="samples-row mt-12 h-8 opacity-30 text-[10px] tracking-[0.3em] uppercase text-ink-dim">
          {/* intentional blank: sample PDFs land in v2 */}
        </div>

        <p className="mt-16 text-[10px] tracking-[0.3em] uppercase text-ink-dim">
          API · <span className="text-cyan">{API_URL.replace(/^https?:\/\//, "")}</span>
        </p>
      </div>
    </BlueprintChrome>
  );
}
```

- [ ] **Step 3: Run dev server and confirm the landing page renders**

Run (from `frontend/`): `npm run dev` (background)
Open browser to `http://localhost:3000`. Expected: Blueprint navy + grid + italic Fraunces headline + glowing drop zone. Hover lifts. Drag-over turns cyan.

Kill dev server.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/page.tsx frontend/lib/hashPdf.ts
git commit -m "frontend: landing page with drop-to-upload handoff"
```

---

# Phase 4 — Streaming + editing UI

## Task 14: Shared TS types

**Files:**
- Create: `frontend/lib/types.ts`

- [ ] **Step 1: Write `types.ts`**

```ts
// Mirrors Python dataclasses in src/hardware_sets/types.py. Hand-maintained for v1.

export type BBox = [number, number, number, number]; // (x0, top, x1, bottom), PDF points

export interface SetLocation {
  page: number;
  line_range: [number, number];
  bbox: BBox | null;
}

export interface Component {
  qty: number | null;
  description: string | null;
  catalog_number: string | null;
  mfr: string | null;
  finish: string | null;
  notes: string | null;
  confidence: { mfr?: number; finish?: number; qty?: number };
}

export interface HardwareSet {
  set_number: string;
  description: string | null;
  location: SetLocation;
  components: Component[];
  continued_on: SetLocation[];
  is_not_used: boolean;
  confidence: number;
  notes: string | null;
}

// SSE events ------------------------------------------------------------

export type SseEvent =
  | { event: "session_started"; data: { session_id: string; filename: string } }
  | { event: "region_found"; data: { page_start: number; page_end: number; marker: string } }
  | { event: "extracting"; data: { region_index: number; total_regions: number; page_start: number; page_end: number } }
  | { event: "set_extracted"; data: HardwareSet }
  | { event: "scored"; data: { set_index: number; confidence: number } }
  | { event: "warning"; data: { message: string } }
  | { event: "done"; data: { total_sets: number; llm_calls: number; warnings: string[] } }
  | { event: "error"; data: { code: "scanned_pdf" | "no_schedule" | "api_error" | "parse_error"; message: string } };

export type EditableField = "qty" | "description" | "catalog_number" | "mfr" | "finish" | "notes";

export type Correction =
  | { type: "field"; set_number: string; component_index: number; field: EditableField; before: unknown; after: unknown }
  | { type: "delete_set"; set_number: string }
  | { type: "add_component"; set_number: string; component_index: number }
  | { type: "remove_component"; set_number: string; component_index: number };
```

- [ ] **Step 2: Commit**

```bash
git add frontend/lib/types.ts
git commit -m "frontend: shared TS types mirroring backend dataclasses"
```

## Task 15: SSE consumer that POSTs + parses streaming events

**Files:**
- Create: `frontend/lib/sse.ts`

Native `EventSource` only does GET. For file uploads we need POST, so we use `fetch` + manual SSE parsing of the ReadableStream.

- [ ] **Step 1: Write `sse.ts`**

```ts
import type { SseEvent } from "./types";

export type SseHandler = (ev: SseEvent) => void;

/** POST `file` to `${apiUrl}/extract` and parse SSE events until the stream closes. */
export async function streamExtract(
  apiUrl: string,
  file: File,
  onEvent: SseHandler,
  signal?: AbortSignal,
): Promise<void> {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${apiUrl}/extract`, {
    method: "POST",
    body: form,
    signal,
    headers: { Accept: "text/event-stream" },
  });

  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => "");
    throw new Error(`extract failed: ${res.status} ${text}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const parsed = parseBlock(block);
      if (parsed) onEvent(parsed);
    }
  }
}

function parseBlock(block: string): SseEvent | null {
  if (!block || block.startsWith(":")) return null; // heartbeat
  let event = "message";
  let dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!dataLines.length) return null;
  try {
    const data = JSON.parse(dataLines.join("\n"));
    return { event, data } as SseEvent;
  } catch {
    return null;
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/lib/sse.ts
git commit -m "frontend: SSE consumer that POSTs files and parses events"
```

## Task 16: `/extract` page shell + set list + StreamLog

**Files:**
- Create: `frontend/app/components/StreamLog.tsx`
- Create: `frontend/app/components/ConfidenceBadge.tsx`
- Create: `frontend/app/extract/page.tsx`

- [ ] **Step 1: Write `StreamLog.tsx`**

```tsx
"use client";

import { useEffect, useRef } from "react";

export type StreamLine = { t: number; text: string; kind: "info" | "warn" | "error" | "done" };

export function StreamLog({ lines }: { lines: StreamLine[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [lines.length]);

  const color = (k: StreamLine["kind"]) =>
    k === "error" ? "text-red-300" : k === "warn" ? "text-amber-300" : k === "done" ? "text-cyan" : "text-ink-dim";

  return (
    <div
      ref={ref}
      className="font-mono text-[11px] tracking-wide h-40 overflow-y-auto border border-cyan-dim rounded-sm p-3 bg-paper2/40"
    >
      {lines.map((l, i) => (
        <div key={i} className={color(l.kind)}>
          <span className="text-ink-dim/60 mr-2">
            {new Date(l.t).toISOString().slice(11, 19)}
          </span>
          {l.text}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Write `ConfidenceBadge.tsx`**

```tsx
"use client";

export function ConfidenceBadge({ value, label }: { value: number | undefined; label: string }) {
  if (value === undefined) return null;
  const color =
    value >= 0.9 ? "bg-cyan" : value >= 0.6 ? "bg-amber-400" : "bg-red-400";
  return (
    <span
      title={`${label} confidence: ${value.toFixed(2)}`}
      className={`inline-block w-1.5 h-1.5 rounded-full ${color} align-middle`}
    />
  );
}
```

- [ ] **Step 3: Write `frontend/app/extract/page.tsx`** (scaffold — components land in the next tasks)

```tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { BlueprintChrome } from "../components/BlueprintChrome";
import { StreamLog, type StreamLine } from "../components/StreamLog";
import { streamExtract } from "@/lib/sse";
import type { HardwareSet, SseEvent } from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type PendingPdf = { name: string; hash: string; base64: string };

function base64ToFile(b64: string, name: string): File {
  const bin = atob(b64);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return new File([arr], name, { type: "application/pdf" });
}

export default function ExtractPage() {
  const router = useRouter();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [filename, setFilename] = useState<string>("");
  const [sets, setSets] = useState<HardwareSet[]>([]);
  const [selected, setSelected] = useState<number>(0);
  const [log, setLog] = useState<StreamLine[]>([]);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const startedRef = useRef(false);

  const appendLog = useCallback((text: string, kind: StreamLine["kind"] = "info") => {
    setLog((l) => [...l, { t: Date.now(), text, kind }]);
  }, []);

  const handleEvent = useCallback(
    (ev: SseEvent) => {
      switch (ev.event) {
        case "session_started":
          setSessionId(ev.data.session_id);
          setFilename(ev.data.filename);
          appendLog(`session · ${ev.data.session_id.slice(0, 8)} · ${ev.data.filename}`);
          break;
        case "region_found":
          appendLog(`region · pages ${ev.data.page_start}-${ev.data.page_end} · ${ev.data.marker}`);
          break;
        case "extracting":
          appendLog(`extracting · ${ev.data.region_index + 1}/${ev.data.total_regions}`);
          break;
        case "set_extracted":
          setSets((s) => [...s, ev.data]);
          appendLog(`set · ${ev.data.set_number} · ${ev.data.components.length} components`);
          break;
        case "scored":
          setSets((s) =>
            s.map((hw, i) => (i === ev.data.set_index ? { ...hw, confidence: ev.data.confidence } : hw)),
          );
          break;
        case "warning":
          appendLog(ev.data.message, "warn");
          break;
        case "error":
          setErrorCode(ev.data.code);
          setErrorMessage(ev.data.message);
          appendLog(`error · ${ev.data.code} · ${ev.data.message}`, "error");
          break;
        case "done":
          setDone(true);
          appendLog(`done · ${ev.data.total_sets} sets · ${ev.data.llm_calls} llm calls`, "done");
          break;
      }
    },
    [appendLog],
  );

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    const raw = sessionStorage.getItem("pending_pdf");
    if (!raw) {
      router.replace("/");
      return;
    }
    const pending = JSON.parse(raw) as PendingPdf;
    sessionStorage.removeItem("pending_pdf");
    const file = base64ToFile(pending.base64, pending.name);

    streamExtract(API_URL, file, handleEvent).catch((e) => {
      appendLog(String(e), "error");
      setErrorCode("api_error");
      setErrorMessage(String(e));
    });
  }, [handleEvent, router, appendLog]);

  return (
    <BlueprintChrome title="02" rev="A" sheet="1·1">
      <div className="min-h-[calc(100vh-4rem)] grid grid-cols-1 md:grid-cols-[60%_40%] gap-4 px-6 py-10">
        {/* left: sets + log */}
        <div className="flex flex-col gap-4 min-h-0">
          <StreamLog lines={log} />

          <div className="flex-1 grid grid-cols-[240px_1fr] gap-4 min-h-0">
            <aside className="overflow-y-auto border border-cyan-dim rounded-sm bg-paper2/40">
              {sets.map((s, i) => (
                <button
                  key={`${s.set_number}-${s.location.page}`}
                  onClick={() => setSelected(i)}
                  className={`block w-full text-left px-3 py-2 border-b border-cyan-dim/40 font-mono text-xs
                    ${i === selected ? "bg-paper text-cyan" : "text-ink-dim hover:text-ink"}`}
                >
                  <div className="flex items-center justify-between">
                    <span>{s.set_number}</span>
                    <span className="text-[10px]">p.{s.location.page}</span>
                  </div>
                  <div className="text-[10px] truncate opacity-70">{s.description ?? "—"}</div>
                </button>
              ))}
              {!sets.length && !errorCode && (
                <div className="p-3 text-[11px] text-ink-dim font-mono">waiting for sets…</div>
              )}
            </aside>

            <section className="overflow-y-auto border border-cyan-dim rounded-sm bg-paper2/40 p-4">
              {/* SetCard lands in Task 17 */}
              {sets[selected] ? (
                <pre className="font-mono text-[11px] whitespace-pre-wrap">
                  {JSON.stringify(sets[selected], null, 2)}
                </pre>
              ) : (
                <div className="text-[11px] text-ink-dim font-mono">select a set</div>
              )}
            </section>
          </div>
        </div>

        {/* right: evidence pane lands in Task 18 */}
        <aside className="border border-cyan-dim rounded-sm bg-paper2/40 p-4 min-h-[500px]">
          <div className="text-[10px] tracking-[0.3em] uppercase text-ink-dim mb-3">
            Evidence · {sessionId ? sessionId.slice(0, 8) : "…"} · {filename}
          </div>
          <div className="text-xs text-ink-dim font-mono">
            PDF pane lands next.
          </div>
        </aside>

        {done && <div className="hidden" aria-hidden>{/* reserved */}</div>}
        {errorCode && <div className="hidden" aria-hidden>{errorMessage}</div>}
      </div>
    </BlueprintChrome>
  );
}
```

- [ ] **Step 4: Typecheck + build**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: clean.

- [ ] **Step 5: Manual smoke test end-to-end (both servers running)**

Terminal 1: `ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY uvicorn hardware_sets_api.main:app --port 8000`
Terminal 2: `cd frontend && npm run dev`
Browser: drop `samples/div_08_1.pdf` on the landing page.
Expected: navigates to `/extract`, log fills in, sets appear in the sidebar. Clicking a set prints its JSON blob including bbox.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/components/StreamLog.tsx frontend/app/components/ConfidenceBadge.tsx frontend/app/extract/page.tsx
git commit -m "frontend: /extract shell with streaming log and set list"
```

## Task 17: `SetCard` + `ComponentRow` with inline editing

**Files:**
- Create: `frontend/app/components/ComponentRow.tsx`
- Create: `frontend/app/components/SetCard.tsx`
- Modify: `frontend/app/extract/page.tsx` (swap the JSON pre for `SetCard`)

Inline editing: clicking a field replaces the span with an input; blur/Enter commits; Escape cancels. Changes bubble up through a `onEdit` callback.

- [ ] **Step 1: Write `ComponentRow.tsx`**

```tsx
"use client";

import { useState } from "react";
import type { Component, EditableField } from "@/lib/types";
import { ConfidenceBadge } from "./ConfidenceBadge";

type Props = {
  component: Component;
  onEdit: (field: EditableField, value: string | number | null) => void;
  onRemove: () => void;
};

const FIELDS: { key: EditableField; label: string; mono: boolean; width: string }[] = [
  { key: "qty", label: "QTY", mono: true, width: "w-10" },
  { key: "description", label: "DESCRIPTION", mono: false, width: "flex-1" },
  { key: "catalog_number", label: "CATALOG", mono: true, width: "w-48" },
  { key: "mfr", label: "MFR", mono: true, width: "w-20" },
  { key: "finish", label: "FINISH", mono: true, width: "w-20" },
  { key: "notes", label: "NOTES", mono: false, width: "w-32" },
];

export function ComponentRow({ component, onEdit, onRemove }: Props) {
  return (
    <div className="flex items-center gap-2 py-1 border-b border-cyan-dim/30 text-[12px]">
      {FIELDS.map((f) => (
        <EditableCell
          key={f.key}
          value={component[f.key]}
          mono={f.mono}
          widthClass={f.width}
          onCommit={(v) => onEdit(f.key, v)}
        />
      ))}
      <div className="flex items-center gap-1">
        <ConfidenceBadge value={component.confidence.mfr} label="mfr" />
        <ConfidenceBadge value={component.confidence.finish} label="finish" />
        <ConfidenceBadge value={component.confidence.qty} label="qty" />
      </div>
      <button
        onClick={onRemove}
        className="text-ink-dim hover:text-red-300 text-[10px] ml-2 font-mono"
        title="Remove component"
      >
        ✕
      </button>
    </div>
  );
}

function EditableCell({
  value,
  mono,
  widthClass,
  onCommit,
}: {
  value: string | number | null;
  mono: boolean;
  widthClass: string;
  onCommit: (v: string | number | null) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<string>(value === null || value === undefined ? "" : String(value));
  const font = mono ? "font-mono" : "font-serif italic";

  const commit = () => {
    const trimmed = draft.trim();
    if (trimmed === "") {
      onCommit(null);
    } else if (/^\d+$/.test(trimmed) && (value === null || typeof value === "number")) {
      onCommit(parseInt(trimmed, 10));
    } else {
      onCommit(trimmed);
    }
    setEditing(false);
  };

  if (editing) {
    return (
      <input
        autoFocus
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          else if (e.key === "Escape") {
            setDraft(value === null || value === undefined ? "" : String(value));
            setEditing(false);
          }
        }}
        className={`${widthClass} ${font} bg-paper border border-cyan text-ink text-[12px] px-1 py-0.5 rounded-sm`}
      />
    );
  }

  return (
    <button
      onClick={() => {
        setDraft(value === null || value === undefined ? "" : String(value));
        setEditing(true);
      }}
      className={`${widthClass} ${font} text-left px-1 py-0.5 hover:bg-paper2/80 truncate`}
      title="Click to edit"
    >
      {value === null || value === undefined || value === "" ? (
        <span className="text-ink-dim/50">—</span>
      ) : (
        String(value)
      )}
    </button>
  );
}
```

- [ ] **Step 2: Write `SetCard.tsx`**

```tsx
"use client";

import type { Component, EditableField, HardwareSet } from "@/lib/types";
import { ComponentRow } from "./ComponentRow";

type Props = {
  set: HardwareSet;
  onEditField: (componentIndex: number, field: EditableField, value: string | number | null) => void;
  onAddComponent: () => void;
  onRemoveComponent: (index: number) => void;
  onDeleteSet: () => void;
  isDeleted: boolean;
};

export function SetCard({
  set,
  onEditField,
  onAddComponent,
  onRemoveComponent,
  onDeleteSet,
  isDeleted,
}: Props) {
  return (
    <div className={isDeleted ? "opacity-40" : ""}>
      <div className="flex items-baseline justify-between mb-4">
        <div>
          <div className="font-mono text-[10px] tracking-[0.3em] uppercase text-ink-dim">
            SET · {set.set_number} · p.{set.location.page}
            {set.is_not_used ? " · NOT USED" : ""}
          </div>
          <h2 className="font-serif text-3xl mt-1">
            {set.description ? <em>{set.description}</em> : <span className="text-ink-dim">(untitled)</span>}
          </h2>
        </div>

        <div className="flex items-center gap-2">
          <div className="text-[10px] tracking-[0.3em] uppercase text-ink-dim">
            CONF {set.confidence.toFixed(2)}
          </div>
          <button
            onClick={onDeleteSet}
            className="text-[10px] tracking-[0.2em] uppercase font-mono text-ink-dim hover:text-red-300 border border-cyan-dim/40 px-2 py-1 rounded-sm"
          >
            {isDeleted ? "UNDO DELETE" : "DELETE SET"}
          </button>
        </div>
      </div>

      <div className="flex items-center gap-2 py-1 border-b border-cyan-dim font-mono text-[10px] tracking-[0.25em] uppercase text-ink-dim">
        <span className="w-10">QTY</span>
        <span className="flex-1">DESCRIPTION</span>
        <span className="w-48">CATALOG</span>
        <span className="w-20">MFR</span>
        <span className="w-20">FINISH</span>
        <span className="w-32">NOTES</span>
        <span className="w-12">CONF</span>
        <span className="w-6" />
      </div>

      {set.components.map((c: Component, i: number) => (
        <ComponentRow
          key={i}
          component={c}
          onEdit={(field, value) => onEditField(i, field, value)}
          onRemove={() => onRemoveComponent(i)}
        />
      ))}

      {!set.components.length && (
        <div className="py-3 text-[11px] text-ink-dim font-mono italic">
          {set.is_not_used ? "NOT USED — no components." : "No components emitted."}
        </div>
      )}

      <button
        onClick={onAddComponent}
        className="mt-3 text-[10px] tracking-[0.3em] uppercase font-mono text-cyan border border-cyan-dim/60 px-3 py-1 rounded-sm hover:bg-cyan/10"
      >
        + ADD COMPONENT
      </button>
    </div>
  );
}
```

- [ ] **Step 3: Wire `SetCard` into `/extract/page.tsx`**

In `frontend/app/extract/page.tsx`, replace the `<pre>...</pre>` block inside the right `<section>` with `SetCard`, and add the edit/delete handlers. Replace the selected-set `<section>` block with:

```tsx
            <section className="overflow-y-auto border border-cyan-dim rounded-sm bg-paper2/40 p-4">
              {sets[selected] ? (
                <SetCard
                  set={applied[selected] ?? sets[selected]}
                  isDeleted={deletedSets.has(sets[selected].set_number)}
                  onEditField={(ci, field, value) =>
                    editField(sets[selected].set_number, ci, field, value)
                  }
                  onAddComponent={() => addComponent(sets[selected].set_number)}
                  onRemoveComponent={(ci) => removeComponent(sets[selected].set_number, ci)}
                  onDeleteSet={() => toggleDeleteSet(sets[selected].set_number)}
                />
              ) : (
                <div className="text-[11px] text-ink-dim font-mono">select a set</div>
              )}
            </section>
```

At the top of the `ExtractPage` component, add `import` and state hooks:

```tsx
import { SetCard } from "../components/SetCard";
import type { Correction, EditableField } from "@/lib/types";
```

Inside `ExtractPage()` (after the existing `useState` calls), add:

```tsx
  const [corrections, setCorrections] = useState<Correction[]>([]);
  const [deletedSets, setDeletedSets] = useState<Set<string>>(new Set());
  const [applied, setApplied] = useState<Record<number, HardwareSet>>({});

  const editField = useCallback(
    (setNumber: string, componentIndex: number, field: EditableField, value: string | number | null) => {
      const setIdx = sets.findIndex((s) => s.set_number === setNumber);
      if (setIdx < 0) return;
      const current = applied[setIdx] ?? sets[setIdx];
      const before = current.components[componentIndex]?.[field] ?? null;
      if (before === value) return;

      const nextComponents = current.components.map((c, i) =>
        i === componentIndex ? { ...c, [field]: value } : c,
      );
      const nextSet = { ...current, components: nextComponents };
      setApplied((prev) => ({ ...prev, [setIdx]: nextSet }));
      setCorrections((prev) => [
        ...prev,
        { type: "field", set_number: setNumber, component_index: componentIndex, field, before, after: value },
      ]);
    },
    [applied, sets],
  );

  const addComponent = useCallback(
    (setNumber: string) => {
      const setIdx = sets.findIndex((s) => s.set_number === setNumber);
      if (setIdx < 0) return;
      const current = applied[setIdx] ?? sets[setIdx];
      const newComp = {
        qty: null,
        description: null,
        catalog_number: null,
        mfr: null,
        finish: null,
        notes: null,
        confidence: {},
      };
      const nextSet = { ...current, components: [...current.components, newComp] };
      setApplied((prev) => ({ ...prev, [setIdx]: nextSet }));
      setCorrections((prev) => [
        ...prev,
        { type: "add_component", set_number: setNumber, component_index: nextSet.components.length - 1 },
      ]);
    },
    [applied, sets],
  );

  const removeComponent = useCallback(
    (setNumber: string, componentIndex: number) => {
      const setIdx = sets.findIndex((s) => s.set_number === setNumber);
      if (setIdx < 0) return;
      const current = applied[setIdx] ?? sets[setIdx];
      const nextComponents = current.components.filter((_, i) => i !== componentIndex);
      const nextSet = { ...current, components: nextComponents };
      setApplied((prev) => ({ ...prev, [setIdx]: nextSet }));
      setCorrections((prev) => [
        ...prev,
        { type: "remove_component", set_number: setNumber, component_index: componentIndex },
      ]);
    },
    [applied, sets],
  );

  const toggleDeleteSet = useCallback((setNumber: string) => {
    setDeletedSets((prev) => {
      const next = new Set(prev);
      if (next.has(setNumber)) {
        next.delete(setNumber);
      } else {
        next.add(setNumber);
      }
      return next;
    });
    setCorrections((prev) => [...prev, { type: "delete_set", set_number: setNumber }]);
  }, []);
```

- [ ] **Step 4: Typecheck + build**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: clean.

- [ ] **Step 5: Manual smoke test — editing**

With both servers running, re-extract a PDF. Click a component field — it becomes an input. Edit, press Enter. Value updates. Click "DELETE SET" — the card dims.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/components/SetCard.tsx frontend/app/components/ComponentRow.tsx frontend/app/extract/page.tsx
git commit -m "frontend: SetCard + ComponentRow with inline editing"
```

## Task 18: Evidence pane with react-pdf + bbox overlay

**Files:**
- Create: `frontend/app/components/EvidencePane.tsx`
- Create: `frontend/app/components/EvidenceTextTab.tsx`
- Modify: `frontend/app/extract/page.tsx` (mount `EvidencePane` + text tab)

- [ ] **Step 1: Write `EvidencePane.tsx`**

```tsx
"use client";

import { useEffect, useMemo, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import type { BBox, SetLocation } from "@/lib/types";

// Serve pdfjs worker from the same version as pdfjs-dist
pdfjs.GlobalWorkerOptions.workerSrc = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.mjs`;

type Props = {
  pdfUrl: string;             // `${API}/pdf/${sessionId}`
  location: SetLocation | null;
  continued: SetLocation[];
};

type PageDims = { width: number; height: number };

export function EvidencePane({ pdfUrl, location, continued }: Props) {
  const pageNum = location?.page ?? 1;
  const [dims, setDims] = useState<PageDims | null>(null);
  const [renderedWidth, setRenderedWidth] = useState(0);

  // Reset dims when navigating to a different PDF page
  useEffect(() => {
    setDims(null);
  }, [pageNum]);

  const bboxes = useMemo(() => {
    const out: Array<{ page: number; bbox: BBox }> = [];
    if (location?.bbox) out.push({ page: location.page, bbox: location.bbox });
    for (const c of continued) if (c.bbox) out.push({ page: c.page, bbox: c.bbox });
    return out.filter((b) => b.page === pageNum);
  }, [location, continued, pageNum]);

  const scale = useMemo(() => {
    if (!dims || !renderedWidth) return 1;
    return renderedWidth / dims.width;
  }, [dims, renderedWidth]);

  return (
    <div className="relative" ref={(el) => setRenderedWidth(el?.clientWidth ?? 0)}>
      <Document
        file={pdfUrl}
        loading={<div className="text-[11px] text-ink-dim font-mono">loading PDF…</div>}
        error={<div className="text-[11px] text-red-300 font-mono">PDF failed to load.</div>}
      >
        <Page
          pageNumber={pageNum}
          width={renderedWidth || undefined}
          onLoadSuccess={(p) => setDims({ width: p.width, height: p.height })}
          renderAnnotationLayer={false}
          renderTextLayer={false}
        />
      </Document>

      {dims &&
        bboxes.map(({ bbox }, i) => {
          const [x0, top, x1, bottom] = bbox;
          return (
            <div
              key={i}
              aria-hidden
              className="pointer-events-none absolute border-2 border-cyan/80 bg-cyan/10 rounded-sm"
              style={{
                left: x0 * scale,
                top: top * scale,
                width: (x1 - x0) * scale,
                height: (bottom - top) * scale,
              }}
            />
          );
        })}
    </div>
  );
}
```

- [ ] **Step 2: Write `EvidenceTextTab.tsx`** (shows the pdftotext view)

```tsx
"use client";

import type { SetLocation } from "@/lib/types";

type Props = { location: SetLocation | null; filename: string };

export function EvidenceTextTab({ location, filename }: Props) {
  if (!location) {
    return (
      <div className="text-[11px] text-ink-dim font-mono p-3">
        Select a set to view its source lines.
      </div>
    );
  }
  return (
    <div className="p-3 text-[11px] font-mono text-ink-dim">
      <div className="uppercase tracking-[0.25em] mb-2">
        {filename} · page {location.page} · lines {location.line_range[0]}–{location.line_range[1]}
      </div>
      <div className="opacity-70">
        The primary evidence pane renders the PDF page with a highlight overlay. This tab is a
        placeholder for the pdftotext line view, which will stream in a future iteration.
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Mount `EvidencePane` + tabs in `/extract/page.tsx`**

In `frontend/app/extract/page.tsx`, replace the right-column `<aside>` block with:

```tsx
        <aside className="flex flex-col border border-cyan-dim rounded-sm bg-paper2/40 min-h-[500px]">
          <div className="flex items-center justify-between px-4 py-2 border-b border-cyan-dim">
            <div className="text-[10px] tracking-[0.3em] uppercase text-ink-dim">
              Evidence · {sessionId ? sessionId.slice(0, 8) : "…"} · {filename}
            </div>
            <div className="flex gap-1">
              <button
                onClick={() => setTab("pdf")}
                className={`text-[10px] uppercase tracking-[0.2em] px-2 py-1 rounded-sm ${
                  tab === "pdf" ? "bg-cyan text-paper" : "text-ink-dim hover:text-ink"
                }`}
              >
                PDF
              </button>
              <button
                onClick={() => setTab("text")}
                className={`text-[10px] uppercase tracking-[0.2em] px-2 py-1 rounded-sm ${
                  tab === "text" ? "bg-cyan text-paper" : "text-ink-dim hover:text-ink"
                }`}
              >
                TEXT
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-auto p-4">
            {tab === "pdf" && sessionId ? (
              <EvidencePane
                pdfUrl={`${API_URL}/pdf/${sessionId}`}
                location={sets[selected]?.location ?? null}
                continued={sets[selected]?.continued_on ?? []}
              />
            ) : (
              <EvidenceTextTab location={sets[selected]?.location ?? null} filename={filename} />
            )}
          </div>
        </aside>
```

Add the imports and state near the top of `ExtractPage`:

```tsx
import { EvidencePane } from "../components/EvidencePane";
import { EvidenceTextTab } from "../components/EvidenceTextTab";

// inside the component:
const [tab, setTab] = useState<"pdf" | "text">("pdf");
```

- [ ] **Step 4: Build + smoke test**

Run: `cd frontend && npm run build`
Expected: clean.

Start both servers. Drop a PDF. Click a set with bbox. Expected: right pane renders the PDF page with a cyan rectangle over the correct rows. For sets where bbox is `null` (line-count mismatch pages), page still renders; no overlay.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/components/EvidencePane.tsx frontend/app/components/EvidenceTextTab.tsx frontend/app/extract/page.tsx
git commit -m "frontend: evidence pane with pdf.js + bbox overlay"
```

---

# Phase 5 — Corrections, persistence, export

## Task 19: Corrections diff builder + vitest (TDD)

**Files:**
- Create: `frontend/lib/corrections.ts`
- Create: `frontend/lib/corrections.test.ts`
- Create: `frontend/vitest.config.ts`

- [ ] **Step 1: Write `frontend/vitest.config.ts`**

```ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["lib/**/*.test.ts"],
  },
});
```

- [ ] **Step 2: Write the failing test**

Create `frontend/lib/corrections.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { buildExport, normalizeCorrections } from "./corrections";
import type { Correction, HardwareSet } from "./types";

const baseSet: HardwareSet = {
  set_number: "1.1",
  description: "RECEPTION",
  location: { page: 40, line_range: [12, 26], bbox: null },
  components: [
    {
      qty: 1, description: "HINGE", catalog_number: "ABC", mfr: "IVE", finish: "630", notes: null,
      confidence: { mfr: 1.0, finish: 1.0, qty: 1.0 },
    },
  ],
  continued_on: [],
  is_not_used: false,
  confidence: 1.0,
  notes: null,
};

describe("normalizeCorrections", () => {
  it("collapses multiple edits of the same field to one before/after", () => {
    const raw: Correction[] = [
      { type: "field", set_number: "1.1", component_index: 0, field: "mfr", before: "IVE", after: "IVS" },
      { type: "field", set_number: "1.1", component_index: 0, field: "mfr", before: "IVS", after: "IVES" },
    ];
    const out = normalizeCorrections(raw);
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({
      type: "field", set_number: "1.1", component_index: 0, field: "mfr", before: "IVE", after: "IVES",
    });
  });

  it("drops field edits that revert to the original value", () => {
    const raw: Correction[] = [
      { type: "field", set_number: "1.1", component_index: 0, field: "mfr", before: "IVE", after: "IVS" },
      { type: "field", set_number: "1.1", component_index: 0, field: "mfr", before: "IVS", after: "IVE" },
    ];
    expect(normalizeCorrections(raw)).toHaveLength(0);
  });

  it("keeps delete_set, add_component, remove_component unchanged", () => {
    const raw: Correction[] = [
      { type: "delete_set", set_number: "1.1" },
      { type: "add_component", set_number: "1.1", component_index: 3 },
      { type: "remove_component", set_number: "1.1", component_index: 2 },
    ];
    expect(normalizeCorrections(raw)).toHaveLength(3);
  });
});

describe("buildExport", () => {
  it("wraps applied sets with corrections diff and metadata", () => {
    const corrections: Correction[] = [
      { type: "field", set_number: "1.1", component_index: 0, field: "mfr", before: "IVE", after: "IVES" },
    ];
    const applied: HardwareSet[] = [
      { ...baseSet, components: [{ ...baseSet.components[0], mfr: "IVES" }] },
    ];
    const out = buildExport({
      sourceFilename: "t.pdf",
      appliedSets: applied,
      corrections,
      extractedAt: "2026-04-21T19:30:00Z",
    });
    expect(out).toMatchObject({
      source_pdf: "t.pdf",
      extracted_at: "2026-04-21T19:30:00Z",
      hardware_sets: applied,
      corrections,
    });
  });
});
```

- [ ] **Step 3: Run the test; it fails (no module yet)**

Run: `cd frontend && npm install && npm test -- --run`
Expected: FAIL — module `./corrections` not found.

- [ ] **Step 4: Implement `corrections.ts`**

```ts
import type { Correction, EditableField, HardwareSet } from "./types";

/**
 * Coalesce repeated edits of the same `(set, component, field)` into a
 * single before/after. Drop edits that revert to the original.
 */
export function normalizeCorrections(raw: Correction[]): Correction[] {
  type Key = string;
  const firstBefore = new Map<Key, unknown>();
  const lastAfter = new Map<Key, unknown>();
  const ordered = new Map<Key, { set_number: string; component_index: number; field: EditableField }>();
  const nonField: Correction[] = [];

  for (const c of raw) {
    if (c.type !== "field") {
      nonField.push(c);
      continue;
    }
    const key = `${c.set_number}::${c.component_index}::${c.field}`;
    if (!firstBefore.has(key)) {
      firstBefore.set(key, c.before);
      ordered.set(key, { set_number: c.set_number, component_index: c.component_index, field: c.field });
    }
    lastAfter.set(key, c.after);
  }

  const fieldOut: Correction[] = [];
  for (const [key, meta] of ordered) {
    const before = firstBefore.get(key);
    const after = lastAfter.get(key);
    if (before === after) continue;
    fieldOut.push({ type: "field", ...meta, before, after });
  }

  return [...fieldOut, ...nonField];
}

export function buildExport(opts: {
  sourceFilename: string;
  appliedSets: HardwareSet[];
  corrections: Correction[];
  extractedAt: string;
}) {
  return {
    source_pdf: opts.sourceFilename,
    extracted_at: opts.extractedAt,
    hardware_sets: opts.appliedSets,
    corrections: normalizeCorrections(opts.corrections),
  };
}
```

- [ ] **Step 5: Run the test; it passes**

Run: `cd frontend && npm test -- --run`
Expected: PASS (all 5 tests).

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/corrections.ts frontend/lib/corrections.test.ts frontend/vitest.config.ts
git commit -m "frontend: corrections diff builder with vitest coverage"
```

## Task 20: `localStorage` persistence keyed by PDF hash

**Files:**
- Create: `frontend/lib/storage.ts`
- Modify: `frontend/app/extract/page.tsx`

- [ ] **Step 1: Write `storage.ts`**

```ts
import type { Correction, HardwareSet } from "./types";

const KEY_PREFIX = "hwsets::";

type Snapshot = {
  corrections: Correction[];
  deletedSets: string[];
  applied: Record<number, HardwareSet>;
  updatedAt: number;
};

export function saveSnapshot(pdfHash: string, snap: Snapshot): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(KEY_PREFIX + pdfHash, JSON.stringify(snap));
  } catch {
    /* quota, private mode, etc. — persistence is best-effort */
  }
}

export function loadSnapshot(pdfHash: string): Snapshot | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(KEY_PREFIX + pdfHash);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Snapshot;
  } catch {
    return null;
  }
}

export function clearSnapshot(pdfHash: string): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(KEY_PREFIX + pdfHash);
}
```

- [ ] **Step 2: Wire into `/extract/page.tsx`**

In `ExtractPage`, track the `pdfHash` on mount (it comes through sessionStorage from landing — update the `pending_pdf` payload already has `hash`). Update the `useEffect` that reads sessionStorage to also store hash in state, and add a second `useEffect` that calls `saveSnapshot` on every change.

Near the existing state hooks, add:

```tsx
import { loadSnapshot, saveSnapshot } from "@/lib/storage";

// inside ExtractPage:
const [pdfHash, setPdfHash] = useState<string>("");
```

Modify the existing `useEffect` that reads `pending_pdf`. Change the handling so it also sets the hash and loads a prior snapshot:

```tsx
  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    const raw = sessionStorage.getItem("pending_pdf");
    if (!raw) {
      router.replace("/");
      return;
    }
    const pending = JSON.parse(raw) as PendingPdf;
    sessionStorage.removeItem("pending_pdf");
    setPdfHash(pending.hash);
    const file = base64ToFile(pending.base64, pending.name);

    // Restore prior edits for this exact PDF, if any
    const prior = loadSnapshot(pending.hash);
    if (prior) {
      setCorrections(prior.corrections);
      setDeletedSets(new Set(prior.deletedSets));
      setApplied(prior.applied);
    }

    streamExtract(API_URL, file, handleEvent).catch((e) => {
      appendLog(String(e), "error");
      setErrorCode("api_error");
      setErrorMessage(String(e));
    });
  }, [handleEvent, router, appendLog]);

  // Persist on every edit
  useEffect(() => {
    if (!pdfHash) return;
    saveSnapshot(pdfHash, {
      corrections,
      deletedSets: [...deletedSets],
      applied,
      updatedAt: Date.now(),
    });
  }, [pdfHash, corrections, deletedSets, applied]);
```

- [ ] **Step 3: Typecheck + smoke test**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: clean.

Start both servers. Extract a PDF, edit a field. Refresh the browser. Expected: on refresh (re-dropping the same PDF), the edit re-appears.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/storage.ts frontend/app/extract/page.tsx
git commit -m "frontend: localStorage snapshot of edits keyed by PDF hash"
```

## Task 21: `ExportMenu` — JSON download + copy

**Files:**
- Create: `frontend/app/components/ExportMenu.tsx`
- Modify: `frontend/app/extract/page.tsx`

- [ ] **Step 1: Write `ExportMenu.tsx`**

```tsx
"use client";

import { useState } from "react";
import type { Correction, HardwareSet } from "@/lib/types";
import { buildExport } from "@/lib/corrections";

type Props = {
  sourceFilename: string;
  sets: HardwareSet[];
  applied: Record<number, HardwareSet>;
  deletedSets: Set<string>;
  corrections: Correction[];
};

export function ExportMenu({ sourceFilename, sets, applied, deletedSets, corrections }: Props) {
  const [copied, setCopied] = useState(false);

  const resolved = sets
    .map((s, i) => applied[i] ?? s)
    .filter((s) => !deletedSets.has(s.set_number));

  const payload = buildExport({
    sourceFilename,
    appliedSets: resolved,
    corrections,
    extractedAt: new Date().toISOString(),
  });

  const download = () => {
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${sourceFilename.replace(/\.pdf$/i, "")}.hardware-sets.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const copy = async () => {
    await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={download}
        disabled={!sets.length}
        className="text-[10px] uppercase tracking-[0.3em] font-mono text-paper bg-cyan px-3 py-1 rounded-sm disabled:opacity-40"
      >
        DOWNLOAD JSON
      </button>
      <button
        onClick={copy}
        disabled={!sets.length}
        className="text-[10px] uppercase tracking-[0.3em] font-mono text-cyan border border-cyan-dim px-3 py-1 rounded-sm hover:bg-cyan/10 disabled:opacity-40"
      >
        {copied ? "COPIED ✓" : "COPY"}
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Mount it in `/extract/page.tsx`**

Add `import { ExportMenu } from "../components/ExportMenu";` to the top of the page. Just above the two-column grid, add a toolbar row:

```tsx
      <div className="flex items-center justify-between px-6 pt-4">
        <div className="text-[10px] tracking-[0.3em] uppercase text-ink-dim">
          {filename || "upload"} · {sets.length} sets · {corrections.length} edits
        </div>
        <ExportMenu
          sourceFilename={filename || "upload.pdf"}
          sets={sets}
          applied={applied}
          deletedSets={deletedSets}
          corrections={corrections}
        />
      </div>
```

Adjust the outer `<div>` to account for the new row (change top padding on the grid container if needed).

- [ ] **Step 3: Smoke test**

Start both servers, extract a PDF, make an edit, click DOWNLOAD JSON. Expected: downloaded file contains `hardware_sets` with the edit applied and `corrections` containing a normalized entry.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/components/ExportMenu.tsx frontend/app/extract/page.tsx
git commit -m "frontend: JSON export with corrections diff"
```

---

# Phase 6 — Error states, deploy, docs

## Task 22: Error + empty states on `/extract`

**Files:**
- Create: `frontend/app/components/ErrorPanel.tsx`
- Modify: `frontend/app/extract/page.tsx`

Render a distinct Blueprint-framed panel on each of the four error codes, plus a "no sets yet / still streaming" empty state.

- [ ] **Step 1: Write `ErrorPanel.tsx`**

```tsx
"use client";

import Link from "next/link";

const COPY: Record<string, { title: string; body: string }> = {
  scanned_pdf: {
    title: "No extractable text",
    body:
      "This PDF looks scanned. The v1 extractor doesn't OCR — we'd need a text-native specbook.",
  },
  no_schedule: {
    title: "Division 08 hardware schedule not detected",
    body:
      "We scanned the whole PDF but didn't find a 08 71 00 door-hardware region. Double-check you uploaded the right file.",
  },
  api_error: {
    title: "Extraction interrupted",
    body:
      "The extraction pipeline hit a recoverable error. Any sets already extracted are preserved below — you can retry or export what you have.",
  },
  parse_error: {
    title: "Couldn't read this PDF",
    body:
      "The file wasn't readable as a valid PDF. Try re-exporting from the source.",
  },
};

export function ErrorPanel({ code, message }: { code: string; message: string }) {
  const { title, body } = COPY[code] ?? { title: "Extraction error", body: message };
  return (
    <div className="mx-auto max-w-xl my-10 border border-cyan-dim rounded-sm bg-paper2/60 p-8">
      <div className="text-[10px] tracking-[0.3em] uppercase text-ink-dim">
        ERROR · {code}
      </div>
      <h2 className="font-serif text-3xl mt-2 mb-3">
        <em>{title}</em>
      </h2>
      <p className="text-[13px] leading-relaxed text-ink-dim mb-2">{body}</p>
      <p className="text-[11px] font-mono text-ink-dim/70 mb-6">{message}</p>
      <Link
        href="/"
        className="text-[10px] tracking-[0.3em] uppercase font-mono text-cyan border border-cyan-dim px-3 py-1 rounded-sm hover:bg-cyan/10"
      >
        UPLOAD ANOTHER
      </Link>
    </div>
  );
}
```

- [ ] **Step 2: Wire into `/extract/page.tsx`**

Add `import { ErrorPanel } from "../components/ErrorPanel";` and render the panel either above the grid (`api_error`, partial results preserved) or instead of the grid (`scanned_pdf`, `no_schedule`, `parse_error`):

```tsx
  const fullReplaceCodes = new Set(["scanned_pdf", "no_schedule", "parse_error"]);

  if (errorCode && fullReplaceCodes.has(errorCode)) {
    return (
      <BlueprintChrome title="02" rev="A" sheet="1·1">
        <ErrorPanel code={errorCode} message={errorMessage ?? ""} />
      </BlueprintChrome>
    );
  }
```

Insert that block right before the `return (` inside `ExtractPage`, and for `api_error` render a banner above the grid:

```tsx
        {errorCode === "api_error" && (
          <div className="px-6 pt-2">
            <ErrorPanel code={errorCode} message={errorMessage ?? ""} />
          </div>
        )}
```

- [ ] **Step 3: Smoke test each code**

Trigger each by:
- `scanned_pdf`: manually add a sample PDF that is scanned (or skip — code path exercised by backend test). For now, manually POST to the backend and confirm you can receive the SSE error.
- `no_schedule`: upload a non-Division-08 PDF (e.g. a random receipt PDF).
- `parse_error`: upload a `.pdf`-renamed text file.

Each should render the framed error panel with an UPLOAD ANOTHER link back to `/`.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/components/ErrorPanel.tsx frontend/app/extract/page.tsx
git commit -m "frontend: Blueprint-framed error panels for each SSE error code"
```

## Task 23: README — one doc covering both platforms

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write/extend the README**

Read the existing README first, then replace its contents with:

```markdown
# Fresco Coding Challenge — Hardware Sets

Extract door-hardware sets from Division 08 specbook PDFs into structured JSON with per-set location data (page, line range, and pixel bounding box). Ships as:

1. A Python CLI (`python -m hardware_sets ...`) — the original pipeline.
2. A FastAPI service (`src/hardware_sets_api/`) — wraps the pipeline, streams typed SSE events.
3. A Next.js frontend (`frontend/`) — drag-drop upload, live streaming, inline editing, PDF evidence pane with bbox highlights.

## Live demo

- **Frontend (Vercel):** <!-- fill in after deploy -->
- **API (Fly.io):** <!-- fill in after deploy -->

## Architecture

```
PDF ─┬─→ filter.py    (pick schedule regions)
     │
     ├─→ layout.py    (pdftotext lines + pdfplumber bboxes)
     │
     ├─→ extract.py   (Claude Sonnet 4.6, tool use)
     │
     └─→ resolve.py   (vocab confidence scoring)
                │
                └─→ SSE events → Next.js UI
```

See `docs/superpowers/specs/` for the full designs.

## Run locally

### Backend

Requires Python 3.12 and `poppler` (for `pdftotext`):

```sh
brew install poppler                        # macOS; apt-get install poppler-utils on Debian
python -m venv .venv && source .venv/bin/activate
pip install -e '.[api,dev]'
export ANTHROPIC_API_KEY=sk-ant-...
uvicorn hardware_sets_api.main:app --port 8000
```

### Frontend

Requires Node 20+:

```sh
cd frontend
cp .env.local.example .env.local            # NEXT_PUBLIC_API_URL defaults to http://localhost:8000
npm install
npm run dev
```

Open <http://localhost:3000>, drop any sample PDF (e.g. `samples/div_08_1.pdf`), and watch it stream.

### CLI-only usage

```sh
python -m hardware_sets samples/div_08_1.pdf --out out/div_08_1.json
```

## Deploy

### Backend (Fly.io)

```sh
fly launch --no-deploy --copy-config        # first time: reads fly.toml
fly secrets set ANTHROPIC_API_KEY=sk-ant-...
fly secrets set ALLOWED_ORIGINS=https://<your-vercel-app>.vercel.app
fly deploy
```

### Frontend (Vercel)

```sh
cd frontend
vercel --prod
# Set NEXT_PUBLIC_API_URL=https://<your-fly-app>.fly.dev in Vercel env settings.
```

## Tests

```sh
pytest                                       # Python: filter patterns, resolve scoring, layout bbox clustering
cd frontend && npm test -- --run             # TypeScript: corrections diff builder
cd frontend && npm run typecheck             # tsc --noEmit
cd frontend && npm run build                 # next build
```

## Output schema

Each hardware set emits:

```json
{
  "set_number": "1.1",
  "description": "RECEPTION",
  "location": { "page": 40, "line_range": [12, 26], "bbox": [50, 100, 555, 240] },
  "continued_on": [],
  "is_not_used": false,
  "components": [
    {
      "qty": 1,
      "description": "HINGE",
      "catalog_number": "...",
      "mfr": "IVES",
      "finish": "630",
      "notes": null,
      "confidence": { "mfr": 1.0, "finish": 1.0, "qty": 1.0 }
    }
  ],
  "confidence": 0.95
}
```

`bbox` is `(x0, top, x1, bottom)` in PDF points (top-left origin, increases downward). `null` when the pdfplumber cluster count disagreed with the pdftotext line count on that page — the UI degrades to "scroll to line, no highlight."

## Known caveats

- **mfr short codes** (e.g. `IVE`, `VON`) are project-local — if a specbook uses a code not in `vocab.py`, it flags as low confidence rather than an error. See `resolve.py` docstring.
- **Scanned PDFs** are detected and rejected; OCR is out of scope for v1.
- **Session PDFs** are held in memory for 10 minutes on the API server. A pod restart drops active sessions.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README covering CLI, API, frontend, deploy"
```

## Task 24: Final CI-style gate sweep

**Files:** (no file changes)

- [ ] **Step 1: Run every verification command**

```sh
# Python
pytest tests/ -v

# Frontend
cd frontend && npm run typecheck && npm test -- --run && npm run build
cd ..

# Docker
docker build -t hardware-sets-api .
```

Expected: all green. Any failures get fixed before claiming the plan complete.

- [ ] **Step 2: Final end-to-end walkthrough**

Start both servers. Upload each of the 3 canonical sample PDFs (`div_08_1.pdf`, `common_lanes_div_8.pdf`, `div_08_Schulz.pdf`). For each:

1. Sets stream into the sidebar.
2. Clicking a set shows the right PDF page with a cyan rectangle over the expected rows.
3. Edit one mfr field, one qty, and delete one set.
4. Refresh the page — restore prior edits offer appears on the same PDF.
5. Download JSON — verify `corrections` array has 3 entries and `hardware_sets` omits the deleted one.

Document any regressions in a follow-up commit before declaring done.

- [ ] **Step 3: Final commit (if any fixes)**

```bash
git add -A
git commit -m "fix: address issues found in final walkthrough" # skip if nothing to fix
```

---

## Self-review against spec §§1–12

- §1 Goal: covered — drag-drop (Task 12), streaming SSE (Tasks 7–8, 15), sets-first layout (Task 16), bbox highlights (Task 18), inline edits (Task 17), export with diff (Task 21).
- §2 Scope in / out: in-scope items all tasked; samples chip row reserved (Task 13) but not populated, per spec.
- §3 Architecture: frontend = Vercel-ready Next.js 15 (Tasks 10–13); backend = FastAPI + Dockerfile + fly.toml (Tasks 5–9); two endpoints (Task 8).
- §4 Data model / bbox addition: Tasks 1–4 add bbox to `NumberedLine`, `SetLocation`, and compute union in `cli.py`.
- §5 SSE event protocol: all 7 event types emitted (Task 7) and consumed (Tasks 15–16).
- §6 Repo layout: every file in the spec exists in the file plan at the top of this doc.
- §7 Blueprint aesthetic: tokens (Task 10), chrome (Task 11), drop zone hero (Task 12), staggered fade / glow (Task 12/13), mono + Fraunces throughout.
- §8 Editing flow: inline edits + delete set + add/remove component (Task 17); corrections export shape (Task 19).
- §9 Error handling: all four codes (Task 22); api_error preserves partial sets.
- §10 Testing: bbox unit test (Task 2), corrections vitest (Task 19), CI gates (Task 24).
- §11 Effort: phases map to spec's day estimates.
- §12 Dependencies: Task 10 package.json (Next, react-pdf, vitest); Task 5 pyproject `[api]` extra (fastapi, uvicorn).
- §13 Key decisions: honored throughout — Layout B split, bbox highlight, SSE streaming, Vercel+Fly, no UI test infra.
