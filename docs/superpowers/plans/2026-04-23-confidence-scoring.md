# Confidence Scoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-field heuristic confidence scoring to extracted hardware sets, with a binary "needs review" indicator in the frontend.

**Architecture:** A new `confidence.py` module runs as a post-processing pass after extraction. It scores each component field (finish, mfr, catalog_number, qty, description) using regex patterns and document-level cross-referencing — no extra LLM calls. Scores roll up to a per-set confidence float. The frontend shows a yellow warning dot on set chips below threshold, and highlights low-confidence cells in the detail table with tooltips.

**Tech Stack:** Python dataclasses, `re` module, React/TypeScript/Tailwind

**Spec:** `docs/superpowers/specs/2026-04-23-confidence-scoring-design.md`

---

### Task 1: Add FieldScore type and update Component.confidence

**Files:**
- Modify: `src/hardware_sets/types.py`

- [ ] **Step 1: Add FieldScore dataclass and update Component**

In `src/hardware_sets/types.py`, add `FieldScore` before `Component` and change the confidence field type:

```python
@dataclass
class FieldScore:
    score: float
    reason: str | None = None
```

Update `Component.confidence` from:
```python
confidence: dict[str, float] = field(default_factory=dict)
```
to:
```python
confidence: dict[str, FieldScore] = field(default_factory=dict)
```

- [ ] **Step 2: Run existing tests to confirm nothing breaks**

Run: `.venv/bin/pytest tests/ -v`
Expected: All existing tests PASS (nothing currently reads `Component.confidence` values)

- [ ] **Step 3: Commit**

```bash
git add src/hardware_sets/types.py
git commit -m "types: add FieldScore dataclass, update Component.confidence type"
```

---

### Task 2: Implement finish scoring

**Files:**
- Create: `src/hardware_sets/confidence.py`
- Create: `tests/test_confidence.py`

- [ ] **Step 1: Write failing tests for finish scoring**

Create `tests/test_confidence.py`:

```python
from hardware_sets.confidence import score_finish
from hardware_sets.types import FieldScore


def test_bhma_numeric_codes():
    assert score_finish("626") == FieldScore(1.0, None)
    assert score_finish("630") == FieldScore(1.0, None)
    assert score_finish("652") == FieldScore(1.0, None)
    assert score_finish("613") == FieldScore(1.0, None)


def test_us_codes():
    assert score_finish("US26D") == FieldScore(1.0, None)
    assert score_finish("US32D") == FieldScore(1.0, None)
    assert score_finish("US3") == FieldScore(1.0, None)
    assert score_finish("US10") == FieldScore(1.0, None)


def test_three_digit_metal_codes():
    assert score_finish("689") == FieldScore(1.0, None)
    assert score_finish("695") == FieldScore(1.0, None)


def test_color_words():
    assert score_finish("BSP") == FieldScore(1.0, None)
    assert score_finish("SATIN") == FieldScore(1.0, None)
    assert score_finish("BRASS") == FieldScore(1.0, None)
    assert score_finish("BRONZE") == FieldScore(1.0, None)
    assert score_finish("CHROME") == FieldScore(1.0, None)
    assert score_finish("BLACK") == FieldScore(1.0, None)
    assert score_finish("PAINTED ENAMEL") == FieldScore(1.0, None)
    assert score_finish("OIL RUBBED BRONZE") == FieldScore(1.0, None)
    assert score_finish("LIGHT BRONZE") == FieldScore(1.0, None)


def test_null_finish():
    assert score_finish(None) == FieldScore(1.0, None)


def test_unrecognized_finish():
    assert score_finish("XYZ") == FieldScore(0.5, "finish code not recognized")
    assert score_finish("FOOBAR") == FieldScore(0.5, "finish code not recognized")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_confidence.py -v`
