# Filter Structural Detection Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace vocab-dependent filter detection with structural pattern tiering, a broadened tabular guard, and a simplified heuristic — then remove dead code (`vocab.py`, `resolve.py`).

**Architecture:** `filter.py` gains a `needs_guard` flag on each START_PATTERN. High-confidence patterns (set/group markers) bypass the tabular guard; low-confidence patterns (section headers) still require it. The tabular guard broadens to recognize more quantity formats. The heuristic drops vocab imports and uses structural signals only. `vocab.py` and `resolve.py` are deleted.

**Tech Stack:** Python 3.12, `pdftotext`, `pypdf`, `pytest`

**Key files:**
- `src/hardware_sets/filter.py` — all production changes
- `tests/test_filter_patterns.py` — all test changes
- `src/hardware_sets/vocab.py` — delete
- `src/hardware_sets/resolve.py` — delete
- `tests/test_resolve_scoring.py` — delete
- `scripts/baseline_filter.snapshot` — update

**Baseline command:** `.venv/bin/python scripts/baseline_filter.py 2>/dev/null | diff scripts/baseline_filter.snapshot -`

**Test command:** `.venv/bin/pytest tests/test_filter_patterns.py -v`

---

### Task 1: Tier START_PATTERNS with `needs_guard` flag

Add a boolean to each pattern tuple indicating whether the tabular guard is required. Update `_match_start` to return the flag alongside the pattern name. Update `find_schedule_regions` to only apply the guard when the flag is set.

**Files:**
- Modify: `src/hardware_sets/filter.py:22-34` (START_PATTERNS), `src/hardware_sets/filter.py:77-82` (_match_start), `src/hardware_sets/filter.py:124-135` and `src/hardware_sets/filter.py:147-155` (find_schedule_regions guard logic)
- Modify: `tests/test_filter_patterns.py:7-9` (import), `tests/test_filter_patterns.py:15-60` (pattern tests)

- [ ] **Step 1: Update START_PATTERNS to 3-tuples with `needs_guard` flag**

Change the data structure from `list[tuple[str, Pattern]]` to `list[tuple[str, Pattern, bool]]`. Low-confidence patterns (section headers that repeat on every page) get `True`; high-confidence patterns (specific set/group markers) get `False`.

```python
START_PATTERNS: list[tuple[str, re.Pattern[str], bool]] = [
    # Low confidence — section headers that repeat on every page; require tabular guard
    ("door_hardware_schedule", re.compile(r"DOOR\s+HARDWARE\s+SCHEDULE", re.I), True),
    ("hardware_sets_colon",    re.compile(r"\bHardware\s+Sets\s*:", re.I), True),
    ("schedule_section_3dot",  re.compile(r"^\s*3\.\d+\s+(?:HARDWARE\s+)?SCHEDULE", re.I | re.M), True),
    ("hardware_schedule_head", re.compile(r"(?:^|\n)\s*Hardware\s+Schedule\s*$", re.I | re.M), True),
    # High confidence — specific set/group markers; bypass tabular guard
    ("group_or_set",    re.compile(r"Hardware\s+(?:Group|Set)(?:/Set)?\s*(?:No\.?|#)\s*\S+", re.I), False),
    ("hw_number",       re.compile(r"\bHW\s+\d+", re.I), False),
    ("set_label",       re.compile(r"\bSet[:\s]+(?:EX-?)?\d", re.I), False),
    ("set_hash",        re.compile(r"\bSet\s+#\s*\S+", re.I), False),
    ("heading_number",  re.compile(r"\bHeading\s+#\s*\d+", re.I), False),
]
```

- [ ] **Step 2: Update `_match_start` to return `(name, needs_guard)` or `(None, False)`**

```python
def _match_start(text: str) -> tuple[str | None, bool]:
    """Return (name, needs_guard) for the first matching pattern, else (None, False)."""
    for name, pat, needs_guard in START_PATTERNS:
        if pat.search(text):
            return name, needs_guard
    return None, False
```

- [ ] **Step 3: Update `find_schedule_regions` to use the new return type**

Two locations use `_match_start` — the initial detection block (lines 124-135) and the section-change re-check block (lines 147-155). Both need the same change.

