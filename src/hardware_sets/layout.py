"""Render one PDF page into a list of numbered lines for the LLM.

See spec §4.2. Blank lines are dropped; `L##` stays contiguous so a
human (or the LLM) can count lines in the rendered text and match
`location.line_range` back to the source PDF.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from hardware_sets.types import NumberedLine, PageLayout


def cluster_words_into_lines(
    words: list[dict],
    *,
    y_tol: float = 3.0,
) -> list[tuple[str, tuple[float, float, float, float]]]:
    if not words:
        return []

    items = sorted(words, key=lambda w: (float(w["top"]), float(w["x0"])))

    clusters: list[list[dict]] = []
    for w in items:
        placed = False
        for c in clusters:
            if abs(float(c[0]["top"]) - float(w["top"])) <= y_tol:
                c.append(w)
                placed = True
                break
        if not placed:
            clusters.append([w])

    result: list[tuple[str, tuple[float, float, float, float]]] = []
    for c in clusters:
        c.sort(key=lambda w: float(w["x0"]))
        text = " ".join(w["text"] for w in c)
        x0 = min(float(w["x0"]) for w in c)
        top = min(float(w["top"]) for w in c)
        x1 = max(float(w["x1"]) for w in c)
        bottom = max(float(w["bottom"]) for w in c)
        result.append((text, (x0, top, x1, bottom)))

    result.sort(key=lambda r: r[1][1])
    return result


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
