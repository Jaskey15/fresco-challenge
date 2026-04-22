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
