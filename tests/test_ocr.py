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
