# OCR Preprocessing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add OCR preprocessing so vector-outlined PDFs (zero extractable text) produce results through the existing pipeline.

**Architecture:** New `ocr.py` module with a context manager that detects text-less PDFs and runs `ocrmypdf` to produce a temp text-layered copy. Both CLI and API orchestrators wrap their pipeline body in this context manager. No downstream changes.

**Tech Stack:** `ocrmypdf` (Python), `tesseract-ocr` + `ghostscript` (system), `pdfplumber` (detection)

**Spec:** `docs/superpowers/specs/2026-04-27-ocr-preprocessing-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `src/hardware_sets/ocr.py` | `needs_ocr()` detection + `ensure_text()` context manager |
| Create | `tests/test_ocr.py` | Unit tests for detection and context manager |
| Modify | `src/hardware_sets/cli.py` | Wrap pipeline in `ensure_text()`, add OCR log line |
| Modify | `src/hardware_sets_api/pipeline.py` | Wrap pipeline in `ensure_text()`, emit OCR progress event |
| Modify | `pyproject.toml` | Add `ocrmypdf` dependency |
| Modify | `Dockerfile` | Add `tesseract-ocr` + `ghostscript` system packages |

---

### Task 1: Add `ocrmypdf` dependency

**Files:**
- Modify: `pyproject.toml:6-13`

- [ ] **Step 1: Add ocrmypdf to dependencies**

In `pyproject.toml`, add `ocrmypdf` to the `dependencies` list:

```toml
dependencies = [
    "anthropic>=0.40.0",
    "ocrmypdf>=16.0",
    "pdfplumber>=0.11",
    "pypdf>=5.0",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "python-multipart>=0.0.12",
]
```

- [ ] **Step 2: Install updated dependencies**

Run: `.venv/bin/pip install -e .`
Expected: installs ocrmypdf and its Python dependencies successfully.

- [ ] **Step 3: Verify tesseract is available locally**

Run: `tesseract --version`
Expected: version output. If not installed, run `brew install tesseract ghostscript` first.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add ocrmypdf for vector-outlined PDF support"
```

---

### Task 2: Create `ocr.py` — `needs_ocr()` with tests

**Files:**
- Create: `src/hardware_sets/ocr.py`
- Create: `tests/test_ocr.py`

- [ ] **Step 1: Write failing tests for `needs_ocr()`**

Create `tests/test_ocr.py`:

```python
from pathlib import Path
from unittest.mock import MagicMock, patch

from hardware_sets.ocr import needs_ocr


def test_needs_ocr_returns_false_for_native_pdf():
    with patch("hardware_sets.ocr.pdfplumber.open") as mock_open:
        mock_page = MagicMock()
        mock_page.chars = [{"text": "A"}, {"text": "B"}]
        mock_open.return_value.__enter__.return_value.pages = [mock_page]
        assert needs_ocr(Path("native.pdf")) is False


def test_needs_ocr_returns_true_when_no_chars():
    with patch("hardware_sets.ocr.pdfplumber.open") as mock_open:
        mock_page = MagicMock()
        mock_page.chars = []
        mock_open.return_value.__enter__.return_value.pages = [mock_page]
        assert needs_ocr(Path("outlined.pdf")) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_ocr.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hardware_sets.ocr'`

- [ ] **Step 3: Implement `needs_ocr()`**

Create `src/hardware_sets/ocr.py`:

```python
from __future__ import annotations

from pathlib import Path

import pdfplumber


def needs_ocr(pdf_path: Path) -> bool:
    with pdfplumber.open(pdf_path) as pdf:
        return len(pdf.pages[0].chars) == 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_ocr.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/hardware_sets/ocr.py tests/test_ocr.py
git commit -m "feat: add needs_ocr() detection for text-less PDFs"
```

---

### Task 3: Add `ensure_text()` context manager with tests

**Files:**
- Modify: `src/hardware_sets/ocr.py`
- Modify: `tests/test_ocr.py`

