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
