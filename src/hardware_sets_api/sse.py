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