- [ ] **Step 1: Write failing tests for `ensure_text()`**

Append to `tests/test_ocr.py`:

```python
import tempfile
from hardware_sets.ocr import ensure_text


def test_ensure_text_passthrough_when_text_exists():
    with patch("hardware_sets.ocr.needs_ocr", return_value=False):
        original = Path("native.pdf")
        with ensure_text(original) as effective:
            assert effective is original


def test_ensure_text_runs_ocr_and_yields_temp_path():
    with patch("hardware_sets.ocr.needs_ocr", return_value=True), \
         patch("hardware_sets.ocr.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        original = Path("outlined.pdf")
        with ensure_text(original) as effective:
            assert effective != original
            assert effective.suffix == ".pdf"
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args[0] == "ocrmypdf"
            assert str(original) in args


def test_ensure_text_cleans_up_temp_file():
    with patch("hardware_sets.ocr.needs_ocr", return_value=True), \
         patch("hardware_sets.ocr.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        with ensure_text(Path("outlined.pdf")) as effective:
            temp_path = effective
        assert not temp_path.exists()


def test_ensure_text_raises_on_ocr_failure():
    with patch("hardware_sets.ocr.needs_ocr", return_value=True), \
         patch("hardware_sets.ocr.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="tesseract failed")
        with ensure_text(Path("outlined.pdf")) as _:
            pass  # should raise before or during yield
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_ocr.py -v`
Expected: FAIL — `ImportError: cannot import name 'ensure_text'`

- [ ] **Step 3: Implement `ensure_text()`**

Update `src/hardware_sets/ocr.py`:

```python
from __future__ import annotations

import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pdfplumber


def needs_ocr(pdf_path: Path) -> bool:
    with pdfplumber.open(pdf_path) as pdf:
        return len(pdf.pages[0].chars) == 0


@contextmanager
def ensure_text(pdf_path: Path) -> Iterator[Path]:
    if not needs_ocr(pdf_path):
        yield pdf_path
        return

    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()
    tmp_path = Path(tmp.name)
    try:
        result = subprocess.run(
            ["ocrmypdf", str(pdf_path), str(tmp_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "No extractable text found and OCR preprocessing failed."
            )
        yield tmp_path
    finally:
        tmp_path.unlink(missing_ok=True)
```

- [ ] **Step 4: Update the failure test to use pytest.raises**

The `test_ensure_text_raises_on_ocr_failure` test needs to assert the exception. Update it:

