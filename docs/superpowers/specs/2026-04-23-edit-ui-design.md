# Edit UI: Inline Row Operations

**Date:** 2026-04-23
**Status:** Draft
**Scope:** Add delete-row and add-row capabilities to the DetailTable component, plus an edit-aware download badge.

## Goal

Extend the existing inline cell editing with row-level operations (delete and add) so users can fully correct extraction mistakes — not just fix values, but remove hallucinated components and add missed ones. The UI should feel minimal and contextual: row actions appear on hover, not at rest.

## Design Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Delete style | Hard delete with inline confirmation | Simpler state than soft delete; confirmation strip is the safety net |
| Add style | Empty row, cell-by-cell | Consistent with existing click-to-edit pattern; no forms or modals |
| Row action visibility | Hover only | Keeps table clean at rest; primary job is reading data |
| State model | Working copy with diff | Avoids index re-keying headache from granular edit tracking |
| Persistence | None (client-side only) | Matches current architecture; download is the save action |
| Save indicator | Badge on download button | Gives product feel without backend changes |

## Interaction Specification

### Delete Row

1. **At rest:** No delete affordance visible. Table rows look exactly as they do now.
2. **On hover:** A small `×` icon appears in a narrow rightmost column, styled in `dim` color.
3. **On click (`×`):** The row content is replaced by an inline confirmation strip:
   - Text: `Remove "{description}"?` — uses description if available, falls back to catalog_number, falls back to `"this component"` if both are null.
   - Two buttons: **Remove** (error/red style) and **Cancel** (muted border style)
   - Strip uses `error-subtle` background with `error` border tint.
4. **On confirm (Remove):** Row is spliced from the working copy. Table re-renders without it.
5. **On cancel:** Row returns to normal display.
6. No undo after confirmation — the confirmation is the safety net.

### Add Row

1. Below the last table row, a `+ Add component` link sits in a dashed-border area, styled in `dim` color.
2. **On hover:** Text and border shift to `accent` color.
3. **On click:** A new empty row is appended to the working copy with all fields set to `null`. The row appears at the bottom of the table. Focus lands on the first cell (QTY) in edit mode.
4. User fills in cells using the existing inline editing (click, type, Tab to advance, Enter to commit).
5. New rows can be deleted with the same `×` → confirm pattern.
6. No visual distinction needed for added rows — they behave identically to extracted rows.

### Download Badge

1. When edits exist (any combination of cell changes, deletions, additions), a summary badge appears next to the download button.
2. Badge format: `{n} edits · {n} added · {n} removed` — only segments with non-zero counts are shown.
3. Badge uses existing `accent-subtle` background + `accent` text + `accent/30` border (same style as the "X edited" badge in the table header).
4. When no edits exist, no badge — button looks the same as current.

### Bottom Bar Hint

Update the instruction text from:
```
Click any cell to edit · Tab to advance · Esc to cancel
```
To:
```
Click any cell to edit · Tab to advance · Esc to cancel · Hover row for actions
```

## State Model

### Current

```typescript
// ResultsView.tsx
edits: Record<number, Record<number, Record<string, string>>>
// setIdx → compIdx → field → editedValue
```

### New

```typescript
// ResultsView.tsx
workingData: Record<number, Component[]>
// setIdx → modified components array (lazily cloned from original on first edit)
```

**Lifecycle:**
- On first interaction with a set (cell edit, delete, or add), deep-clone that set's `components` array into `workingData[setIdx]`.
- All handlers produce new state immutably (React requires new references for re-renders):
  - `handleCellEdit(compIdx, field, value)` — clone the array, update the field on the target component, set new state.
  - `handleDelete(compIdx)` — clone the array with the target index filtered out, set new state.
  - `handleAdd()` — clone the array with an empty component appended (`{ qty: null, description: null, catalog_number: null, mfr: null, finish: null, notes: null }`), set new state.
  - `handleReset()` — delete `workingData[setIdx]` key (falls back to original).
  - `handleDownload()` — for each set, use `workingData[setIdx]` if it exists, otherwise original.

**Diff computation** (for badge counts):
- Each working copy component gets a `_sourceIndex: number | null` tag when cloned (original index) or added (`null` for new rows). This tag is not exported in download.
- **Removed count:** original indices not present in any working copy component's `_sourceIndex`.
- **Added count:** working copy components where `_sourceIndex` is `null`.
- **Edited count:** working copy components with a `_sourceIndex` whose field values differ from the original at that index.
- This runs at render time; with 3-15 components per set it's negligible.

## Files Modified

### `ResultsView.tsx`
- Replace `edits` state with `workingData: Record<number, Component[]>` state.
- Rewrite `handleCellEdit` to mutate working copy.
- Add `handleDelete(compIdx: number)` — splice from working copy.
- Add `handleAdd()` — push empty component to working copy.
- Rewrite `handleReset` to delete working copy key.
- Rewrite `handleDownload` to use working copies.
- Add `computeDiffSummary(setIdx)` helper for badge counts.
- Add `computeTotalDiffSummary()` for the download badge (across all sets).
- Render badge next to download button.

### `DetailTable.tsx`
- Add props: `onDelete: (compIndex: number) => void`, `onAdd: () => void`.
- Add narrow rightmost `<th>` / `<td>` column for row actions.
- Implement hover-reveal `×` button using Tailwind `group`/`group-hover` on `<tr>`.
- Add `ConfirmStrip` inline component: renders confirmation row replacing normal row content.
- Track `confirmingIndex: number | null` local state for which row is showing confirmation.
- Render `+ Add component` area below `</tbody>`.
- Update bottom bar hint text.

### No new files, no new dependencies.

## Edge Cases

- **Empty set (all rows deleted):** Table shows only the `+ Add component` area and column headers. No special empty state needed.
- **Reset after mixed operations:** Clears everything — cell edits, deletions, additions — back to original extraction. The reset button already exists and this behavior is intuitive.
- **Download with no working copies:** Behaves identically to current — exports original data untouched.
- **NOT USED sets:** Already handled — DetailTable shows "This set is marked as NOT USED" and doesn't render the table. No edit operations available. No change needed.

## Out of Scope

- Backend persistence of edits
- Undo/redo history
- Reordering rows
- Moving components between sets
- localStorage session persistence
- Confidence score display on edited fields
