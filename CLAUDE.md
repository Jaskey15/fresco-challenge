# Fresco Coding Challenge — Hardware Sets

Interview challenge for Fresco (construction-tech startup). Extract **hardware sets** from Division 08 (Openings) specbook PDFs into structured JSON with per-set location data (page + line range / bbox).

Input: specbook pages (section-list format or tabular schedule). Output per set: `set_number`, `description`, `location`, `components[] {qty, description, catalog_number, mfr, finish, notes}`.

## Stack
- **Extractor:** Python 3.12, `pdfplumber` + `pypdf`, `anthropic` SDK, `pytest`. Package: `src/hardware_sets/` (CLI).
- **API:** FastAPI + uvicorn. Package: `src/hardware_sets_api/` — wraps the extractor, serves `frontend/dist/` as static in prod.
- **Frontend:** React 19 + TypeScript + Vite + Tailwind v4 in `frontend/`.
- **Deploy:** Single-service Docker (multi-stage: Node build → Python runtime with poppler) → Fly.io app `fresco-challenge` (region `iad`). Config in `Dockerfile` + `fly.toml`.

## Run
- CLI: `.venv/bin/python -m hardware_sets <pdf> --out result.json`
- API dev: `export $(grep -v '^#' .env.local | xargs) && .venv/bin/uvicorn hardware_sets_api.app:app --reload`
- Frontend dev: `cd frontend && npm run dev`
- Tests: `.venv/bin/pytest`
- Deploy: `fly deploy`

## Critical Rules
- **mfr vs. finish is column-level, not value-level.** Codes are ambiguous (PE = Pemko or Painted Enamel; NO = Norton or "No"). Resolve from the surrounding column (MK/LCN/SCH → mfr; US26D/630/BSP → finish), never per-cell.
- **Never guess missing quantities** — emit `null`.
- **Every set needs location data** (page + line range or bbox). It's a graded success criterion.
- Keep "NOT USED" / N/A sets — they still count.
- Sets can span page breaks — don't drop continuations.
- `samples/` is gitignored — do not commit. `demo_samples/` IS committed (bundled into the deployed image for the public demo).
- `ANTHROPIC_API_KEY` is required at runtime; set via `.env.local` locally and `fly secrets` in prod.
- **PDFs can be native-text, scanned, or vector-outlined** (text converted to curves). Detect by checking pdfplumber char count — zero chars means OCR preprocessing is needed. Use `ocrmypdf --skip-text` to add a text layer, then run the normal pipeline. One codepath, not two.

## Lessons Learned
- `little_rock.pdf` had zero extractable text (vector-outlined) → added OCR detection/preprocessing. Problem: no PDF metadata distinguishes the three types. Rule: always check char count, never assume text exists.
