"""Tests for the API pipeline runner."""
from pathlib import Path
from unittest.mock import MagicMock, patch

from hardware_sets.types import (
    HardwareSet, SetLocation, Component, ScheduleRegion, PageLayout, NumberedLine,
)
from hardware_sets_api.pipeline import run_pipeline


def _fake_region():
    return ScheduleRegion(start_page=3, end_page=4, start_marker="group_or_set", end_marker="eof")


def _fake_layout(page: int):
    return PageLayout(page_number=page, lines=[
        NumberedLine(number=1, text="HARDWARE GROUP NO. 1"),
        NumberedLine(number=2, text="3 EA  HINGE  626  IVE"),
    ])


def _fake_set():
    return HardwareSet(
        set_number="1",
        description="ENTRANCE DOORS",
        location=SetLocation(page=3, line_range=(1, 2)),
        components=[Component(qty=3, description="Hinge", catalog_number=None, mfr="IVE", finish="626", notes=None)],
    )


@patch("hardware_sets_api.pipeline.attach_bboxes")
@patch("hardware_sets_api.pipeline.extract_mod")
@patch("hardware_sets_api.pipeline.layout_mod")
@patch("hardware_sets_api.pipeline.filter_mod")
@patch("hardware_sets_api.pipeline.PdfReader")
def test_run_pipeline_emits_progress_and_result(mock_reader, mock_filter, mock_layout, mock_extract, mock_attach):
    mock_reader.return_value.pages = [None] * 5  # 5 pages
    mock_filter.find_schedule_regions.return_value = [_fake_region()]
    mock_layout.extract_layout.side_effect = lambda path, pages: [_fake_layout(p) for p in pages]
    mock_extract.extract_sets.return_value = [_fake_set()]

    progress_events = []
    result = run_pipeline(Path("test.pdf"), on_progress=progress_events.append)

    assert any(e["phase"] == "filter" for e in progress_events)
    assert any(e["phase"] == "extract" for e in progress_events)
    assert result["source_pdf"] == "test.pdf"
    assert len(result["hardware_sets"]) == 1
    assert "3" in result["page_layouts"]
    assert "4" in result["page_layouts"]
    assert result["page_layouts"]["3"]["lines"][0]["text"] == "HARDWARE GROUP NO. 1"


@patch("hardware_sets_api.pipeline.filter_mod")
@patch("hardware_sets_api.pipeline.PdfReader")
def test_run_pipeline_no_regions(mock_reader, mock_filter):
    mock_reader.return_value.pages = [None] * 3
    mock_filter.find_schedule_regions.return_value = []

    result = run_pipeline(Path("empty.pdf"), on_progress=lambda e: None)

    assert result["hardware_sets"] == []
    assert result["diagnostics"]["regions_found"] == 0