In the initial detection block, replace:
```python
name = _match_start(text)
if name and not _has_tabular_content(text):
    name = None
```
with:
```python
name, needs_guard = _match_start(text)
if name and needs_guard and not _has_tabular_content(text):
    name = None
```

In the section-change re-check block, replace:
```python
name = _match_start(text)
if name and not _has_tabular_content(text):
    name = None
```
with:
```python
name, needs_guard = _match_start(text)
if name and needs_guard and not _has_tabular_content(text):
    name = None
```

- [ ] **Step 4: Update existing tests for new `_match_start` return type**

All existing `_match_start` tests assert on the return value. Since the return type changes from `str | None` to `tuple[str | None, bool]`, update each test to unpack or index. For example:

```python
def test_start_door_hardware_schedule():
    name, needs_guard = _match_start("DOOR HARDWARE SCHEDULE")
    assert name == "door_hardware_schedule"
    assert needs_guard is True

def test_start_group_or_set():
    name, _ = _match_start("Hardware Group No. 01")
    assert name == "group_or_set"
    name, _ = _match_start("Hardware Set #1")
    assert name == "group_or_set"
    name, _ = _match_start("Hardware Group/Set #103")
    assert name == "group_or_set"

def test_start_set_label():
    name, needs_guard = _match_start("Set: EX-1.0")
    assert name == "set_label"
    assert needs_guard is False

def test_start_no_match_on_narrative():
    name, _ = _match_start("Hardware sets are indicated on Drawings.")
    assert name is None
```

Update all pattern tests (`test_start_hardware_sets_colon`, `test_start_schedule_section_3dot`, `test_start_hardware_schedule_head`, `test_start_hw_number`, `test_start_set_hash`, `test_start_heading_number`) in the same way — unpack the tuple return.

- [ ] **Step 5: Run tests**

Run: `.venv/bin/pytest tests/test_filter_patterns.py -v`
Expected: All tests PASS. The heuristic tests still pass because the heuristic path is unchanged so far.

- [ ] **Step 6: Run baseline to observe impact of tiering alone**

Run: `.venv/bin/python scripts/baseline_filter.py 2>/dev/null | diff scripts/baseline_filter.snapshot -`

Expected changes:
- `jc_ryan_2.pdf`: `heuristic` → `set_label` (high-confidence pattern now bypasses guard)
- `roselle_public_library_08.pdf`: may still show `heuristic` (depends on whether `door_hardware_schedule` is still guarded and guard still fails — expected, will be fixed in Task 2)

Review each diff line — no other samples should change.

- [ ] **Step 7: Commit**

```bash
git add src/hardware_sets/filter.py tests/test_filter_patterns.py
git commit -m "refactor(filter): tier START_PATTERNS by confidence level

High-confidence patterns (set/group markers) now bypass the tabular
guard. Low-confidence patterns (section headers) still require it."
```

---

### Task 2: Broaden the Tabular Guard

Widen `_has_tabular_content` to recognize more schedule formats. The current regexes miss roselle-style quantity lines (bare numbers without EA/Set/Pr unit words) and lines with hardware component keywords.

**Files:**
- Modify: `src/hardware_sets/filter.py:45-53` (_has_tabular_content and its regexes)

- [ ] **Step 1: Broaden `_has_tabular_content` with additional regexes**

Add new regex patterns and update the function. Keep existing patterns (they still work for the samples they cover).

```python
_TABULAR_ROW_RE = re.compile(r"\b\d+\s+(?:EA(?:-[A-Z])?|Ea\.|Set|Pr)\b", re.I | re.M)
_BARE_QTY_LINE = re.compile(r"^\s+\d+\s+\w", re.M)
_QTY_LEADING_LINE = re.compile(r"^\s*\d+\s+[A-Z]", re.M)
_DASH_QTY = re.compile(r"(?:^|\s)--\s+\w", re.M)
_HW_COMPONENT_RE = re.compile(
    r"\d+.*(?:HINGE|CLOSER|LOCKSET|STRIKE|BOLT|THRESHOLD|GASKETING|SWEEP|CYLINDER|STOP|PANIC|EXIT\s+DEVICE)",
    re.I,
)


def _has_tabular_content(text: str) -> bool:
    if _TABULAR_ROW_RE.search(text):
        return True
    if len(_BARE_QTY_LINE.findall(text)) >= 3:
        return True
    if len(_QTY_LEADING_LINE.findall(text)) >= 3:
        return True
    if _DASH_QTY.search(text) and _QTY_LEADING_LINE.search(text):
        return True
    if len(_HW_COMPONENT_RE.findall(text)) >= 2:
        return True
    return False
```

