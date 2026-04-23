from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Callable

from pypdf import PdfReader

from hardware_sets import filter as filter_mod
from hardware_sets import layout as layout_mod
from hardware_sets import extract as extract_mod
from hardware_sets.extract import attach_bboxes
from hardware_sets.types import HardwareSet


def run_pipeline(
    pdf_path: Path,
    on_progress: Callable[[dict], None],
) -> dict:
    total_pages = len(PdfReader(str(pdf_path)).pages)
    on_progress({"phase": "filter", "message": f"Scanning {total_pages} pages..."})

    regions = filter_mod.find_schedule_regions(pdf_path)
    if not regions:
        on_progress({"phase": "filter", "message": "No schedule regions found"})
        return {
            "source_pdf": pdf_path.name,
            "hardware_sets": [],
            "page_layouts": {},
            "diagnostics": {
                "pages_scanned": total_pages,
                "regions_found": 0,
                "pages_with_sets": 0,
                "llm_calls": 0,
                "warnings": ["no_schedule_found"],
            },
        }

    on_progress({
        "phase": "filter",
        "message": f"Found {len(regions)} region(s)",
    })

    all_sets: list[HardwareSet] = []
    all_layouts: dict[str, dict] = {}
    warnings: list[str] = []
    llm_calls = 0

    for i, region in enumerate(regions, start=1):
        on_progress({
            "phase": "extract",
            "message": f"Extracting sets from region {i}/{len(regions)}...",
        })

        layouts = [
            layout_mod.extract_layout(pdf_path, p)
            for p in range(region.start_page, region.end_page + 1)
        ]

        for lay in layouts:
            all_layouts[str(lay.page_number)] = {
                "lines": [
                    {"number": line.number, "text": line.text, "bbox": line.bbox}
                    for line in lay.lines
                ],
                "page_width": lay.page_width,
                "page_height": lay.page_height,
            }

        try:
            sets = extract_mod.extract_sets(region, layouts)
            attach_bboxes(sets, layouts)
            llm_calls += 1
            all_sets.extend(sets)
        except extract_mod.ExtractionError as e:
            warnings.append(f"region {region.start_page}-{region.end_page}: {e}")

    return {
        "source_pdf": pdf_path.name,
        "hardware_sets": [asdict(s) for s in all_sets],
        "page_layouts": all_layouts,
        "diagnostics": {
            "pages_scanned": total_pages,
            "regions_found": len(regions),
            "pages_with_sets": sum(r.end_page - r.start_page + 1 for r in regions),
            "llm_calls": llm_calls,
            "warnings": warnings,
        },
    }
