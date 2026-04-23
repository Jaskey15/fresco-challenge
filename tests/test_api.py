"""Tests for the API endpoints."""
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from hardware_sets_api.app import app
from hardware_sets_api import session

client = TestClient(app)


def test_get_samples():
    resp = client.get("/api/samples")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2
    assert all("id" in s and "name" in s and "label" in s for s in data)


def test_get_pdf_serves_stored_bytes():
    sid = session.put(b"%PDF-fake-content", "test.pdf")
    resp = client.get(f"/api/pdf/{sid}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content == b"%PDF-fake-content"


def test_get_pdf_expired_returns_404():
    resp = client.get("/api/pdf/nonexistent-session-id")
    assert resp.status_code == 404


@patch("hardware_sets_api.routes.session")
@patch("hardware_sets_api.routes.run_pipeline")
def test_extract_sample_streams_sse(mock_pipeline, mock_session):
    mock_session.put.return_value = "test-session-id"
    mock_pipeline.side_effect = lambda path, on_progress: (
        on_progress({"phase": "filter", "message": "Scanning 5 pages..."}),
        {
            "source_pdf": "test.pdf",
            "hardware_sets": [],
            "page_layouts": {},
            "diagnostics": {"pages_scanned": 5, "regions_found": 0, "pages_with_sets": 0, "llm_calls": 0, "warnings": []},
        },
    )[-1]

    resp = client.post("/api/extract/sample/bridgeport")
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    body = resp.text
    assert "event: progress" in body
    assert "event: result" in body


def test_extract_sample_not_found():
    resp = client.post("/api/extract/sample/nonexistent")
    assert resp.status_code == 404
