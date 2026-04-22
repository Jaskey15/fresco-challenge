# Filter Structural Detection Redesign

## Problem

`filter.py` detects hardware schedule regions in specbook PDFs using two stages: named START_PATTERNS (regex matches on page text) gated by a tabular content guard, with a heuristic fallback. Three issues emerged from analysis of all 8 test samples:

1. **The tabular guard is too narrow.** It only recognizes `\d+\s+(EA|Ea.|Set|Pr)` as tabular rows. Roselle p15 (which literally says "DOOR HARDWARE SCHEDULE" in the header and contains dense schedule data) gets 0 tabular matches because its quantities appear without unit words (`3    613`). JC Ryan p24 similarly rejected. Both fall through to the heuristic unnecessarily.

2. **All START_PATTERNS are treated equally.** A pattern like `set_label` matching `Set: EX-1.0` is very specific — if it appears, it's a schedule. But `door_hardware_schedule` matching "DOOR HARDWARE SCHEDULE" fires on every page in the section (it's in the header). Both go through the same tabular guard, which is wrong — high-specificity patterns don't need the guard.

3. **The heuristic depends on static vocabulary.** `vocab.py` contains ~30 hand-curated manufacturer names and ~25 finish codes seeded from 4 early samples. Any unseen specbook with different manufacturers won't get vocab signal. The heuristic also produces false positives — morris_bank p27 and p40 (pure narrative pages) are flagged as schedule starts.

## Current Detection Flow

```
for each page:
  name = _match_start(text)          # try all START_PATTERNS
  if name and not _has_tabular_content(text):
      name = None                    # tabular guard rejects
  if not name and _heuristic_start(text):
      name = "heuristic"             # vocab-based fallback
```

### Current Baseline Results (3 heuristic-dependent samples)

| Sample | Baseline | Actual schedule start | Issue |
|--------|----------|----------------------|-------|
| roselle | p15-17 `heuristic` | p15 — `door_hardware_schedule` matches but tabular guard rejects | Guard too narrow |
| jc_ryan | p24-46 `heuristic` | p24 — `set_label` matches but tabular guard rejects | Guard too narrow |
| morris_bank | p27-33, p40-110 `heuristic` | p53 — `hardware_sets_colon` correctly matches | Heuristic false positive; regions start too early |

## Design

### 1. Tier START_PATTERNS by Confidence

Split patterns into two tiers based on specificity:

**High confidence — bypass tabular guard:**
These patterns match content that only appears on actual schedule pages, not section headers.

- `group_or_set` — `Hardware Group/Set No. X`
- `hw_number` — `HW 5`
- `set_label` — `Set: EX-1`
- `set_hash` — `Set # X`
- `heading_number` — `Heading # 1`

**Low confidence — require tabular guard:**
These patterns match section headers that repeat on every page throughout the section.

- `door_hardware_schedule` — `DOOR HARDWARE SCHEDULE`
- `hardware_sets_colon` — `Hardware Sets:`
- `schedule_section_3dot` — `3.x SCHEDULE`
- `hardware_schedule_head` — `Hardware Schedule` (standalone heading)

Implementation: tag each pattern with a `needs_guard` flag, or split into two lists.

### 2. Broaden the Tabular Guard

Replace the current narrow regexes with a broader structural check. The guard's job is: "This page is in a hardware schedule section — does it contain schedule-format data, or is it still narrative prose?"

**Current (too narrow):**
```python
_TABULAR_ROW_RE = re.compile(r"\b\d+\s+(?:EA(?:-[A-Z])?|Ea\.|Set|Pr)\b", re.I | re.M)
_BARE_QTY_LINE = re.compile(r"^\s+\d+\s+\w", re.M)
```

**Proposed — keep existing checks and add:**

- **Quantity-leading lines:** `^\s*\d+\s+[A-Z]` — lines starting with a digit followed by an uppercase word. Schedules have many of these (component listings); narrative prose has few. Threshold: 3+ matches.
- **Dash-quantity lines:** `\b--\s+\w` — lines using `--` as a quantity placeholder (common in roselle-style schedules).
- **Hardware component keywords on quantity lines:** Lines matching `\d+.*(?:HINGE|CLOSER|LOCKSET|STRIKE|BOLT|THRESHOLD|GASKETING|SWEEP|CYLINDER|STOP)` — a lightweight structural check for hardware terminology co-occurring with quantities. This is format-driven (keyword + quantity pattern), not dictionary-driven.

The guard returns True if ANY of these checks passes. The exact thresholds will be tuned against the baseline.

### 3. Simplify the Heuristic

After tiering patterns and broadening the guard, the heuristic's role shrinks. Strip out vocab dependency; keep structural signals only.

**Current signals (needs 3 of 4):**
1. SET token at start of line
2. QTY/QUANTITY/EA keyword
3. ~~Token in GLOBAL_MFR_VOCAB~~ (remove)
4. ~~Token in GLOBAL_FINISH_VOCAB~~ (remove)

**Proposed signals (needs 2 of 3):**
1. SET token at start of line (keep)
2. QTY/QUANTITY/EA keyword (keep)
3. **Quantity-line density** — 3+ lines matching `^\s*\d+\s+\S` on the page. This is the most universal structural fingerprint of a schedule page.

Lowering the threshold from 3-of-4 to 2-of-3 is safe because the heuristic now only fires on pages that didn't match ANY START_PATTERN (not even low-confidence ones). Its role is catching formats with no recognizable header at all.

### 4. Remove Dead Code

After the changes:
- `filter.py` no longer imports from `vocab.py`
- `resolve.py` (already disconnected from the pipeline — nothing imports it) is the only remaining consumer of `vocab.py`

Remove both `vocab.py` and `resolve.py`. If confidence scoring is revisited later, it should be rebuilt on a different foundation (dynamic vocab from context, column analysis, etc.).

## Expected Baseline Changes

| Sample | Before | After | Change |
|--------|--------|-------|--------|
| roselle | p15-17 `heuristic` | p15-17 `door_hardware_schedule` | Pattern name improves; same pages |
| jc_ryan | p24-46 `heuristic` | p24-46 `set_label` | Pattern name improves; same pages |
| morris_bank | p27-33 + p40-110 `heuristic` | ~p49-110 `hardware_sets_colon` | False-positive region eliminated; start page tightens to actual schedule |
| all others | unchanged | unchanged | No regression |

Morris_bank's exact start page will depend on where `hardware_sets_colon` fires — currently p53 matches this pattern. The region may start slightly earlier if a broadened guard catches an earlier page, but it should no longer start at p27 or p40 (narrative pages).

## Validation Plan

1. Implement changes in `filter.py`
2. Delete `vocab.py` and `resolve.py`
3. Run baseline: `.venv/bin/python scripts/baseline_filter.py 2>/dev/null`
4. Diff against old snapshot — review each change as improvement or regression
5. All 8 samples must detect with correct page ranges
6. Roselle and jc_ryan should show pattern names instead of `heuristic`
7. Morris_bank should show tighter, more accurate region boundaries
8. Update snapshot to new baseline

## Files Changed

- `src/hardware_sets/filter.py` — tier patterns, broaden guard, simplify heuristic
- `src/hardware_sets/vocab.py` — delete
- `src/hardware_sets/resolve.py` — delete
- `scripts/baseline_filter.snapshot` — update after validation
