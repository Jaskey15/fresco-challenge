from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hardware_sets.ocr import ensure_text, needs_ocr


def test_needs_ocr_returns_none_for_native_pdf():
    with patch("hardware_sets.ocr.pdfplumber.open") as mock_open:
        mock_page = MagicMock()
        mock_page.chars = [{"text": "A"}, {"text": "B"}]
        mock_page.extract_text.return_value = "AB"
        mock_open.return_value.__enter__.return_value.pages = [mock_page]
        assert needs_ocr(Path("native.pdf")) is None


def test_needs_ocr_returns_no_text_when_no_chars():
    with patch("hardware_sets.ocr.pdfplumber.open") as mock_open:
        mock_page = MagicMock()
        mock_page.chars = []
        mock_open.return_value.__enter__.return_value.pages = [mock_page]
        assert needs_ocr(Path("outlined.pdf")) == "no_text"


def test_needs_ocr_returns_cid_encoded_for_cid_fonts():
    with patch("hardware_sets.ocr.pdfplumber.open") as mock_open:
        mock_page = MagicMock()
        mock_page.chars = [{"text": "(cid:43)"}, {"text": "(cid:68)"}]
        mock_page.extract_text.return_value = "(cid:43)(cid:68)(cid:85)(cid:71)"
        mock_open.return_value.__enter__.return_value.pages = [mock_page]
        assert needs_ocr(Path("cid.pdf")) == "cid_encoded"


def test_needs_ocr_returns_none_for_empty_pdf():
    with patch("hardware_sets.ocr.pdfplumber.open") as mock_open:
        mock_open.return_value.__enter__.return_value.pages = []
        assert needs_ocr(Path("empty.pdf")) is None


def test_ensure_text_passthrough_when_text_exists():
    with patch("hardware_sets.ocr.needs_ocr", return_value=None):
        original = Path("native.pdf")
        with ensure_text(original) as effective:
            assert effective is original


def test_ensure_text_runs_skip_text_for_no_text():
    with patch("hardware_sets.ocr.needs_ocr", return_value="no_text"), \
         patch("hardware_sets.ocr.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        original = Path("outlined.pdf")
        with ensure_text(original) as effective:
            assert effective != original
            assert effective.suffix == ".pdf"
            args = mock_run.call_args[0][0]
            assert "--skip-text" in args


def test_ensure_text_runs_force_ocr_for_cid():
    with patch("hardware_sets.ocr.needs_ocr", return_value="cid_encoded"), \
         patch("hardware_sets.ocr.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        with ensure_text(Path("cid.pdf")) as effective:
            assert effective.suffix == ".pdf"
            args = mock_run.call_args[0][0]
            assert "--force-ocr" in args


def test_ensure_text_cleans_up_temp_file():
    with patch("hardware_sets.ocr.needs_ocr", return_value="no_text"), \
         patch("hardware_sets.ocr.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        with ensure_text(Path("outlined.pdf")) as effective:
            temp_path = effective
        assert not temp_path.exists()


def test_ensure_text_raises_on_ocr_failure():
    with patch("hardware_sets.ocr.needs_ocr", return_value="no_text"), \
         patch("hardware_sets.ocr.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="tesseract failed")
        with pytest.raises(RuntimeError, match="OCR preprocessing failed"):
            with ensure_text(Path("outlined.pdf")) as _:
                pass
