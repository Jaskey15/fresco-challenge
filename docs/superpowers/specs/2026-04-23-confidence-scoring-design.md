# Confidence Scoring Design

## Overview

A post-extraction heuristic scoring system that flags fields likely to contain extraction errors. No extra API calls — pure Python validation against known patterns and document-level cross-referencing.

## Architecture

### New module: `src/hardware_sets/confidence.py`

Single function entry point:

```python
def score_confidence(sets: list[HardwareSet], layouts: dict[int, PageLayout]) -> None:
    """Mutate sets in-place: populate Component.confidence dicts and HardwareSet.confidence."""
```

Called after `extract_sets()` and `attach_bboxes()`, before serialization.

### Data structure change

`Component.confidence` changes from `dict[str, float]` to `dict[str, FieldScore]`:

```python
@dataclass
class FieldScore:
    score: float        # 0.0 to 1.0
    reason: str | None  # human-readable explanation, null when score is 1.0
```

`HardwareSet.confidence` remains `float` (the rollup).

### Threshold constant

```python
REVIEW_THRESHOLD = 0.5
```

Any set with `confidence < REVIEW_THRESHOLD` is flagged for review. Tunable later.

## Scoring Rules

### Finish (regex-based)

| Score | Condition |
|-------|-----------|
| 1.0 | Matches known pattern: BHMA numeric (600-695), US-code (US26D, US32D), three-digit metal code (626, 630, 652), color words (BRASS, BRONZE, CHROME, SATIN, etc.) |
| 1.0 | Null (many components legitimately lack a finish) |
| 0.5 | Non-null, doesn't match any known pattern. Reason: "finish code not recognized" |

### Manufacturer (document cross-reference + finish-regex guard)

Build a frequency map of all mfr values across the entire document.

**When document has 5+ sets:**

| Score | Condition |
|-------|-----------|
| 1.0 | Value appears as mfr in 2+ sets |
| 0.7 | Appears once, does NOT match finish regex. Reason: "manufacturer code seen only once" |
| 0.3 | Matches a finish regex pattern. Reason: "matches finish pattern — possible mfr/finish swap" |
| 1.0 | Null |

**When document has fewer than 5 sets (small-document fallback):**

| Score | Condition |
|-------|-----------|
| 1.0 | Does NOT match finish regex |
| 0.3 | Matches finish regex. Reason: "matches finish pattern — possible mfr/finish swap" |
| 1.0 | Null |

The frequency map still gets built but single-appearance is not penalized when the whole document is small.

### Catalog Number (format check)

| Score | Condition |
|-------|-----------|
| 1.0 | Contains both letters and digits, optionally with hyphens/dots/spaces |
| 1.0 | Null |
| 0.5 | Purely numeric or purely alphabetic. Reason: "unusual catalog number format" |
| 0.3 | Matches a finish or mfr-like pattern. Reason: "looks like a finish/mfr code, not a catalog number" |

### Quantity

| Score | Condition |
|-------|-----------|
| 1.0 | Non-null integer |
| 1.0 | Null, and no other components in the same set have quantities |
| 0.5 | Null, but other components in the same set have quantities. Reason: "missing quantity while other components have one" |

### Description

| Score | Condition |
|-------|-----------|
| 1.0 | Non-null, 3+ characters |
| 0.5 | Non-null, 1-2 characters. Reason: "very short description — possible parsing artifact" |
| 0.3 | Null. Reason: "missing description" |

### Notes

Not scored. Always 1.0 — notes are freeform and optional by nature.

## Set-Level Rollup

```python
HardwareSet.confidence = min(all field scores across all components)
```

Structural modifier applied after rollup:
- **Page-break penalty: -0.1** if the set has `continued_on` entries

Floor at 0.0, cap at 1.0.

One low-confidence field tanks the entire set — intentional, since the UI shows a binary "needs review" flag per set.

## Frontend Integration

### Set chips (existing selector: 101, 103, 104)

- **No change** for confident sets — stays white (unselected) / green (selected) as-is
- **Yellow dot** added to sets where `confidence < REVIEW_THRESHOLD`
- Selected state remains green regardless of confidence

### Component table (set detail view)

- Low-confidence cells (`score < REVIEW_THRESHOLD`) get a subtle yellow background highlight
- Tooltip on hover shows the `reason` string from `FieldScore`
- High-confidence cells are untouched

### API response

No schema change needed. `Component.confidence` already exists as a dict. The values change from `float` to `{score, reason}` objects. `HardwareSet.confidence` remains a float. Frontend reads both.

## Testing

- Unit tests in `tests/test_confidence.py` with synthetic `HardwareSet` data
- Test cases:
  - Known finish codes score 1.0
  - Unknown finish codes score 0.5
  - Mfr value matching finish regex scores 0.3
  - Small-document fallback behavior (< 5 sets)
  - Null handling for each field
  - Set rollup: min aggregation + page-break penalty
  - Threshold boundary: sets at exactly 0.5 vs just below

## Files to create/modify

- **Create:** `src/hardware_sets/confidence.py` — scoring logic
- **Modify:** `src/hardware_sets/types.py` — add `FieldScore` dataclass, update `Component.confidence` type
- **Modify:** `src/hardware_sets/cli.py` — call `score_confidence()` after extraction
- **Modify:** `src/hardware_sets_api/pipeline.py` — same integration point
- **Modify:** frontend `SetGrid` component — yellow dot on flagged sets
- **Modify:** frontend component table — cell highlights + tooltips
- **Create:** `tests/test_confidence.py`
