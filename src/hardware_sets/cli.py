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
            sets = extract_mod.attach_bboxes(sets, layouts)
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
