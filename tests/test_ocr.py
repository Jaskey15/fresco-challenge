from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hardware_sets.ocr import ensure_text, needs_ocr


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
        with pytest.raises(RuntimeError, match="OCR preprocessing failed"):
            with ensure_text(Path("outlined.pdf")) as _:
                pass