```python
import pytest

def test_ensure_text_raises_on_ocr_failure():
    with patch("hardware_sets.ocr.needs_ocr", return_value=True), \
         patch("hardware_sets.ocr.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="tesseract failed")
        with pytest.raises(RuntimeError, match="OCR preprocessing failed"):
            with ensure_text(Path("outlined.pdf")) as _:
                pass
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_ocr.py -v`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add src/hardware_sets/ocr.py tests/test_ocr.py
git commit -m "feat: add ensure_text() context manager for OCR preprocessing"
```

---

### Task 4: Integrate into `pipeline.py` (API path)

**Files:**
- Modify: `src/hardware_sets_api/pipeline.py:1-91`

- [ ] **Step 1: Add OCR import and wrap pipeline body**

Update `src/hardware_sets_api/pipeline.py`. Add the import at the top:

```python
from hardware_sets.ocr import needs_ocr, ensure_text
```

Replace the body of `run_pipeline` — emit an OCR progress event when needed, then wrap everything in the context manager. The `source_pdf` field must still use the original `pdf_path.name`:

```python
def run_pipeline(
    pdf_path: Path,
    on_progress: Callable[[dict], None],
    *,
    model: str | None = None,
) -> dict:
    if needs_ocr(pdf_path):
        on_progress({"phase": "ocr", "message": "Document has no extractable text, running OCR..."})

    with ensure_text(pdf_path) as effective_path:
        total_pages = len(PdfReader(str(effective_path)).pages)
        on_progress({"phase": "filter", "message": f"Scanning {total_pages} pages..."})

        regions = filter_mod.find_schedule_regions(effective_path)
        if not regions:
            on_progress({"phase": "filter", "message": "No schedule regions found"})
            return {
                "source_pdf": pdf_path.name,
                "hardware_sets": [],
                "page_layouts": {},
                "diagnostics": {
                    "pages_scanned": total_pages,
                    "regions_found": 0,
                    "pages_with_sets": 0,
                    "llm_calls": 0,
                    "warnings": ["no_schedule_found"],
                },
            }

        on_progress({
            "phase": "filter",
            "message": f"Found {len(regions)} region(s)",
        })

        all_sets: list[HardwareSet] = []
        all_layouts: dict[str, dict] = {}
        warnings: list[str] = []
        llm_calls = 0

        for i, region in enumerate(regions, start=1):
            on_progress({
                "phase": "extract",
                "message": f"Extracting sets from region {i}/{len(regions)}...",
            })

            layouts = layout_mod.extract_layout(
                effective_path, range(region.start_page, region.end_page + 1),
            )

            for lay in layouts:
                all_layouts[str(lay.page_number)] = {
                    "lines": [
                        {"number": line.number, "text": line.text, "bbox": line.bbox}
                        for line in lay.lines
                    ],
                    "page_width": lay.page_width,
                    "page_height": lay.page_height,
                }

            try:
                extract_kwargs = {"model": model} if model else {}
                sets = extract_mod.extract_sets(region, layouts, **extract_kwargs)
                attach_bboxes(sets, layouts)
                llm_calls += 1
                all_sets.extend(sets)
            except Exception as e:
                warnings.append(f"region {region.start_page}-{region.end_page}: {e}")

        return {
            "source_pdf": pdf_path.name,
            "hardware_sets": [asdict(s) for s in all_sets],
            "page_layouts": all_layouts,
            "diagnostics": {
                "pages_scanned": total_pages,
                "regions_found": len(regions),
                "pages_with_sets": sum(r.end_page - r.start_page + 1 for r in regions),
                "llm_calls": llm_calls,
                "warnings": warnings,
            },
        }
```

- [ ] **Step 2: Run existing tests to verify no regressions**

Run: `.venv/bin/pytest -v`
Expected: all tests pass

- [ ] **Step 3: Commit**

```bash
git add src/hardware_sets_api/pipeline.py
git commit -m "feat: integrate OCR preprocessing into API pipeline"
```

---

### Task 5: Integrate into `cli.py` (CLI path)

**Files:**
- Modify: `src/hardware_sets/cli.py:1-126`

- [ ] **Step 1: Add OCR import and wrap pipeline body**

Add the import at the top of `cli.py`:

```python
from hardware_sets.ocr import needs_ocr, ensure_text
```

In `main()`, after the `ANTHROPIC_API_KEY` check (line 63) and before `total_pages`, add OCR detection and wrap the rest of the pipeline body in the context manager. The function should look like:

```python
def main(argv: list[str]) -> int:
    args = parse_args(argv)
    _setup_logging(args.quiet)

    if not args.pdf_path.is_file():
        print(f"error: pdf not found: {args.pdf_path}", file=sys.stderr)
        return 1
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: ANTHROPIC_API_KEY is not set", file=sys.stderr)
        return 1

    if needs_ocr(args.pdf_path):
        log.info("[0/2] ocr: no text detected, running OCR...")

    with ensure_text(args.pdf_path) as effective_path:
        total_pages = _page_count(effective_path)

        log.info("[1/2] filter: scanning %d pages of %s", total_pages, args.pdf_path.name)
        regions = filter_mod.find_schedule_regions(effective_path)
        if not regions:
            log.warning("no schedule region found")
            _emit(
                {
                    "source_pdf": args.pdf_path.name,
                    "hardware_sets": [],
                    "diagnostics": {
                        "pages_scanned": total_pages,
                        "regions_found": 0,
                        "pages_with_sets": 0,
                        "llm_calls": 0,
                        "warnings": ["no_schedule_found"],
                    },
                },
                args.out,
            )
            return 2

        log.info("[1/2] filter: found %d region(s): %s",
                 len(regions), ", ".join(f"pgs {r.start_page}-{r.end_page}" for r in regions))

        all_sets: list[HardwareSet] = []
        warnings: list[str] = []
        llm_calls = 0

        for i, region in enumerate(regions, start=1):
            log.info("[2/2] extract: region %d/%d pages %d-%d", i, len(regions), region.start_page, region.end_page)
            layouts = layout_mod.extract_layout(
                effective_path, range(region.start_page, region.end_page + 1),
            )
            try:
                sets = extract_mod.extract_sets(region, layouts, model=args.model)
                attach_bboxes(sets, layouts)
                llm_calls += 1
                log.info("[2/2] extract: region %d/%d -> %d set(s)", i, len(regions), len(sets))
                all_sets.extend(sets)
            except Exception as e:
                log.error("extract failed for region %d-%d: %s", region.start_page, region.end_page, e)
                return 3

        result = {
            "source_pdf": args.pdf_path.name,
            "hardware_sets": [asdict(s) for s in all_sets],
            "diagnostics": {
                "pages_scanned": total_pages,
                "regions_found": len(regions),
                "pages_with_sets": sum(r.end_page - r.start_page + 1 for r in regions),
                "llm_calls": llm_calls,
                "warnings": warnings,
            },
        }
        _emit(result, args.out)
        return 0
