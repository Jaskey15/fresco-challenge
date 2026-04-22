# Session Findings — Roselle Coverage Gap

**Date:** 2026-04-21
**Context:** End-to-end verification run of the hardware-sets pipeline (plan tasks 11/15/16/18). Findings below cover what surfaced when the pipeline was run against every sample PDF, with the most consequential being a complete extraction failure on the Roselle bordered-tabular layout that was traced, fixed, and verified within the same session.

## TL;DR

- Pipeline already extracted Schulz (15 sets), Commons Lanes (12), and `div_08_1` (3) cleanly out of the box.
- Roselle bordered tabular (`087100_FL_-_Door_Hardware_IFB_REVISED.pdf`) returned **0 sets** despite the filter correctly identifying its region.
- Root cause was **not** prompt comprehension — it was **output token exhaustion**. The model was hitting `max_tokens=8000` mid-tool-call.
- Fix: streaming + `MAX_TOKENS=32000` + a layout-patterns paragraph in `SYSTEM_PROMPT`. Roselle now extracts **33 sets** (`1.1` through `8.3`) in one call. No regression on Schulz.

## Per-sample batch run (initial pass)

| Sample | Exit | Sets | Notes |
|---|---|---|---|
| `081113_FL_-_Hollow_Metal_Doors_and_Frames.pdf` | 2 | — | Non-hardware Div 08; expected |
| `081416_FL_lush_Wood_Doors.pdf` | 2 | — | Non-hardware Div 08; expected |
| `083113_FL_-_Access_Doors_and_Frames.pdf` | 2 | — | Non-hardware Div 08; expected |
| `083113-ACCESS-DOORS-AND-FRAMES_Rev_1.pdf` | 2 | — | Non-hardware Div 08; expected |
| `088000-GLAZING_Rev_1.pdf` | 2 | — | Non-hardware Div 08; expected |
| `088713-DECORATIVE-WINDOW-FILMS_Rev_0.pdf` | 2 | — | Non-hardware Div 08; expected |
| `087100_FL_-_Door_Hardware_IFB_REVISED.pdf` | 0 | **0** | **Region found (pgs 15-17); LLM returned `[]`** |
| `common_lanes_div_8.pdf` | 0 | 12 | Bordered + prose; long run (~7 min) |
| `div_08_1.pdf` | 0 | 3 | Small sample |
| `div_08_Schulz.pdf` | 0 | 15 | Labeled list + legend; clean |

## Diagnosing the Roselle failure

Filter behaviour was fine — `find_schedule_regions` correctly identified pages 15-17 via the heuristic fallback (it's a bordered table without one of the labeled headings). Layout extraction was fine — pages rendered with clean `Lnn:` numbering.

The failure was at the LLM step. To see what the model was actually saying, I called `messages.create` **without** `tool_choice` forcing so any preamble text would surface:

```
STOP REASON: max_tokens
TEXT: I'll analyze all three pages carefully, parsing the bordered tabular schedule format, then emit all hardware sets at once.
TOOL_USE: 0 sets
```

That `stop_reason: max_tokens` was the smoking gun. Re-running with `tool_choice` forced and `MAX_TOKENS=16000`:

```
STOP REASON: max_tokens
USAGE: input_tokens=14291, output_tokens=16000
TOOL_USE: 0 sets   (input keys: [])
```

The model was producing >16K tokens of JSON before completing the tool call, so the tool input arrived as an empty object. Bumping to 32K hit the SDK's 10-minute synchronous request limit instead.

**Why is Roselle output so dense?** The format genuinely demands more JSON per page:

1. ~10 sets/page (vs ~2/page in Schulz). 33 total in one 3-page region.
2. The "MANUFACTURER - PRODUCT" column smashes mfr and product detail together, producing long `catalog_number` values once split.
3. Heavy NOTES column on most rows ("FULL MORTISE, FIVE KNUCKLE BB HINGE", "COORDINATE W/ OWNER'S SECURITY VENDOR", etc.) — Schulz mostly leaves notes null.
4. Parenthetical finish values ("613 (OIL RUBBED BRONZE)" instead of "613").
5. The schema requires all 6 component fields, so even nulls cost ~15 tokens each.

This is a property of the source layout, not a parser flaw — the JSON is honest about the source content.

## The fix

Three coordinated changes in `src/hardware_sets/extract.py`:

1. **Streaming** — switched `_call_model` from `client.messages.create(...)` to `client.messages.stream(...).get_final_message()`. Lifts the SDK's 10-minute sync cap so larger `max_tokens` values can actually complete.
2. **`MAX_TOKENS = 8000` → `32000`** — gives dense regions enough output budget. Sonnet 4.6 supports more if needed.
3. **Layout-patterns paragraph in `SYSTEM_PROMPT`** — explicit guidance for both labeled-list and bordered-tabular formats, including how to handle the SET column being blank on continuation rows and how door-type tags (CURTAINWALL, EXTR ENTR, SINGLE DOOR) become part of the set's description.

## Verification

| Sample | Sets before | Sets after |
|---|---|---|
| IFB Roselle | 0 | **33** (1.1 — 8.3) |
| Schulz | 15 | 15 (unchanged) |

Spot-check on Roselle set `1.2` (page 15, lines 9-16): description joined as `CURTAINWALL / EXTR ENTR / SINGLE DOOR / CARD READER`, six components extracted with correct mfr/finish/catalog splits and `qty=null` on the rows where the source had `--`.

## Known quality gaps (not addressed)

These showed up on Roselle and are worth a follow-up prompt tweak before any reviewer-facing demo:

1. **`mfr` alias-joining.** The model emits "IVE/IVES", "VON/Von Duprin", "PEM/NGP/ZER" — reading our vocab list literally instead of using the form that appears in the source. (For gasketing rows, "PEM/NGP/ZER" is genuinely correct because the source lists three alternative manufacturers per row, but for hinges and locksets it's wrong.) Fix: clarify in the prompt that slashes in the vocabulary list separate aliases — emit whichever form the source uses.
2. **`finish` parentheticals.** "613 (OIL RUBBED BRONZE)" verbatim from source. This tanks `confidence['finish']` from 1.0 to 0.5 because the parenthetical breaks the BHMA pattern match. Fix options: instruct the model to emit just the code and put the color in `notes`; or extend `looks_like_finish` to tolerate "<code> (<color word>)".

Both are pure-prompt or pure-resolve changes — no architecture impact.

## Cost note

Per the user's "demo first, cost second" call, we accepted that dense layouts now cost ~2× to extract because of the larger output budget. That's a structural property of the format, not a regression.

## Open follow-ups

- Re-run the full batch to capture a fresh `out/_summary.txt` after the fix (interrupted mid-session for Commons Lanes; no reason to expect regression but not formally verified).
- Address the two quality gaps above before recording the demo Loom.
- Consider per-page chunking for tabular regions as a cheaper alternative to the 32K output budget — would also let the CLI stream progress.
