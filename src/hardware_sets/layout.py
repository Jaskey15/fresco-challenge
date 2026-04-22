"""Render one PDF page into a list of numbered lines for the LLM.

See spec §4.2. Blank lines are dropped; `L##` stays contiguous so a
human (or the LLM) can count lines in the rendered text and match
`location.line_range` back to the source PDF.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Iterable

import pdfplumber

from hardware_sets.types import BBox, NumberedLine, PageLayout

log = logging.getLogger(__name__)


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


def render_for_prompt(layout: PageLayout) -> str:
    """Render a PageLayout as the `=== PAGE N === / L01: ...` block the prompt uses."""
    header = f"=== PAGE {layout.page_number} ==="
    body = "\n".join(f"L{line.number:02d}: {line.text}" for line in layout.lines)
    return f"{header}\n{body}"
