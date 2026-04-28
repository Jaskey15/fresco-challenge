from __future__ import annotations

import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pdfplumber


def needs_ocr(pdf_path: Path) -> str | None:
    """Return an OCR reason string, or None if the PDF has readable text.

    Scans all pages to handle mixed documents (e.g. native cover + scanned schedule).
    Returns:
        ``"no_text"``      — no extractable characters (vector-outlined / scanned)
        ``"cid_encoded"``  — chars exist but fonts use unresolvable CID encoding
        ``None``           — text is readable
    """
    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            return None
        has_no_text = False
        for page in pdf.pages:
            if len(page.chars) == 0:
                has_no_text = True
                continue
            text = page.extract_text() or ""
            if "(cid:" in text:
                return "cid_encoded"
        return "no_text" if has_no_text else None


@contextmanager
def ensure_text(pdf_path: Path, *, ocr_needed: str | None = None) -> Iterator[Path]:
    if ocr_needed is None:
        ocr_needed = needs_ocr(pdf_path)
    if not ocr_needed:
        yield pdf_path
        return

    force = ocr_needed == "cid_encoded"
    ocr_flag = "--force-ocr" if force else "--skip-text"

    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()
    tmp_path = Path(tmp.name)
    try:
        result = subprocess.run(
            ["ocrmypdf", ocr_flag, "-O", "0", "--fast-web-view", "0", "-j", "4", str(pdf_path), str(tmp_path)],
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
