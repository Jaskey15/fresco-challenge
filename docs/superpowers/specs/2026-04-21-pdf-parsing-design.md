# PDF Parsing Design — Hardware Sets Extraction

**Date:** 2026-04-21
**Scope:** PDF parsing component only. Downstream feedback UI, API layer, and deployment are out of scope for this spec.

## 1. Goal

Extract every door-hardware set from a Division 08 specbook PDF into a structured JSON record, including a `location` that names the page and bounding box where the set lives. The extractor must survive the four distinct layouts observed in the sample set and degrade gracefully on a fifth we haven't seen.

## 2. Input assumptions

- **Input:** a single PDF, typically 10–120 pages, covering one or more Division 08 sections. Hardware sets live in section 08 71 00 (or 08 71 10) and usually occupy the last 5–15 pages.
- PDFs are text-native (we've confirmed this across all 10 samples). Scanned PDFs are out of scope — we'll detect and raise rather than OCR.
- A project typically has 5–30 hardware sets, each with 3–15 components.

## 3. Output schema

```json
{
  "source_pdf": "common_lanes_div_8.pdf",
  "hardware_sets": [
    {
      "set_number": "04.1",
      "description": "RECEPTION OFFICE",
      "location": {
        "page": 40,
        "line_range": [12, 26]
      },
      "components": [
        {
          "qty": 1,
          "description": "ANSI Grade 1 Mortise Body Storeroom-Type Lockset with Lever",
          "catalog_number": "6210SM x PVD #IXBSB x M507 x L/C",
          "mfr": "FR",
          "finish": null,
          "notes": null,
          "confidence": {
            "mfr": 0.92,
            "finish": 1.0,
            "qty": 1.0
          }
        }
      ],
      "confidence": 0.88,
      "notes": null
    }
  ],
  "diagnostics": {
    "pages_scanned": 113,
    "pages_with_sets": 47,
    "llm_calls": 6,
    "warnings": []
  }
}
```

- `line_range` is `[first_line, last_line]`, 1-indexed from the top of the page. A "line" is a line as rendered by `pdftotext -layout`. The challenge spec allows either bounding box or line range; line range is simpler to compute, diff in tests, and eyeball against the source PDF. Pixel-precise rectangles can be derived later if needed without breaking the schema.
- For sets that span multiple pages, `location` represents the first page; a `continued_on` array holds additional `{page, line_range}` entries.
- `NOT USED` sets are emitted with `components: []` and `description: "NOT USED"` — never dropped.
- Missing values are `null`, never guessed.

## 4. Architecture

Five modules under a `hardware_sets/` package:

```
hardware_sets/
├── filter.py      # Pick candidate pages (skip narrative)
├── layout.py      # pdftotext -layout → PageLayout (numbered lines)
├── extract.py     # PageLayout → HardwareSet via Claude
├── resolve.py     # Mfr/finish validation + legend-table parsing
└── cli.py         # Entry point: PDF path → JSON
```

### 4.1 `filter.py` — schedule region selection

Goal: cut the LLM bill by 80% by skipping narrative pages. We find the *region(s)* of the PDF that contain the hardware schedule, not individual set headers — the schedule is always contiguous, framing it as region-finding is more robust to edge cases (unanticipated set-header formats, blank pages mid-schedule, full-page notes) and keeps multi-page sets in one LLM batch.

Approach: single scan of `pdftotext -layout` output, tracking start/end markers.

**Start markers** (priority-ordered, first match per region wins):

1. `DOOR HARDWARE SCHEDULE` — Roselle, Schulz style lead-in.
2. `D\.\s*Hardware\s+Sets:` or `^\s*3\.\d+\s+SCHEDULE` — Schulz / Shubenacadie lead-ins.
3. `Hardware\s+(Group|Set)(/Set)?\s*(No\.?|#)?\s*0*1\b` — first "Group 1" header (Commons Lanes, Shubenacadie when no explicit lead-in).
4. Heuristic fallback: a page containing 3+ of `{bare "SET" token on its own line, a "QTY" or "EA" column, a known mfr code, a known finish code}`.

**End markers** (after a region has started):

- `END OF SECTION`
- A new CSI section header (`SECTION\s+\d{6}` or `SECTION\s+\d{2}\s\d{2}\s\d{2}`) different from the current one
- EOF

Scanning continues past each `END OF SECTION` so a PDF containing multiple schedule regions produces multiple results.

**Output:**

```python
@dataclass
class ScheduleRegion:
    start_page: int        # 1-indexed, inclusive
    end_page: int          # 1-indexed, inclusive
    start_marker: str      # which pattern triggered — for debugging
    end_marker: str        # "END OF SECTION" | "new_section" | "eof"

def find_schedule_regions(pdf_path: Path) -> list[ScheduleRegion]
```

**Edge cases:**

- **Scanned PDF** (no extractable text): return `[]`; CLI exits 2 with a `scanned_pdf` warning.
- **Region starts but no end marker found**: close at EOF.
- **Abbreviation/legend table on the page before the first Group** (Schulz): include in the region — `resolve.py` needs it.
- **False-positive start match in narrative** (e.g., "Hardware sets are indicated on Drawings"): the heuristic fallback won't fire without companion signals (mfr/finish codes, QTY column). The explicit markers are specific enough not to match narrative prose.

**Explicitly out of scope for `filter.py`:** identifying individual sets, parsing any content, deciding format (bordered vs list). Those are `extract.py`'s and `layout.py`'s concerns.

### 4.2 `layout.py` — layout extraction

Goal: for each page from `filter.py`, produce a numbered-line representation ready to feed to the LLM. A "line" is what appears as one `L##:` in the prompt and is what the LLM cites back in `location.line_range`.

**Approach: one path, `pdftotext -layout` for every page.** Modern LLMs handle whitespace-aligned columns fine across all four observed formats (Roselle bordered, Commons Lanes bordered with prose titles, Shubenacadie unlabeled list, Schulz labeled list + legend). Merged cells render as "value in the first row, blanks below," which is legible to the LLM. Using a single path keeps the code simple and avoids the trap of losing interstitial prose (Commons Lanes puts set titles *outside* its tables) when swapping in table-detection output.

If testing shows the LLM stumbles on a specific merged-cell layout, we can add pipe-delimited rendering as a targeted enhancement later. v1 does not.

**Output shape:**

```python
@dataclass
class NumberedLine:
    number: int          # 1-indexed from top of page
    text: str            # verbatim pdftotext -layout output for that line

@dataclass
class PageLayout:
    page_number: int
    lines: list[NumberedLine]

def extract_layout(pdf_path: Path, page_num: int) -> PageLayout
```

Blank lines are dropped; the `L##` sequence stays contiguous. A human can open the PDF, count text lines from the top, and match `line_range` reliably.

**Edge cases:**

- Page has no extractable text (scanned) → `lines: []`; `extract.py` skips it.
- Page chrome (headers, footers, page numbers) → **not stripped**. The LLM prompt tells Claude to ignore chrome.
- Embedded product images (Commons Lanes) → not captured; the surrounding text already describes the component.
- Hyphenated word breaks at line ends → left as-is.

**Explicitly out of scope for `layout.py`:** identifying sets or components, classifying mfr vs finish, validating anything, pre-merging multi-page sets.

### 4.3 `extract.py` — LLM-driven structured extraction

Goal: given a `ScheduleRegion` and its `PageLayout`s, produce a list of `HardwareSet` objects.

**Interface:**

```python
def extract_sets(
    region: ScheduleRegion,
    layouts: list[PageLayout],
    *,
    model: str = "claude-sonnet-4-6",
    client: Anthropic | None = None,
) -> list[HardwareSet]
```

**Prompt structure:**

*System prompt* (prompt-cached — doesn't change across calls):

- Role: "You extract door hardware sets from construction specification books."
- Known manufacturer vocabulary: `IVE/IVES/Ives`, `VON/Von Duprin`, `SCH/SCHLAGE/Schlage`, `LCN`, `NGP`, `ZER/Zero`, `PEM/Pemko`, `ROC/Rockwood`, `GLY/Glynn-Johnson`, `HAG/Hager`, `ADA/Adams Rite`, `TRI/Trimco/BBW`, `ABH`, `MED/Medeco`, `SEN/Sentronic`, `ASS/Assa Abloy`, `SCE/Securitron`, `BLU/Blumcraft`, `CRL/C.R. Laurence`, `KNX/Knox`, `RIX/Rixson`.
- Known finish vocabulary: BHMA codes `600–695` (notably `613`, `626`, `630`, `652`, `689`), US codes (`US3/US4/US10/US26/US26D/US32D`), color words (`BLACK`, `BSP`, `PAINTED ENAMEL`, `OIL RUBBED BRONZE`, `LIGHT BRONZE`).
- Disambiguation rule: "Resolve mfr vs finish by looking at the whole column, not individual tokens. A column mostly containing `MK/LCN/SCH` is a manufacturer column; one with `US26D/630/BSP` is a finish column. Codes like `PE` (Pemko vs Painted Enamel) and `NO` (Norton vs the word 'No.') follow the column context."
- Nulls and edges: "Emit `qty: null` rather than guessing when absent. A set marked `NOT USED` / `N/A` is emitted with empty components and `is_not_used: true`. Ignore page headers/footers, project titles, and CSI section markers — those are page chrome, not content."
- Line-citing rule: "For each set, cite the first and last line that belong to it. If the set spans a page break, emit `continued_on` entries for each additional page."

*User prompt* (the region content, one block per page):

```
=== PAGE 15 ===
L01: SECTION 087100
L02: DOOR HARDWARE
L03:
L04: ROSELLE PUBLIC LIBRARY DISTRICT - DOOR HARDWARE SCHEDULE
L05: SET    HARDWARE TYPE         MANUFACTURER - PRODUCT     QTY   FINISH               NOTES
L06: 1.1    CYLINDER / CORE       SCHLAGE - FSIC PRIMUS      1     613 (OIL RUBBED BRONZE)
L07: SLIDING
L08: AUTO
L09: EXTR ENTR
...
=== PAGE 16 ===
L01: ...
```

**Tool schema** (`emit_hardware_sets`):

```json
{
  "sets": [
    {
      "set_number": "1.1",
      "description": "SLIDING AUTO ENTR",
      "location": {"page": 15, "line_range": [6, 9]},
      "continued_on": [],
      "is_not_used": false,
      "components": [
        {
          "qty": 1,
          "description": "CYLINDER / CORE",
          "catalog_number": "FSIC PRIMUS",
          "mfr": "SCHLAGE",
          "finish": "613",
          "notes": null
        }
      ]
    }
  ]
}
```

All string fields use `null` when absent, never empty string. `qty` is integer-or-null.

**Batching:**

- Default: one LLM call per `ScheduleRegion`.
- Large-region guard: if a region's total input tokens exceed ~80K (measured via Anthropic's token counting), chunk at 20-page boundaries with 2 pages of overlap. Merge duplicates post-hoc by `(set_number, first_page)`. None of our samples hit this threshold; it's a safety rail.

**Error handling:**

- Tool-input fails schema → retry once with a structured error message. Second failure → warn, skip region, record in `diagnostics.warnings`.
- Network/API error → bubble up; CLI exits 3.
- Empty response → warn, no sets emitted.

**Model & caching:**

- Model: `claude-sonnet-4-6`. Extraction is well within its competence; Opus costs 5× for no quality gain on this task.
- Caching: system prompt cached with `cache_control: {"type": "ephemeral"}`. Hit across multiple regions or PDFs in one run; the vocabulary block alone is ~800 tokens.
- Thinking: not used. Extraction is pattern-matching, not reasoning.

**Explicitly out of scope for `extract.py`:** vocabulary validation, confidence scoring, legend-table parsing.

### 4.4 `resolve.py` — vocabulary-match scoring

Goal: add a `confidence` field to LLM-extracted sets so downstream tools can sort "look at this first" items. **Never auto-corrects** — surfacing errors to a human beats hiding them behind a heuristic swap.

**Framing (important):** what this module actually measures is "does the extracted value match known vocabulary," not "is the extraction correct." That distinction matters for interpreting output — see the caveat below.

**Interface:**

```python
def validate_and_score(sets: list[HardwareSet]) -> list[HardwareSet]
```

**Purely additive and decoupled.** No prompt or tool-schema changes in `extract.py`. No PDF re-reading. Works solely from the LLM's output against module-local vocabularies. Can be added or removed without touching any other module.

**Per-field confidence rules:**

| Field | Score | Rule |
|---|---|---|
| `mfr` | 1.0 | Exact match in `GLOBAL_MFR_VOCAB` |
| `mfr` | 0.7 | Plausible short code (2–4 chars, all caps) not in vocab |
| `mfr` | 0.2 | Looks like a finish code (3-digit number or `US`-prefixed) |
| `mfr` | 0.5 | Doesn't match any pattern |
| `finish` | 1.0 | Exact match in `GLOBAL_FINISH_VOCAB` |
| `finish` | 0.9 | Matches finish pattern — BHMA 3-digit (`600–695`), `US##[DL]?`, or known color word |
| `finish` | 0.2 | Looks like a mfr code |
| `finish` | 0.5 | Doesn't match any pattern |
| `qty` | 1.0 | Always — LLM emits a number or `null` |
| Others | 1.0 | Descriptive fields can't be validated |

**Roll-up:** component confidence = min of field confidences. Set confidence = mean across components (or 1.0 for `is_not_used` sets).

**Vocabularies** are module-local constants, seeded from the four observed formats:

- `GLOBAL_MFR_VOCAB` — Ives, Von Duprin, Schlage, LCN, NGP, Zero, Pemko, Rockwood, Glynn-Johnson, Hager, Adams Rite, Trimco, ABH, Medeco, Sentronic, Assa Abloy, Securitron, Blumcraft, CRL, Knox, Rixson, Alur, Tubelite (plus common short-code variants: IVE/IVES, VON, SCH, PEM, ZER, ROC, ...).
- `GLOBAL_FINISH_VOCAB` — `613`, `626`, `630`, `652`, `689`, `691`, `693`, `622`, `711`, `BLACK`, `BSP`, `OIL RUBBED BRONZE`, `LIGHT BRONZE`, `MILL ALUM`, etc.
- `FINISH_PATTERNS` — regex for BHMA 3-digit and `US##[DL]?` codes.

**Known caveat: vocabulary generalizability varies.**

| Category | Generalizability | False-alarm risk |
|---|---|---|
| Finish BHMA/US numeric codes | Very high (industry standard ANSI/BHMA A156.18) | Low |
| Finish color words | Moderate | Low |
| Manufacturer full names | High (stable ~30–50 name industry) | Low — fixable by adding a vocab entry |
| Manufacturer **short codes** | **Low** — each book uses project-local abbreviations (IVE vs IVES, VON vs VND) | **Moderate** — will false-alarm on project-specific codes |

So: an `mfr` confidence below 0.7 means "this short code isn't in our global list" — could be a legitimate project-specific abbreviation (Schulz's book defines them in a legend table) **or** a real LLM error. Can't tell without the legend. Documented in the README so downstream consumers don't misread the signal.

If short-code false alarms bite us in testing, the cheapest fix is to re-add the `legend_abbreviations` field to the `extract.py` tool schema and merge per-document legends into the vocab. v1 does not.

**Explicitly out of scope:** auto-correcting mfr↔finish swaps, re-reading the PDF, re-computing line ranges, validating catalog numbers, per-document legend handling.

### 4.5 `cli.py` — glue

Thin orchestrator. Parses args, runs the pipeline, emits JSON.

**Usage:**

```
python -m hardware_sets <pdf_path> [--out <path>] [--model <id>] [--no-score] [--quiet]
```

| Flag | Default | Purpose |
|---|---|---|
| `pdf_path` (positional) | required | PDF to extract from |
| `--out` / `-o` | stdout | Output JSON path |
| `--model` | `claude-sonnet-4-6` | Override model |
| `--no-score` | off | Skip `resolve.py` |
| `--quiet` | off | Suppress progress logs |

`ANTHROPIC_API_KEY` from environment. Missing → exit 1 with a clear message.

**Pipeline:**

```python
def main(argv: list[str]) -> int:
    args = parse_args(argv)
    pdf = Path(args.pdf_path)

    regions = filter.find_schedule_regions(pdf)
    if not regions:
        emit_empty_result(reason="no_schedule_found")
        return 2

    all_sets: list[HardwareSet] = []
    warnings: list[str] = []
    llm_calls = 0

    for region in regions:
        layouts = [layout.extract_layout(pdf, p)
                   for p in range(region.start_page, region.end_page + 1)]
        try:
            sets = extract.extract_sets(region, layouts, model=args.model)
            llm_calls += 1
        except ExtractionError as e:
            warnings.append(f"region {region.start_page}-{region.end_page}: {e}")
            continue
        all_sets.extend(sets)

    if not args.no_score:
        all_sets = resolve.validate_and_score(all_sets)

    emit_result(
        source_pdf=pdf.name,
        hardware_sets=all_sets,
        diagnostics={
            "pages_scanned": total_pages(pdf),
            "regions_found": len(regions),
            "pages_with_sets": sum(r.end_page - r.start_page + 1 for r in regions),
            "llm_calls": llm_calls,
            "warnings": warnings,
        },
    )
    return 0
```

**Exit codes:**

| Code | Meaning |
|---|---|
| 0 | Sets extracted |
| 1 | Usage error — bad args, file not found, missing API key |
| 2 | No schedule region found (includes scanned-PDF case) |
| 3 | LLM/API error that couldn't be recovered |

**Progress logging** to stderr (stdout stays clean JSON). Example:

```
[1/3] filter: found 3 schedule regions (pgs 15-17, 39-44, 65-78)
[2/3] extract: region 1/3 → 5 sets
[2/3] extract: region 2/3 → 8 sets
[2/3] extract: region 3/3 → 22 sets
[3/3] resolve: scored 35 sets
```

Suppressed by `--quiet`.

**Package layout:**

```
src/hardware_sets/
├── __init__.py
├── __main__.py       # forwards to cli.main
├── cli.py
├── filter.py
├── layout.py
├── extract.py
├── resolve.py
├── types.py          # HardwareSet, Component, ScheduleRegion, PageLayout, NumberedLine
└── vocab.py          # GLOBAL_MFR_VOCAB, GLOBAL_FINISH_VOCAB, FINISH_PATTERNS
```

**Dependencies:** `anthropic`, `pdfplumber`, `pypdf` (for page count). Runtime system requirement: `pdftotext` from poppler (README notes `brew install poppler` on macOS).

**Explicitly out of scope for `cli.py`:** retrying LLM calls (extract.py handles that), batching multiple PDFs in one invocation (shell loop), rendering PDFs.

## 5. Data flow

```
PDF path
  │
  ├─→ filter.py ──→ [(15, 17), (39, 44), (65, 78)]  (page ranges)
  │
  ├─→ layout.py ──→ [PageLayout, PageLayout, ...]
  │                       │
  │                       ├─→ resolve.py (legend scan) ──→ legend dict
  │                       │
  │                       └─→ extract.py (Claude, with legend) ──→ [HardwareSet, ...]
  │
  └─→ resolve.py (vocab validation) ──→ HardwareSet with confidence scores
                                  │
                                  └─→ JSON output
```

## 6. Key design decisions

**Why hybrid rather than LLM-only on PDFs?** Claude's native PDF support doesn't give us a way to tie extracted rows back to specific lines on a page, and the challenge explicitly asks for location data per set. Extracting text + line groupings with pdfplumber gets us the `line_range` field natively and lets us pass structured rows (table cells or whitespace-aligned text) rather than rendered page images — cheaper in tokens and more deterministic.

**Why batch by page-range instead of per-page?** Hardware sets span page breaks (observed in the 17-page Roselle schedule and the 113-page Common Lanes book). Batching keeps the LLM aware that a set starting on page 40 may continue on page 41, and lets it emit one record with `continued_on` data.

**Why LLM for column classification instead of a header-row parser?** Two of the four observed formats have no labeled header row (div_08_1, common_lanes). Heuristic column assignment by position works until it doesn't — which is exactly the mfr-vs-finish ambiguity the challenge warns about. An LLM with the full row in context and a vocabulary hint is strictly better here.

**Why `pdftotext -layout` over Camelot/pdfplumber table extraction?** `pdftotext -layout` preserves both bordered and non-bordered column alignment with whitespace, handling all four observed formats from one code path. Camelot and pdfplumber's `extract_tables` are strong on bordered tables but drop interstitial prose (like Commons Lanes' per-set title lines above each bordered box), which would lose set boundaries. We're trusting the LLM to read the column structure, same as a human would.

## 7. Edge cases

| Case | Handling |
|---|---|
| Mfr/finish ambiguity (`PE`, `NO`) | LLM uses column-wide vocabulary. Validated post-hoc; low confidence on mismatch. |
| Missing qty | Emit `qty: null`, confidence 1.0 (we're confident it's absent). |
| NOT USED set | Emit with `components: []`, `description` preserving the "NOT USED" text. |
| Multi-page set | Batched in one LLM call; `continued_on` lists additional pages. |
| Embedded product images (common_lanes) | Recorded in `PageLayout.images` but filtered out of LLM payload. |
| Decimal set numbers (`4.1`, `#04.2`) | Preserved as strings, never numerically parsed. |
| Combined mfr-product cell (`SCHLAGE - L9077 18 L`) | LLM splits; we validate that the `mfr` token appears in the vocabulary. |
| Legend/abbreviation table present | Extracted by `resolve.py`, passed as context into the LLM call. |
| Scanned-only PDF (no extractable text) | `filter.py` returns empty; CLI exits 2 with `scanned_pdf` warning. |

## 8. QA approach

No formal test suite for v1. The fastest and highest-signal QA loop on a prototype is: run the pipeline on every sample PDF, eyeball the JSON against the source PDF, fix what's broken.

**The QA artifact:** `scripts/run_samples.py`. Iterates over every `*.pdf` in `samples/` and writes output JSONs to `out/<pdf_name>.json`. Also writes a brief summary (sets found per PDF, any warnings) to `out/_summary.txt`. This is what we use during development and what the demo video shows.

**Tests we might add later (not now):**

- `resolve.py` vocab-match logic — pure I/O, small. If `resolve.py` survives past v1 and gets used, add ~10 lines of pytest for it.
- Regression fixtures — pin known-good output so future changes can't silently regress. Worth doing once the pipeline is stable; premature before then.

Golden-output tests, pdftotext snapshots, and LLM-output regressions are deliberately out. They'd take hours to set up, produce brittle or noisy signal, and duplicate what manual eyeballing already gives us within this window.

## 9. Out of scope (for this spec)

- Feedback UI for correcting extractions (challenge bonus — separate spec if we pursue it).
- API wrapper / web deployment (separate spec).
- OCR for scanned PDFs.
- Cross-document dedup / merging multiple specbooks.
- Door-schedule parsing (the other half of Division 08 — we only extract hardware sets, not the door schedule that references them).

## 10. Rough cost estimate

- ~50 candidate pages × ~1,500 input tokens (text + coords) × ~500 output tokens per LLM call.
- Batched into ~5 calls per PDF averaging 10 pages each.
- Sonnet 4.6 pricing: ~$0.02 per PDF extracted. Well within acceptable range.