- [ ] **Step 2: Run all tests**

Run: `.venv/bin/pytest tests/test_filter_patterns.py -v`
Expected: ALL PASS — existing tabular and prose-rejection tests still hold.

- [ ] **Step 3: Run baseline to observe combined impact (tiering + broadened guard)**

Run: `.venv/bin/python scripts/baseline_filter.py 2>/dev/null | diff scripts/baseline_filter.snapshot -`

Expected changes from old baseline:
- `roselle_public_library_08.pdf`: `heuristic` → `door_hardware_schedule` (guard now passes on p15)
- `jc_ryan_2.pdf`: `heuristic` → `set_label` (from Task 1, still holds)
- `morris_bank_08.pdf`: regions may shift — watch carefully. Region 1 (p27-33) should disappear or change since p27 is narrative with no hardware keywords. Region 2 should tighten.

Review each diff. If the broadened guard is accidentally passing on narrative pages (false positives), tighten the thresholds or keyword list.

- [ ] **Step 4: Commit**

```bash
git add src/hardware_sets/filter.py
git commit -m "refactor(filter): broaden tabular guard for more schedule formats

Add quantity-leading line density, dash-quantity, and hardware
component keyword checks. Roselle-style schedules now pass the
guard instead of falling to the heuristic."
```

---

### Task 3: Simplify the Heuristic (Remove Vocab Dependency)

Strip vocab imports from `_heuristic_start`. Replace the two vocab-based signals with a single structural signal (quantity-line density). Adjust threshold from 3-of-4 to 2-of-3.

**Files:**
- Modify: `src/hardware_sets/filter.py:85-100` (_heuristic_start)
- Modify: `tests/test_filter_patterns.py:72-83` (heuristic tests)

- [ ] **Step 1: Rewrite `_heuristic_start` without vocab**

```python
_QTY_LEADING_RE = re.compile(r"^\s*\d+\s+\S", re.M)


def _heuristic_start(text: str) -> bool:
    """Fallback: 2+ of (SET token, QTY/EA keyword, quantity-line density)."""
    signals = 0
    if _SET_TOKEN_RE.search(text):
        signals += 1
    if _QTY_HDR_RE.search(text) or _EA_RE.search(text):
        signals += 1
    if len(_QTY_LEADING_RE.findall(text)) >= 3:
        signals += 1
    return signals >= 2
```

Note: `_QTY_LEADING_RE` may overlap with `_QTY_LEADING_LINE` from Task 2. If the pattern is identical (`^\s*\d+\s+[A-Z]` vs `^\s*\d+\s+\S`), consolidate into a single module-level regex. The heuristic version uses `\S` (any non-space) which is slightly broader — keep one and use it in both places, or keep both if the stricter `[A-Z]` version is needed for the guard.

- [ ] **Step 2: Remove the old vocab import comment**

Delete the comment on line 43: `# A known-mfr or known-finish code presence is checked against vocab.`

- [ ] **Step 3: Update heuristic tests to use structural signals instead of vocab**

Replace the existing tests that depend on vocab (`SCH` as a known mfr code) with tests that use the new structural signals:

```python
def test_heuristic_fallback_fires_on_structural_signals():
    # SET token + QTY keyword + multiple quantity-leading lines
    text = "SET 1\n\nQTY  DESCRIPTION\n 1  Hinge\n 2  Closer\n 1  Lockset"
    assert _heuristic_start(text)


def test_heuristic_fires_on_set_and_qty_lines():
    # SET token + quantity-line density (no QTY keyword)
    text = "SET 1\n1 Hinge\n2 Closer\n1 Lockset\n3 Strike"
    assert _heuristic_start(text)


def test_heuristic_does_not_fire_on_narrative():
    assert not _heuristic_start(
        "The hardware sets specified in this section shall comply with the project requirements."
    )


def test_heuristic_does_not_fire_on_single_signal():
    # Only QTY keyword, no SET, no qty-line density
    assert not _heuristic_start("QTY  DESCRIPTION  MFR\nSome narrative text follows.")
```

