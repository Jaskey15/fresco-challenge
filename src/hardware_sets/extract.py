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