```

- [ ] **Step 2: Run all tests to verify no regressions**

Run: `.venv/bin/pytest -v`
Expected: all tests pass

- [ ] **Step 3: Commit**

```bash
git add src/hardware_sets/cli.py
git commit -m "feat: integrate OCR preprocessing into CLI pipeline"
```

---

### Task 6: Update Dockerfile

**Files:**
- Modify: `Dockerfile:9-15`

- [ ] **Step 1: Add system packages for OCR**

In the `Dockerfile`, after the `FROM python:3.12-slim` line and before `COPY pyproject.toml`, add the system package installation:

```dockerfile
FROM python:3.12-slim
WORKDIR /app

# System deps for OCR (tesseract + ghostscript required by ocrmypdf)
RUN apt-get update && \
    apt-get install -y --no-install-recommends tesseract-ocr ghostscript && \
    rm -rf /var/lib/apt/lists/*

# Python deps
COPY pyproject.toml ./
COPY src/ src/
RUN pip install --no-cache-dir -e .
```

- [ ] **Step 2: Verify Docker build succeeds**

Run: `docker build -t fresco-challenge .`
Expected: builds successfully with tesseract and ghostscript installed

- [ ] **Step 3: Commit**

```bash
git add Dockerfile
git commit -m "build: add tesseract and ghostscript to Docker image for OCR"
```

---

### Task 7: Manual integration test with `little_rock.pdf`

**Files:**
- No file changes — validation only

- [ ] **Step 1: Run CLI against little_rock.pdf**

Run: `export $(grep -v '^#' .env.local | xargs) && .venv/bin/python -m hardware_sets samples/non-pdf/little_rock.pdf --out /tmp/little_rock_result.json`

Expected output in stderr:
```
[0/2] ocr: no text detected, running OCR...
[1/2] filter: scanning 9 pages of little_rock.pdf
[1/2] filter: found N region(s): ...
[2/2] extract: ...
```

- [ ] **Step 2: Verify output has hardware sets**

Run: `python -c "import json; d=json.load(open('/tmp/little_rock_result.json')); print(f'{len(d[\"hardware_sets\"])} sets extracted')"`

Expected: non-zero number of sets extracted.

- [ ] **Step 3: Run full test suite one final time**

Run: `.venv/bin/pytest -v`
Expected: all tests pass

- [ ] **Step 4: Commit (if any fixups were needed)**

Only if prior steps revealed issues that required code changes.
