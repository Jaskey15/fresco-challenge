# OCR Preprocessing for Vector-Outlined PDFs

**Date:** 2026-04-27
**Context:** [OCR Investigation](../../2026-04-27-ocr-investigation.md)

## Problem

Some specbook PDFs have all text converted to vector outlines (bezier curves). pdfplumber finds zero characters, so the pipeline produces no results. This was surfaced by Fresco's CTO testing with `little_rock.pdf`.

## Solution

Add an OCR preprocessing step that detects text-less PDFs and runs `ocrmypdf` to produce a text-layered copy before the existing pipeline runs. The rest of the pipeline (filter → layout → extract) operates unchanged on the OCR'd output.

## Design

### New module: `src/hardware_sets/ocr.py`

Two public functions:

- **`needs_ocr(pdf_path: Path) -> bool`** — Opens page 1 with pdfplumber, returns `True` if `len(page.chars) == 0`. Single-page check is sufficient because vector outlining is a global export setting that affects all pages uniformly.

- **`ensure_text(pdf_path: Path) -> Iterator[Path]`** — Context manager. If `needs_ocr()` is `False`, yields the original path unchanged. If `True`, runs `ocrmypdf <input> <output>` via `subprocess.run` (no special flags needed — the input has no text so defaults are fine), writing to a `tempfile.NamedTemporaryFile`, yields the temp path, and deletes it on context exit.

### Integration: `pipeline.py` (API path)

`run_pipeline` wraps its body in `with ensure_text(pdf_path) as effective_path:`. Before OCR, calls `needs_ocr()` and if true, emits a progress event:

```python
{"phase": "ocr", "message": "Document has no extractable text, running OCR..."}
```

All downstream references use `effective_path`. The `source_pdf` field in the result dict still uses the original `pdf_path.name`.

### Integration: `cli.py` (CLI path)

Same context manager pattern. Logs `[0/2] ocr: no text detected, running OCR...` when triggered. Step numbering for filter/extract stays `[1/2]` and `[2/2]` — OCR is a conditional pre-step.

### Integration: `routes.py`

No changes. Routes pass `pdf_path` to `run_pipeline`, which handles OCR internally.

### Temp file lifecycle

The OCR'd PDF is a transient artifact. The API stores the original PDF bytes in the session store for the frontend viewer — the temp file only needs to live for the duration of the pipeline run. The context manager's `finally` block guarantees cleanup even on errors.

### Error handling

- **ocrmypdf failure:** Raise an exception with message "No extractable text found and OCR preprocessing failed." Bubbles up as exit code 3 (CLI) or error SSE event (API).
- **Tesseract not installed:** ocrmypdf's own error propagates naturally.
- **OCR succeeds but filter finds no regions:** Legitimate outcome — pipeline returns zero sets as normal.

### Dependencies

**Python:** Add `ocrmypdf` to `pyproject.toml`.

**System (Dockerfile):** Add `tesseract-ocr` and `ghostscript` to `apt-get install` in the Python runtime stage. Adds ~200MB to the Docker image.

**Local dev:** Requires `brew install tesseract ghostscript` (macOS).

### Testing

**Unit tests (`tests/test_ocr.py`):**
- `test_needs_ocr_native_pdf` — native PDF returns `False`
- `test_needs_ocr_no_text` — mock pdfplumber returning zero chars, returns `True`
- `test_ensure_text_native_passthrough` — native PDF yields original path, no temp file
- `test_ensure_text_ocr_path` — mock subprocess, verify yields different path and cleans up on exit

**Manual integration test:** Run `little_rock.pdf` through CLI end-to-end, confirm sets are produced.

## Out of scope

- Mixed-PDF detection (some pages outlined, some native) — not a realistic scenario for single-author spec sections.
- Scanned/raster PDF handling — ocrmypdf handles these too, but no samples to validate against.
- Frontend changes — the UI renders whatever progress events arrive; `"phase": "ocr"` needs no special treatment.
