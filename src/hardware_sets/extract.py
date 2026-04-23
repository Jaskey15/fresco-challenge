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

Known manufacturers (common shortcodes in parentheses):
IVES (IVE), Von Duprin (VON, VND), Schlage (SCH), LCN, NGP, Zero (ZER),
Pemko (PEM), Rockwood (ROC), Glynn-Johnson (GLY, GJ), Hager (HAG),
Adams Rite (ADA), Trimco (TRI, BBW), ABH, Medeco (MED), Sentronic (SEN),
Assa Abloy (ASS), Securitron (SCE), Blumcraft (BLU), C.R. Laurence (CRL),
Knox (KNX), Rixson (RIX), Norton (NOR).
When the PDF uses a shortcode, emit the shortcode as-is.
When the source lists multiple manufacturers separated by slashes
(e.g. "PEM/NGP/ZERO"), preserve the full slash-delimited string.

Known finish vocabulary:
BHMA three-digit codes 600-695 (notably 613, 626, 630, 652, 689),
US codes (US3, US4, US10, US26, US26D, US32D),
color words (BLACK, BSP, PAINTED ENAMEL, OIL RUBBED BRONZE, LIGHT BRONZE).

Disambiguation rule: resolve mfr vs finish by looking at the whole column,
not individual tokens. A column mostly containing MK/LCN/SCH is a manufacturer
column; one with US26D/630/BSP is a finish column. Codes like "PE" (Pemko vs
Painted Enamel) and "NO" (Norton vs the word "No.") follow column context.

Layout patterns you will encounter:
- Labeled list: a heading like "Hardware Group No. 01", "SET 1", or
  "Hardware Set #5" introduces each set, followed by a small table of its
  components. The set ends before the next heading.
- Bordered tabular schedule: one large table with columns like
  SET / HARDWARE TYPE / MANUFACTURER / QTY / FINISH / NOTES. The SET column
  is only populated on the FIRST row of each set (e.g., "1.1", "2.3"); the
  rows that follow with the same set leave the SET column blank or place a
  door-type tag in it like "SINGLE DOOR", "CURTAINWALL", "INTR EGRESS",
  "EXTR ENTR". Group every row up to the next numeric SET value into the
  same set. The set_number is the literal numeric value (e.g., "1.1"). The
  door-type tags collected from those continuation rows form the set's
  description (join them with " / "). Each row whose HARDWARE TYPE column
  is non-empty is one component of the current set.

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

# Every optional-looking field is listed in `required` on purpose: the model
# emits explicit nulls (qty, description, etc.) rather than omitting keys, so
# downstream can distinguish "absent" from "missing". Do not slim this down.
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

import logging

from anthropic import Anthropic

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
MAX_TOKENS = 64000


def _build_user_content(region: ScheduleRegion, layouts: list[PageLayout]) -> str:
    header = (
        f"Schedule region: pages {region.start_page}-{region.end_page} "
        f"(entered via {region.start_marker}).\n\n"
    )
    return header + "\n\n".join(render_for_prompt(lay) for lay in layouts)


def _normalize_line_range(
    raw: list[int] | tuple[int, int],
    *,
    context: str,
) -> tuple[int, int]:
    """Return (first, last). Swap if reversed, logging a warning."""
    first, last = int(raw[0]), int(raw[1])
    if first > last:
        log.warning("%s: line_range reversed (%d, %d); swapped", context, first, last)
        return (last, first)
    return (first, last)


def _coerce_sets(tool_input: dict) -> list[HardwareSet]:
    """Convert tool-use JSON into HardwareSets, auto-fixing fixable invariant
    violations and logging the rest. Structural/schema errors become
    ExtractionError so the caller's retry path triggers."""
    try:
        raw_sets = tool_input.get("sets", [])
        out: list[HardwareSet] = []
        for s in raw_sets:
            set_number = s["set_number"]
            page = s["location"]["page"]
            ctx = f"set {set_number!r} (page {page})"

            loc = SetLocation(
                page=page,
                line_range=_normalize_line_range(s["location"]["line_range"], context=ctx),
            )
            cont = [
                SetLocation(
                    page=c["page"],
                    line_range=_normalize_line_range(
                        c["line_range"], context=f"{ctx} continued_on[{i}]"
                    ),
                )
                for i, c in enumerate(s.get("continued_on", []))
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
            is_not_used = bool(s.get("is_not_used", False))

            if is_not_used and components:
                log.warning(
                    "%s: is_not_used=true but %d components present; keeping both as emitted",
                    ctx, len(components),
                )
            if not set_number.strip():
                log.warning("%s: empty set_number; keeping as emitted", ctx)

            out.append(
                HardwareSet(
                    set_number=set_number,
                    description=s.get("description"),
                    location=loc,
                    continued_on=cont,
                    is_not_used=is_not_used,
                    components=components,
                )
            )
    except (KeyError, TypeError, ValueError) as e:
        raise ExtractionError(f"tool_use payload malformed: {e}") from e

    _warn_duplicate_set_numbers(out)
    return out


def _warn_duplicate_set_numbers(sets: list[HardwareSet]) -> None:
    seen: dict[str, int] = {}
    for s in sets:
        seen[s.set_number] = seen.get(s.set_number, 0) + 1
    for number, count in seen.items():
        if count > 1:
            log.warning("duplicate set_number %r appears %d times", number, count)


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

    # Streaming so MAX_TOKENS can exceed the 10-min sync cap on dense regions.
    with client.messages.stream(
        model=model,
        max_tokens=MAX_TOKENS,
        temperature=0,
        system=system_blocks,
        tools=[EMIT_HARDWARE_SETS_TOOL],
        tool_choice={"type": "tool", "name": EMIT_HARDWARE_SETS_TOOL["name"]},
        messages=[{"role": "user", "content": user_blocks}],
    ) as stream:
        resp = stream.get_final_message()

    if resp.stop_reason == "max_tokens":
        log.warning(
            "extract: hit max_tokens cap (%d); output likely truncated",
            MAX_TOKENS,
        )

    for block in resp.content:
        if block.type == "tool_use" and block.name == EMIT_HARDWARE_SETS_TOOL["name"]:
            return _coerce_sets(block.input)
    raise ExtractionError("model did not call emit_hardware_sets")


def extract_sets(
    region: ScheduleRegion,
    layouts: list[PageLayout],
    *,
    model: str = DEFAULT_MODEL,
    client: Anthropic | None = None,
) -> list[HardwareSet]:
    if client is None:
        client = Anthropic()

    user_content = _build_user_content(region, layouts)
    try:
        return _call_model(client, model, user_content)
    except ExtractionError as e:
        log.warning("extract_sets: retry after %s", e)
        return _call_model(client, model, user_content, retry_note=str(e))


def _union_bbox(
    layouts: list[PageLayout], page: int, line_range: tuple[int, int],
) -> tuple[float, float, float, float] | None:
    page_layout = next((lay for lay in layouts if lay.page_number == page), None)
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


def attach_bboxes(sets: list[HardwareSet], layouts: list[PageLayout]) -> None:
    for s in sets:
        s.location.bbox = _union_bbox(layouts, s.location.page, s.location.line_range)
        for cont in s.continued_on:
            cont.bbox = _union_bbox(layouts, cont.page, cont.line_range)