- [ ] **Step 4: Run all tests**

Run: `.venv/bin/pytest tests/test_filter_patterns.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Run baseline**

Run: `.venv/bin/python scripts/baseline_filter.py 2>/dev/null | diff scripts/baseline_filter.snapshot -`

Key check: morris_bank. With the heuristic tightened (no vocab, structural-only), the false positive regions at p27-33 and p40 should either disappear or tighten. The actual schedule at p53 should still be caught (by `hardware_sets_colon` pattern, not heuristic).

- [ ] **Step 6: Commit**

```bash
git add src/hardware_sets/filter.py tests/test_filter_patterns.py
git commit -m "refactor(filter): remove vocab dependency from heuristic

Replace mfr/finish vocab signals with quantity-line density.
Threshold changes from 3-of-4 to 2-of-3 structural signals."
```

---

### Task 4: Delete Dead Code (`vocab.py`, `resolve.py`, and their tests)

With `filter.py` no longer importing from `vocab.py`, and `resolve.py` already disconnected from the pipeline, both modules are dead code.

**Files:**
- Delete: `src/hardware_sets/vocab.py`
- Delete: `src/hardware_sets/resolve.py`
- Delete: `tests/test_resolve_scoring.py`

- [ ] **Step 1: Verify no remaining imports**

```bash
grep -rn "from hardware_sets.vocab\|import vocab\|from hardware_sets.resolve\|import resolve" src/ tests/ scripts/ --include="*.py"
```

Expected: No output (no remaining imports). If any hits remain, address them before deleting.

- [ ] **Step 2: Delete the files**

```bash
git rm src/hardware_sets/vocab.py src/hardware_sets/resolve.py tests/test_resolve_scoring.py
```

- [ ] **Step 3: Run full test suite**

Run: `.venv/bin/pytest tests/ -v`
Expected: ALL PASS. No import errors.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore: remove dead vocab.py, resolve.py, and their tests

No remaining consumers after filter heuristic was rewritten to
use structural signals instead of static vocabulary."
```

---

### Task 5: Update Baseline Snapshot

Run the baseline, review the full output, and update the snapshot file.

**Files:**
- Modify: `scripts/baseline_filter.snapshot`

- [ ] **Step 1: Capture new baseline output**

```bash
.venv/bin/python scripts/baseline_filter.py 2>/dev/null
```

Review the full output. Check each sample:
- **Shubie**: should be unchanged (`35-36 schedule_section_3dot`)
- **Valor**: should be unchanged (`7-18 group_or_set`)
- **Roselle**: should now show `door_hardware_schedule` instead of `heuristic`, same pages `15-17`
- **Bridgeport**: should be unchanged (`3-49 hardware_schedule_head`)
- **SJC**: should be unchanged (`161-198 hw_number`)
- **JC Ryan**: should now show `set_label` instead of `heuristic`, same pages `24-46`
- **Morris Bank**: should show fewer/tighter regions — ideally 1 region starting around p49-53 via `hardware_sets_colon`
- **Star**: should be unchanged (`25-26` and `53-113 group_or_set`)

- [ ] **Step 2: Diff against old snapshot for a clear summary**

```bash
.venv/bin/python scripts/baseline_filter.py 2>/dev/null | diff scripts/baseline_filter.snapshot -
```

Every diff line should be an improvement. If anything looks like a regression (lost region, wrong pages), investigate before updating.

- [ ] **Step 3: Update snapshot**

```bash
.venv/bin/python scripts/baseline_filter.py 2>/dev/null > scripts/baseline_filter.snapshot
```

- [ ] **Step 4: Run final verification — diff should now be empty**

```bash
.venv/bin/python scripts/baseline_filter.py 2>/dev/null | diff scripts/baseline_filter.snapshot -
```

Expected: No output (baseline matches snapshot).

- [ ] **Step 5: Commit**

```bash
git add scripts/baseline_filter.snapshot
git commit -m "chore(baseline): update snapshot after structural detection redesign

Roselle: heuristic → door_hardware_schedule (same pages)
JC Ryan: heuristic → set_label (same pages)
Morris Bank: false-positive regions eliminated, tighter bounds"
```
