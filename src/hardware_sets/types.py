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
    bbox: tuple[float, float, float, float] | None = None  # (x0, top, x1, bottom) in PDF points


@dataclass
class PageLayout:
    page_number: int      # 1-indexed
    lines: list[NumberedLine]
    page_width: float = 0.0   # PDF page width in points
    page_height: float = 0.0  # PDF page height in points


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
    bbox: tuple[float, float, float, float] | None = None  # union of line bboxes


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
