from __future__ import annotations

from pathlib import Path

import pdfplumber


def needs_ocr(pdf_path: Path) -> bool:
    with pdfplumber.open(pdf_path) as pdf:
        return len(pdf.pages[0].chars) == 0
