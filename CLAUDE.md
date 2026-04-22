# Fresco Coding Challenge — Hardware Sets

Interview challenge for Fresco (construction-tech startup). Extract **hardware sets** from Division 08 (Openings) specbook PDFs into structured JSON with per-set location data (page + line range / bbox).

Input: specbook pages (section-list format or tabular schedule). Output per set: `set_number`, `description`, `location`, `components[] {qty, description, catalog_number, mfr, finish, notes}`.

## Stack
Python 3.12, `pdfplumber` + `pypdf`, `anthropic` SDK, `pytest`. Run: `python -m hardware_sets ...`.

## Critical Rules
- **mfr vs. finish is column-level, not value-level.** Codes are ambiguous (PE = Pemko or Painted Enamel; NO = Norton or "No"). Resolve from the surrounding column (MK/LCN/SCH → mfr; US26D/630/BSP → finish), never per-cell.
- **Never guess missing quantities** — emit `null`.
- **Every set needs location data** (page + line range or bbox). It's a graded success criterion.
- Keep "NOT USED" / N/A sets — they still count.
- Sets can span page breaks — don't drop continuations.
- Don't commit anything under `samples/` or `out/`.

## Deliverables
Repo + README, deployed link or local run steps, 3–5 min Loom. Evaluated on: extraction accuracy, mfr/finish handling, code quality, explanation clarity.

## Lessons Learned
_(empty — add `Problem → Rule` entries as they come up)_
