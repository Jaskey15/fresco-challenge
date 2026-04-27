from __future__ import annotations

import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pdfplumber


def needs_ocr(pdf_path: Path) -> bool:
    """Check first page only — assumes uniform PDF type (all native or all outlined)."""
    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            return False
        return len(pdf.pages[0].chars) == 0


@contextmanager
def ensure_text(pdf_path: Path, *, ocr_needed: bool | None = None) -> Iterator[Path]:
    if ocr_needed is None:
        ocr_needed = needs_ocr(pdf_path)
    if not ocr_needed:
        yield pdf_path
        return

    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()
    tmp_path = Path(tmp.name)
    try:
        result = subprocess.run(
            ["ocrmypdf", "--skip-text", str(pdf_path), str(tmp_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"No extractable text found and OCR preprocessing failed: {result.stderr}"
            )
        yield tmp_path
    finally:
        tmp_path.unlink(missing_ok=True)
