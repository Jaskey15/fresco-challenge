# Baseline Testing Pattern for Pipeline Hardening

## What We Did (filter.py)

### Goal
Test `find_schedule_regions()` across all 8 sample PDFs to see how well the filter detects hardware schedule page ranges, then harden the detection based on what we found.

### Process
1. **Read the module** to understand the detection logic (named patterns, guard, heuristic fallback).
2. **Wrote `scripts/baseline_filter.py`** — a simple script that runs the function against every sample and prints region count, page ranges, start marker, and end marker.
3. **Captured output to `scripts/baseline_filter.snapshot`** — the frozen baseline to diff against after changes.
4. **Analyzed the results** — identified which samples were detected via named pattern vs. heuristic vs. not at all. Found 3 root causes: guard too narrow, missing patterns, existing patterns too restrictive.
5. **Made targeted changes** to patterns and guard, reran the baseline, diffed against snapshot.
6. **Investigated unexpected changes** (star_hardware split into 2 regions turned out to be an improvement, not a regression).
7. **Updated snapshot and committed.**

### Diff workflow
```bash
.venv/bin/python scripts/baseline_filter.py 2>/dev/null | diff scripts/baseline_filter.snapshot -
```

### What we found
- 5 of 7 detected samples were falling through to heuristic — named patterns weren't covering real formats.
- Added 5 new named patterns (hw_number, set_label, set_hash, heading_number, hardware_schedule_head).
- Broadened the tabular content guard beyond "N EA" rows.
- Bridgeport went from 0 regions to detected. SJC and star promoted from heuristic to named patterns.
- Morris Bank has a harmless false-positive region (aluminum storefronts prose) — costs extra tokens but doesn't affect correctness.

## What We Did (layout.py)

### Goal
Test `extract_layout()` across all 8 sample PDFs to check whether `pdftotext -layout` rendering produces clean, readable output for the pages identified by filter.

### Process
1. **Read the module** — thin wrapper: shells out to `pdftotext -layout`, drops blank lines, numbers remaining lines contiguously.
2. **Wrote `scripts/baseline_layout.py`** — for each sample, runs `find_schedule_regions()` to get page ranges, then renders first/mid/last pages per region. Prints line count, first 3 lines, last 3 lines (truncated to 100 chars).
3. **Captured output to `scripts/baseline_layout.snapshot`**.
4. **Analyzed the results** — all 8 samples render successfully with reasonable line counts (12–94 per page).

### Diff workflow
```bash
.venv/bin/python scripts/baseline_layout.py 2>/dev/null | diff scripts/baseline_layout.snapshot -
```

### What we found
- All samples produce clean, readable output. No garbled columns, no encoding issues, no merged/split lines.
- **star_hardware**: Content is pushed far right by whitespace in the PDF (wide tabular layout). `pdftotext -layout` preserves this, so lines start 100+ chars in. This is a `pdftotext` behavior, not a layout.py issue — the data is present and correct.
- **morris_bank region 0** (pages 27–33): Confirms the known false-positive from filter — renders aluminum storefronts prose, not schedule data.
- **No hardening needed.** The module is a thin pass-through to `pdftotext` with minimal logic (blank-line stripping, line numbering). Nothing to tune.

## Applying This Pattern to Remaining Modules

The pipeline flows: **filter → layout → extract → resolve**

### extract.py — LLM extraction
- **What it does**: Sends rendered pages to Claude and parses structured JSON (sets with components).
- **What to test**: For each sample, run extraction on the filtered regions and check: set count, set numbers found, component counts per set, presence of NOT USED sets.
- **Baseline script**: Run extraction, capture set_number list and component count per set. This is the most expensive step (LLM calls), so consider caching results to `out/` and diffing against those.
- **What to look for**: Missing sets, hallucinated sets, wrong set numbers, missing components, mfr/finish swaps.

### resolve.py — Post-processing / scoring
- **What it does**: Scores extraction confidence, resolves ambiguous mfr/finish codes.
- **What to test**: Already has unit tests (`test_resolve_scoring.py`). Baseline testing would run resolve on extract output and check confidence scores across samples.
- **Baseline script**: Capture per-set confidence scores and any fields that got resolved/changed.
- **What to look for**: Low confidence scores (flag extraction issues), mfr/finish misclassifications.

### General pattern for each module
1. Write `scripts/baseline_{module}.py` that runs the module's main function against all samples.
2. Print a compact, diffable summary (not raw data — just the key metrics).
3. Save to `scripts/baseline_{module}.snapshot`.
4. Analyze, harden, diff, repeat.
