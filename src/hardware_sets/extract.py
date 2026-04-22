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