Expected: FAIL (ImportError — module doesn't exist yet)

- [ ] **Step 3: Implement score_finish**

Create `src/hardware_sets/confidence.py`:

```python
from __future__ import annotations

import re

from hardware_sets.types import FieldScore

FINISH_PATTERN = re.compile(
    r"^("
    r"6\d{2}"                          # BHMA 600-699
    r"|US\d{1,2}[A-Z]?"               # US3, US10, US26D, US32D
    r"|BSP|BRASS|BRONZE|CHROME|BLACK"
    r"|SATIN|NICKEL|PEWTER|STAINLESS"
    r"|PAINTED ENAMEL|OIL RUBBED BRONZE|LIGHT BRONZE"
    r"|DARK BRONZE|SATIN BRONZE|SATIN CHROME"
    r"|POLISHED|PRIMED|ALUMINUM|DULL"
    r")$",
    re.IGNORECASE,
)


def _matches_finish(value: str) -> bool:
    return bool(FINISH_PATTERN.match(value.strip()))


def score_finish(value: str | None) -> FieldScore:
    if value is None:
        return FieldScore(1.0, None)
    if _matches_finish(value):
        return FieldScore(1.0, None)
    return FieldScore(0.5, "finish code not recognized")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_confidence.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/hardware_sets/confidence.py tests/test_confidence.py
git commit -m "confidence: implement finish field scoring with regex patterns"
```

---

### Task 3: Implement manufacturer scoring

**Files:**
- Modify: `src/hardware_sets/confidence.py`
- Modify: `tests/test_confidence.py`

- [ ] **Step 1: Write failing tests for manufacturer scoring**

Append to `tests/test_confidence.py`:

```python
from hardware_sets.confidence import score_mfr, build_mfr_frequency


def test_mfr_frequent_in_large_doc():
    freq = {"SCH": 3, "LCN": 5, "MK": 2}
    total_sets = 10
    assert score_mfr("SCH", freq, total_sets) == FieldScore(1.0, None)


def test_mfr_seen_once_no_finish_match_large_doc():
    freq = {"SCH": 3, "LCN": 5, "XYZ": 1}
    total_sets = 10
    assert score_mfr("XYZ", freq, total_sets) == FieldScore(0.7, "manufacturer code seen only once")


def test_mfr_matches_finish_pattern_large_doc():
    freq = {"SCH": 3, "626": 1}
    total_sets = 10
    assert score_mfr("626", freq, total_sets) == FieldScore(0.3, "matches finish pattern — possible mfr/finish swap")


def test_mfr_null():
    freq = {"SCH": 3}
    assert score_mfr(None, freq, 10) == FieldScore(1.0, None)


def test_mfr_small_doc_no_finish_match():
    freq = {"SCH": 1, "LCN": 1}
    total_sets = 3
    assert score_mfr("SCH", freq, total_sets) == FieldScore(1.0, None)


def test_mfr_small_doc_matches_finish():
    freq = {"SCH": 1, "626": 1}
    total_sets = 3
    assert score_mfr("626", freq, total_sets) == FieldScore(0.3, "matches finish pattern — possible mfr/finish swap")


def test_build_mfr_frequency():
    from hardware_sets.types import Component, HardwareSet, SetLocation
    sets = [
        HardwareSet(
            set_number="1", description=None,
            location=SetLocation(page=1, line_range=(1, 5)),
            components=[
                Component(qty=1, description="Hinge", catalog_number=None, mfr="SCH", finish=None, notes=None),
                Component(qty=1, description="Lock", catalog_number=None, mfr="LCN", finish=None, notes=None),
            ],
        ),
        HardwareSet(
            set_number="2", description=None,
            location=SetLocation(page=1, line_range=(6, 10)),
            components=[
                Component(qty=1, description="Closer", catalog_number=None, mfr="SCH", finish=None, notes=None),
            ],
        ),
    ]
    freq = build_mfr_frequency(sets)
    assert freq == {"SCH": 2, "LCN": 1}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_confidence.py::test_mfr_frequent_in_large_doc -v`
Expected: FAIL (ImportError — `score_mfr` not defined)

- [ ] **Step 3: Implement score_mfr and build_mfr_frequency**

Add to `src/hardware_sets/confidence.py`:

```python
from hardware_sets.types import FieldScore, HardwareSet

SMALL_DOC_THRESHOLD = 5


def build_mfr_frequency(sets: list[HardwareSet]) -> dict[str, int]:
    freq: dict[str, int] = {}
    for s in sets:
        seen_in_set: set[str] = set()
        for comp in s.components:
            if comp.mfr and comp.mfr not in seen_in_set:
                seen_in_set.add(comp.mfr)
                freq[comp.mfr] = freq.get(comp.mfr, 0) + 1
    return freq


def score_mfr(
    value: str | None,
    mfr_freq: dict[str, int],
    total_sets: int,
) -> FieldScore:
    if value is None:
        return FieldScore(1.0, None)
    if _matches_finish(value):
        return FieldScore(0.3, "matches finish pattern — possible mfr/finish swap")
    if total_sets >= SMALL_DOC_THRESHOLD:
        count = mfr_freq.get(value, 0)
        if count >= 2:
            return FieldScore(1.0, None)
        return FieldScore(0.7, "manufacturer code seen only once")
    return FieldScore(1.0, None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_confidence.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/hardware_sets/confidence.py tests/test_confidence.py
git commit -m "confidence: implement manufacturer scoring with cross-reference and small-doc fallback"
```

---

### Task 4: Implement catalog_number, qty, and description scoring

**Files:**
- Modify: `src/hardware_sets/confidence.py`
- Modify: `tests/test_confidence.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_confidence.py`:

```python
from hardware_sets.confidence import score_catalog_number, score_qty, score_description


def test_catalog_alphanumeric():
    assert score_catalog_number("A156-18S") == FieldScore(1.0, None)
    assert score_catalog_number("8Q00010-003") == FieldScore(1.0, None)
    assert score_catalog_number("LM9200 EU") == FieldScore(1.0, None)


def test_catalog_null():
    assert score_catalog_number(None) == FieldScore(1.0, None)


def test_catalog_pure_numeric():
    assert score_catalog_number("12345") == FieldScore(0.5, "unusual catalog number format")


def test_catalog_pure_alpha():
    assert score_catalog_number("ABCDE") == FieldScore(0.5, "unusual catalog number format")


def test_catalog_looks_like_finish():
    assert score_catalog_number("US26D") == FieldScore(0.3, "looks like a finish/mfr code, not a catalog number")
    assert score_catalog_number("626") == FieldScore(0.3, "looks like a finish/mfr code, not a catalog number")


def test_qty_present():
    assert score_qty(3, has_siblings_with_qty=True) == FieldScore(1.0, None)


def test_qty_null_siblings_have_qty():
    assert score_qty(None, has_siblings_with_qty=True) == FieldScore(0.5, "missing quantity while other components have one")


def test_qty_null_no_siblings_have_qty():
    assert score_qty(None, has_siblings_with_qty=False) == FieldScore(1.0, None)


def test_description_normal():
    assert score_description("CONTINUOUS HINGE") == FieldScore(1.0, None)


def test_description_short():
    assert score_description("A") == FieldScore(0.5, "very short description — possible parsing artifact")
    assert score_description("AB") == FieldScore(0.5, "very short description — possible parsing artifact")


def test_description_null():
    assert score_description(None) == FieldScore(0.3, "missing description")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_confidence.py::test_catalog_alphanumeric -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement the three scoring functions**

Add to `src/hardware_sets/confidence.py`:

```python
CATALOG_MIXED_PATTERN = re.compile(r"(?=.*[A-Za-z])(?=.*\d)")


def score_catalog_number(value: str | None) -> FieldScore:
    if value is None:
        return FieldScore(1.0, None)
    stripped = value.strip()
    if _matches_finish(stripped):
        return FieldScore(0.3, "looks like a finish/mfr code, not a catalog number")
    if CATALOG_MIXED_PATTERN.search(stripped):
        return FieldScore(1.0, None)
    return FieldScore(0.5, "unusual catalog number format")


def score_qty(value: int | None, *, has_siblings_with_qty: bool) -> FieldScore:
    if value is not None:
        return FieldScore(1.0, None)
    if has_siblings_with_qty:
        return FieldScore(0.5, "missing quantity while other components have one")
    return FieldScore(1.0, None)


def score_description(value: str | None) -> FieldScore:
    if value is None:
        return FieldScore(0.3, "missing description")
    if len(value.strip()) <= 2:
        return FieldScore(0.5, "very short description — possible parsing artifact")
    return FieldScore(1.0, None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_confidence.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/hardware_sets/confidence.py tests/test_confidence.py
git commit -m "confidence: implement catalog_number, qty, and description scoring"
```

---

### Task 5: Implement set-level rollup and score_confidence entry point

**Files:**
- Modify: `src/hardware_sets/confidence.py`
- Modify: `tests/test_confidence.py`

- [ ] **Step 1: Write failing tests for rollup and entry point**

Append to `tests/test_confidence.py`:

```python
from hardware_sets.confidence import score_confidence, REVIEW_THRESHOLD


def _make_set(
    set_number: str,
    components: list[Component],
    continued_on: list[SetLocation] | None = None,
) -> HardwareSet:
    return HardwareSet(
        set_number=set_number,
        description=None,
        location=SetLocation(page=1, line_range=(1, 5)),
        components=components,
        continued_on=continued_on or [],
    )


def test_all_confident_set():
    sets = [_make_set("1", [
        Component(qty=1, description="HINGE", catalog_number="A156-18S", mfr="SCH", finish="626", notes=None),
        Component(qty=2, description="CLOSER", catalog_number="LM9200", mfr="SCH", finish="630", notes=None),
    ])]
    score_confidence(sets)
    assert sets[0].confidence == 1.0


def test_low_confidence_field_tanks_set():
    sets = [_make_set("1", [
        Component(qty=1, description="HINGE", catalog_number="A156-18S", mfr="SCH", finish="626", notes=None),
        Component(qty=1, description=None, catalog_number="LM9200", mfr="SCH", finish="630", notes=None),
    ])]
    score_confidence(sets)
    assert sets[0].confidence == 0.3


def test_page_break_penalty():
    sets = [_make_set(
        "1",
        [Component(qty=1, description="HINGE", catalog_number="A156-18S", mfr="SCH", finish="626", notes=None)],
        continued_on=[SetLocation(page=2, line_range=(1, 3))],
    )]
    score_confidence(sets)
    assert sets[0].confidence == 0.9


def test_page_break_penalty_floors_at_zero():
    sets = [_make_set(
        "1",
        [Component(qty=None, description=None, catalog_number=None, mfr=None, finish=None, notes=None)],
        continued_on=[SetLocation(page=2, line_range=(1, 3))],
    )]
    score_confidence(sets)
    assert sets[0].confidence >= 0.0


def test_component_confidence_dict_populated():
    sets = [_make_set("1", [
        Component(qty=1, description="HINGE", catalog_number="A156-18S", mfr="SCH", finish="XYZ", notes=None),
    ])]
    score_confidence(sets)
    conf = sets[0].components[0].confidence
    assert "finish" in conf
    assert conf["finish"].score == 0.5
    assert conf["finish"].reason == "finish code not recognized"
    assert conf["mfr"].score == 1.0


def test_review_threshold_boundary():
    assert REVIEW_THRESHOLD == 0.5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_confidence.py::test_all_confident_set -v`
Expected: FAIL (ImportError — `score_confidence` not defined)

- [ ] **Step 3: Implement score_confidence**

Add to `src/hardware_sets/confidence.py`:

```python
REVIEW_THRESHOLD = 0.5


def score_confidence(sets: list[HardwareSet]) -> None:
    mfr_freq = build_mfr_frequency(sets)
    total_sets = len(sets)

    for s in sets:
        has_siblings_with_qty = any(c.qty is not None for c in s.components)
        min_score = 1.0

        for comp in s.components:
            comp.confidence = {
                "qty": score_qty(comp.qty, has_siblings_with_qty=has_siblings_with_qty),
                "description": score_description(comp.description),
                "catalog_number": score_catalog_number(comp.catalog_number),
                "mfr": score_mfr(comp.mfr, mfr_freq, total_sets),
                "finish": score_finish(comp.finish),
            }
            for fs in comp.confidence.values():
                if fs.score < min_score:
                    min_score = fs.score

        if s.continued_on:
            min_score = max(0.0, min_score - 0.1)

        s.confidence = min_score
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_confidence.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/hardware_sets/confidence.py tests/test_confidence.py
git commit -m "confidence: implement set-level rollup with page-break penalty"
```

---

### Task 6: Integrate into CLI and API pipeline

**Files:**
- Modify: `src/hardware_sets/cli.py`
- Modify: `src/hardware_sets_api/pipeline.py`

- [ ] **Step 1: Add score_confidence call to cli.py**

In `src/hardware_sets/cli.py`, add the import at the top with the other imports:

```python
from hardware_sets.confidence import score_confidence
```

Then in the `main()` function, after the `for` loop over regions (after `all_sets.extend(sets)`), add:

```python
    score_confidence(all_sets)
```

This should go right before the `result = {` line (around line 113). The final flow is: extract → attach_bboxes → (collect all sets) → score_confidence → serialize.

- [ ] **Step 2: Add score_confidence call to pipeline.py**

In `src/hardware_sets_api/pipeline.py`, add the import:

```python
from hardware_sets.confidence import score_confidence
```

Then after the `for` loop over regions (after `all_sets.extend(sets)`), add:

```python
    score_confidence(all_sets)
```

This goes right before the `return {` line (around line 78).

- [ ] **Step 3: Run existing tests to verify nothing breaks**

Run: `.venv/bin/pytest tests/ -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/hardware_sets/cli.py src/hardware_sets_api/pipeline.py
git commit -m "pipeline: integrate confidence scoring after extraction"
```

---

### Task 7: Serialize FieldScore in JSON output

**Files:**
- Modify: `src/hardware_sets/cli.py`
- Modify: `tests/test_confidence.py`

- [ ] **Step 1: Write a failing test for JSON serialization**

Append to `tests/test_confidence.py`:

```python
import json
from dataclasses import asdict


def test_field_score_serializes_to_json():
    sets = [_make_set("1", [
        Component(qty=1, description="HINGE", catalog_number="A156-18S", mfr="SCH", finish="XYZ", notes=None),
    ])]
    score_confidence(sets)
    result = json.loads(json.dumps(asdict(sets[0]), default=str))
    finish_conf = result["components"][0]["confidence"]["finish"]
    assert finish_conf == {"score": 0.5, "reason": "finish code not recognized"}
```

- [ ] **Step 2: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_confidence.py::test_field_score_serializes_to_json -v`
Expected: PASS (`dataclasses.asdict` recursively converts `FieldScore` to a dict)

- [ ] **Step 3: Commit**

```bash
git add tests/test_confidence.py
git commit -m "test: verify FieldScore JSON serialization via asdict"
```

---

### Task 8: Update frontend types

**Files:**
- Modify: `frontend/src/types.ts`

- [ ] **Step 1: Update Component.confidence type**

In `frontend/src/types.ts`, change the `confidence` field on `Component` from:

```typescript
confidence?: Record<string, number>;
```

to:

```typescript
confidence?: Record<string, { score: number; reason: string | null }>;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/types.ts
git commit -m "frontend: update Component.confidence type to include reason"
```

---

### Task 9: Add yellow warning dot to SetGrid chips

**Files:**
- Modify: `frontend/src/components/SetGrid.tsx`

- [ ] **Step 1: Add the needs-review indicator**

In `frontend/src/components/SetGrid.tsx`, update the button inside the `filtered.map()` to add a yellow dot for low-confidence sets. The `REVIEW_THRESHOLD` is 0.5.

Replace the entire `<button>` block (the one inside `filtered.map()`) with:

```tsx
          <button
            key={index}
            onClick={() => onSelect(index)}
            className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
              index === activeIndex
                ? "bg-green-500 text-white shadow-sm"
                : set.is_not_used
                  ? "bg-gray-100 text-gray-400 hover:bg-gray-200"
                  : "bg-gray-100 text-gray-700 hover:bg-gray-200"
            }`}
            title={set.description || set.set_number}
          >
            {set.confidence < 0.5 && index !== activeIndex && (
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-400 mr-1 align-middle" />
            )}
            {set.set_number}
          </button>
```

- [ ] **Step 2: Start dev server and verify visually**

Run: `cd frontend && npm run dev`

Open in browser. If there are sets with low confidence, they should show a small yellow dot before the set number. Selected (green) sets should NOT show the dot.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/SetGrid.tsx
git commit -m "frontend: add yellow warning dot on low-confidence set chips"
```

---

### Task 10: Add cell highlights and tooltips in DetailTable

**Files:**
- Modify: `frontend/src/components/DetailTable.tsx`

- [ ] **Step 1: Update EditableCell to accept confidence**

In `frontend/src/components/DetailTable.tsx`, update the `EditableCellProps` interface and the `EditableCell` component:

Change `EditableCellProps` to:

```typescript
interface EditableCellProps {
  value: string | number | null;
  isEdited: boolean;
  onCommit: (value: string) => void;
  lowConfidence?: { score: number; reason: string | null } | null;
}
```

Update the `EditableCell` function signature:

```typescript
function EditableCell({ value, isEdited, onCommit, lowConfidence }: EditableCellProps) {
```

Update the non-editing `<div>` return (the `else` branch) to add a yellow highlight and tooltip when `lowConfidence` is present:

```tsx
  return (
    <div
      onClick={startEdit}
      title={lowConfidence?.reason ?? undefined}
      className={`cursor-pointer px-1.5 py-0.5 rounded min-h-[24px] ${
        isEdited
          ? "bg-amber-50 border border-amber-300"
          : lowConfidence
            ? "bg-yellow-50 border border-yellow-300"
            : "hover:bg-gray-50"
      }`}
    >
      {displayValue || <span className="text-gray-300">—</span>}
    </div>
  );
```

- [ ] **Step 2: Pass confidence data from DetailTable to EditableCell**

In the `DetailTable` component, update the `<EditableCell>` inside the `tbody` map to pass the confidence prop. Replace the `<td>` block:

```tsx
                    <td key={col.key} className="px-2 py-1.5">
                      <EditableCell
                        value={getDisplayValue(compIdx, col.key, (comp[col.key] as string | number | null) ?? null)}
                        isEdited={isEdited(compIdx, col.key)}
                        onCommit={(val) => onCellEdit(compIdx, col.key, val)}
                        lowConfidence={
                          col.key !== "notes" && comp.confidence?.[col.key]?.score !== undefined && comp.confidence[col.key].score < 0.5
                            ? comp.confidence[col.key]
                            : null
                        }
                      />
                    </td>
```

- [ ] **Step 3: Update the set header dot color**

In `DetailTable.tsx`, update the green dot next to "Hardware Set {set.set_number}" to reflect confidence. Replace:

```tsx
            <span className="text-green-500 mr-1">●</span>
```

with:

```tsx
            <span className={`mr-1 ${set.confidence < 0.5 ? "text-amber-400" : "text-green-500"}`}>●</span>
```

- [ ] **Step 4: Start dev server and verify visually**

Run: `cd frontend && npm run dev`

Open in browser. Low-confidence cells should have a subtle yellow background with a yellow border. Hovering over them should show the reason as a native tooltip. The header dot should be amber for flagged sets.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/DetailTable.tsx
git commit -m "frontend: highlight low-confidence cells with yellow background and reason tooltips"
```

---

### Task 11: End-to-end verification

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `.venv/bin/pytest tests/ -v`
Expected: All PASS

- [ ] **Step 2: Run CLI on a demo sample**

Run: `.venv/bin/python -m hardware_sets demo_samples/roselle_demo.pdf --out /tmp/confidence_test.json`

Then check the output:
```bash
python3 -c "
import json
data = json.load(open('/tmp/confidence_test.json'))
for s in data['hardware_sets']:
    print(f\"Set {s['set_number']}: confidence={s['confidence']}\")
    for i, c in enumerate(s['components']):
        low = {k: v for k, v in c['confidence'].items() if v['score'] < 0.5}
        if low:
            print(f\"  comp[{i}] flagged: {low}\")
"
```

Expected: Sets print with confidence scores. Any flagged fields show their reasons.

- [ ] **Step 3: Verify frontend with dev server**

Start API: `.venv/bin/uvicorn hardware_sets_api.app:app --reload`
Start frontend: `cd frontend && npm run dev`

Upload the same demo PDF. Verify:
- Set chips: low-confidence sets have yellow dots
- Detail view: flagged cells have yellow backgrounds
- Hovering flagged cells shows reason tooltips
- Header dot is amber for flagged sets, green for confident sets
